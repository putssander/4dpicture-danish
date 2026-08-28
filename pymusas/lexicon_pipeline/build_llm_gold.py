#!/usr/bin/env python3
"""Build an LLM-committee USAS reference set — and calibrate the procedure on human gold.

The project needs to evaluate its Danish (and Dutch) USAS lexicons but no human gold
exists for those languages. This tool implements the two-step design documented in
GOLD_STRATEGY.md:

  CALIBRATE   Run a committee of frontier LLMs (independent annotators + a judge for
              disagreements) over a language that HAS human gold (Finnish; English as a
              second check). Committee-vs-human agreement is the measured credibility of
              LLM-built gold — obtained before any new language is touched.

  BUILD       Run the IDENTICAL committee (same prompts, same parsing, same adjudication)
              over new-language text (Danish, Dutch) and emit a benedict-format reference
              file that run_usas_wsd_eval.py can score lexicons against, plus a review
              spreadsheet for optional native-speaker checking (rows where the committee
              disagreed are flagged first — that is where human minutes matter most).

Terminology discipline: the output is an **LLM-adjudicated reference set**, not gold.
Report lexicon accuracy against it together with the calibration number, e.g. "the
committee itself agrees with human gold at X% on Finnish". See GOLD_STRATEGY.md for the
shared-error caveat (the lexicon under evaluation was also machine-translated) and the
mitigations (different model families; the Finnish/Dutch validation legs).

Examples:
  # step 1 — calibration on Finnish human gold (no new data involved):
  python build_llm_gold.py calibrate --language fin \\
      --models openai:gpt-5.6 anthropic:claude-fable-5 --judge anthropic:claude-opus-5

  # step 2 — build a Danish reference from text (one sentence per line):
  python build_llm_gold.py build --input danish_coffee.txt --code dan \\
      --language-name Danish --spacy-model da_core_news_sm \\
      --models openai:gpt-5.6 anthropic:claude-fable-5 --judge anthropic:claude-opus-5

  # step 3 — evaluate the Danish lexicon against it:
  python run_usas_wsd_eval.py --gold-file results/llm_gold/benedict_dan.txt \\
      --language dan --language-name Danish --system rule \\
      --single-lexicon ../../pymusas_danish/lexicons/da/semantic_lexicon_da_fixed.tsv \\
      --mwe-lexicon ../../pymusas_danish/lexicons/da/mwe_da_fixed.tsv \\
      --spacy-model da_core_news_sm
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from usas_llm import make_llm, llm_tag_sentence, normalise
from usas_wsd import LANGUAGE_NAMES, load_usas_wsd, score_predictions, sentences

COMMITTEE_JUDGE_PROMPT = """\
You are adjudicating USAS semantic tags for {language} text. The full USAS tagset was
provided above. Independent annotators disagreed on some tokens of this sentence.

Sentence tokens:
{tokens}

Disputed tokens (number: each annotator's code):
{disputes}

For each disputed token, decide the correct code — one of the proposed codes or a better
one. Return ONLY a JSON object mapping token numbers to codes, e.g. {{"3": "B2"}}.
"""


class _Args:                                   # adapter for usas_llm.make_llm
    def __init__(self, model, model2=None, judge=None):
        self.model, self.model2, self.judge = model, model2, judge


def committee_annotate(sents, models, judge_model, language, ckpt_path=None):
    """Annotate sentences with N independent LLMs (+ optional judge).

    Returns (finals, stats, detail).
    finals: list (per sentence) of {token_index(1-based): code}
    detail: per-token record of every model's code, for the review sheet.
    ckpt_path: JSON file storing every model's raw answers per sentence; a rerun
    resumes instead of re-paying for completed sentences.
    """
    clients = []
    system = None
    for m in models:
        c, _, _, system = make_llm(_Args(m))
        clients.append((m, c))
    judge, _, _, _ = make_llm(_Args(judge_model)) if judge_model else (None,) * 4
    judge = judge if judge_model else None

    ckpt = {}
    if ckpt_path and Path(ckpt_path).exists():
        ckpt = json.loads(Path(ckpt_path).read_text())
        print(f"  resuming: {len(ckpt)} sentences already annotated")

    finals, detail = [], []
    stats = Counter()
    for n, sent in enumerate(sents, 1):
        key = str(n)
        if key in ckpt:
            per_model = {m: {int(i): c for i, c in ckpt[key][m].items()} for m in ckpt[key]}
        else:
            per_model = {m: llm_tag_sentence(c, system, sent, language) for m, c in clients}
            if ckpt_path:
                ckpt[key] = {m: {str(i): c for i, c in v.items()} for m, v in per_model.items()}
                Path(ckpt_path).write_text(json.dumps(ckpt, ensure_ascii=False))
        final = {}
        disputes = {}
        for i in range(1, len(sent) + 1):
            codes = [per_model[m].get(i, "") for m in per_model]
            nonempty = [c for c in codes if c]
            if not nonempty:
                stats["no_code"] += 1
                continue
            if len(set(nonempty)) == 1 and len(nonempty) == len(codes):
                final[i] = nonempty[0]
                stats["unanimous"] += 1
            else:
                disputes[i] = codes
                # provisional: majority, else first non-empty
                top, k = Counter(nonempty).most_common(1)[0]
                final[i] = top
                stats["majority" if k > 1 else "single_vote"] += 1
        if disputes and judge is not None:
            numbered = "\n".join(f"{i + 1}: {r['token']}" for i, r in enumerate(sent))
            dtext = "\n".join(
                f"{i}: " + " vs ".join(c or "(none)" for c in cs)
                for i, cs in disputes.items())
            parsed, _ = judge.ask_json(
                COMMITTEE_JUDGE_PROMPT.format(language=language, tokens=numbered,
                                              disputes=dtext), system=system)
            if isinstance(parsed, dict):
                for k_, v in parsed.items():
                    try:
                        i = int(k_)
                    except (ValueError, TypeError):
                        continue
                    code = normalise(v)
                    if i in disputes and code:
                        final[i] = code
                        stats["judge_decided"] += 1
        finals.append(final)
        for i, r in enumerate(sent, 1):
            detail.append({"sentence": n, "index": i, "token": r["token"],
                           **{m: per_model[m].get(i, "") for m in per_model},
                           "final": final.get(i, ""),
                           "disputed": i in disputes})
        if n % 10 == 0:
            print(f"  {n}/{len(sents)} sentences")
    return finals, stats, detail


def tokenize_input(path, spacy_model):
    """Turn plain text (one sentence per line preferred) into gold-style row dicts."""
    import spacy
    nlp = spacy.load(spacy_model, exclude=["ner", "parser"])
    rows = []
    sent_id = 0
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        for tok in nlp(line.strip()):
            if tok.is_space:
                continue
            rows.append({"sent_id": sent_id, "token": tok.text,
                         "gold_label": "", "gold_fields": []})
        sent_id += 1
    return rows


def write_outputs(rows, finals, stats, detail, code, out_dir, meta):
    out_dir.mkdir(parents=True, exist_ok=True)
    # benedict-format reference file (tokens without a code are left unlabelled)
    lines = []
    for sent, final in zip(sentences(rows), finals):
        parts = []
        for i, r in enumerate(sent, 1):
            c = final.get(i, "")
            parts.append(f"{r['token']}_{c}" if c else r["token"])
        lines.append(" ".join(parts))
    gold_path = out_dir / f"benedict_{code}.txt"
    gold_path.write_text("\n".join(lines), encoding="utf-8")

    import pandas as pd
    review = pd.DataFrame(detail)
    review = review.sort_values(["disputed", "sentence", "index"],
                                ascending=[False, True, True])
    review_path = out_dir / f"review_{code}.xlsx"
    review.to_excel(review_path, index=False)

    (out_dir / f"stats_{code}.json").write_text(json.dumps(
        {**meta, "stats": dict(stats)}, ensure_ascii=False, indent=1))
    print(f"\nWrote {gold_path}\n      {review_path} (disagreements first — review those)"
          f"\n      {out_dir / f'stats_{code}.json'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--models", nargs="+", required=True,
                       help="two or more annotator LLMs (aisuite ids), STRONGEST FIRST "
                            "— on disputes with no majority the first-listed wins")
        p.add_argument("--judge", default=None,
                       help="judge LLM (aisuite id). OFF by default: measured on Finnish "
                            "gold, a judge choosing between bare codes scored 48.9%% on "
                            "disputes, below the 62.2%% of trusting the stronger annotator "
                            "(GOLD_STRATEGY.md). The default recipe is unanimity labels + "
                            "strongest-annotator fallback, disputes flagged for review.")
        p.add_argument("--limit", type=int, help="max sentences (smoke test)")
        p.add_argument("--out-dir", default=str(Path(__file__).parent / "work"))

    c = sub.add_parser("calibrate", help="committee vs existing human gold")
    c.add_argument("--language", required=True, choices=("fin", "eng", "cym", "zho"))
    common(c)

    b = sub.add_parser("build", help="build a reference set for a new language")
    b.add_argument("--input", required=True, help="text file, one sentence per line")
    b.add_argument("--code", required=True, help="ISO 639-3 code, e.g. dan, nld")
    b.add_argument("--language-name", required=True, help="e.g. Danish, Dutch")
    b.add_argument("--spacy-model", required=True, help="e.g. da_core_news_sm, nl_core_news_sm")
    common(b)

    args = ap.parse_args()
    out_dir = Path(args.out_dir)
    meta = {"cmd": args.cmd, "models": args.models, "judge": args.judge,
            "run_utc": datetime.now(timezone.utc).isoformat()}

    if args.cmd == "calibrate":
        rows = load_usas_wsd(args.language)
        sents = sentences(rows)[: args.limit or None]
        rows = [r for s in sents for r in s]
        language = LANGUAGE_NAMES[args.language]
        print(f"Calibration on {language}: {len(rows)} labelled tokens, "
              f"{len(sents)} sentences, committee {args.models} + judge {args.judge}")
        ckpt = out_dir / f"ckpt_committee_calib_{args.language}.json"
        finals, stats, detail = committee_annotate(sents, args.models, args.judge, language,
                                                   ckpt_path=ckpt)

        preds = []
        for sent, final in zip(sents, finals):
            preds.extend([final.get(i, "")] for i in range(1, len(sent) + 1))
        acc = score_predictions(rows, preds, level=None)
        acc1 = score_predictions(rows, preds, level=1)
        print(f"\n=== Committee vs human gold | {language} ===")
        print(f"Agreement (exact codes):  {acc * 100:.1f}%")
        print(f"Agreement (USAS level 1): {acc1 * 100:.1f}%")
        print(f"Committee stats: {dict(stats)}")
        print("Compare with the rule-based lexicon reference for this language "
              "(run_usas_wsd_eval.py --system rule) and the published Table 12 numbers.")
        meta.update({"language": args.language, "agreement_exact": acc,
                     "agreement_level1": acc1})
        write_outputs(rows, finals, stats, detail, f"calib_{args.language}", out_dir, meta)

    else:
        rows = tokenize_input(args.input, args.spacy_model)
        sents = sentences(rows)[: args.limit or None]
        rows = [r for s in sents for r in s]
        print(f"Building {args.language_name} reference: {len(rows)} tokens, "
              f"{len(sents)} sentences, committee {args.models} + judge {args.judge}")
        finals, stats, detail = committee_annotate(sents, args.models, args.judge,
                                                   args.language_name,
                                                   ckpt_path=out_dir / f"ckpt_committee_build_{args.code}.json")
        meta.update({"language": args.code, "input": args.input,
                     "note": "LLM-adjudicated reference set, NOT human gold; report with "
                             "the calibration agreement from the calibrate step"})
        write_outputs(rows, finals, stats, detail, args.code, out_dir, meta)


if __name__ == "__main__":
    main()
