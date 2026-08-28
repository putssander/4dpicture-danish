#!/usr/bin/env python3
"""Do we still need the lexicon? Rule-based vs LLM vs LLM+judge vs hybrid on USAS gold.

Evaluates USAS semantic tagging against the human gold data of Moore, Rayson et al. 2026
(USAS-WSD; no Danish exists, so the method is validated on languages that have gold —
Finnish and Chinese are the cleanest, see usas_wsd.py). Four systems:

  rule       PyMUSAS rule-based tagger built from a lexicon (the paper's approach).
             Validate the harness first by reproducing the published numbers:
             eng 72.4 / cym 70.6 / fin 58.4 / zho 32.6 (Table 12, n=1).
  llm        A single LLM tags each sentence directly: it receives the numbered tokens
             and the USAS tagset, returns one code per token. No lexicon involved.
  llm-judge  Two LLMs tag independently; where they disagree a judge model picks
             (or overrules with) a code. The "replace the translator with top LLMs and
             a judge" configuration.
  hybrid     Rule-based first; the LLM only tags tokens the lexicon left unmatched
             (Z99). The configuration the paper found best (rules + neural fallback),
             with the LLM in the fallback seat.

Scoring follows the paper: token-level top-1 accuracy over labelled tokens, exact codes
(--level exact). A gold label with multi-tag membership (``I2.2/H1`` asserts BOTH fields)
counts as correct if the prediction matches any of its fields. Producing no code counts
as wrong, never as a skip. --level 1 adds the project's level-1 figure (GRANULARITY.md)
as a secondary, clearly-labelled number.

Examples:
  # validate the harness (no LLM needed):
  python run_usas_wsd_eval.py --language fin --system rule \\
      --single-lexicon https://raw.githubusercontent.com/UCREL/Multilingual-USAS/master/Finnish/semantic_lexicon_fin.tsv \\
      --spacy-model fi_core_news_sm
  # your own translated lexicon for a language with gold:
  python run_usas_wsd_eval.py --language fin --system rule --single-lexicon my_fin.tsv --spacy-model fi_core_news_sm
  # the LLM contenders:
  python run_usas_wsd_eval.py --language fin --system llm --model ollama:gemma3:27b
  python run_usas_wsd_eval.py --language zho --system llm-judge \\
      --model ollama:gemma3:27b --model2 ollama:qwen2.5:72b --judge ollama:llama3.3:70b
  python run_usas_wsd_eval.py --language fin --system hybrid --model ollama:gemma3:27b \\
      --single-lexicon .../semantic_lexicon_fin.tsv --spacy-model fi_core_news_sm
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from usas_wsd import (LANGUAGE_NAMES, PUBLISHED_RULE_BASED, load_benedict,
                      load_usas_wsd, score_predictions, sentences)

from usas_llm import (TAGSET_PATH, LLM_PROMPT, JUDGE_PROMPT, normalise,  # noqa: F401
                      make_llm, llm_tag_sentence)

# ---------------------------------------------------------------- rule-based system
def run_rule(rows, args):
    from spacy.tokens import Doc
    from pymusas_tagger import from_lexicons

    nlp = from_lexicons(args.single_lexicon, args.mwe_lexicon, args.spacy_model)
    preds = []
    for sent in sentences(rows):
        # Feed spaCy the GOLD tokenization directly: alignment is then exact by
        # construction (re-tokenizing and re-aligning loses ~1/3 of tokens).
        doc = Doc(nlp.vocab, words=[r["token"] for r in sent])
        for _, proc in nlp.pipeline:
            doc = proc(doc)
        for tok in doc:
            # Unlike the metaphor harnesses, KEEP grammatical Z tags (except Z99):
            # the gold labels function words (The_Z5) and the paper scores them.
            raw = getattr(tok._, "pymusas_tags", None) or []
            fields = []
            if raw:
                for part in str(raw[0]).split("/"):
                    code = normalise(part)
                    if code and code != "Z99":
                        fields.append(code)
            preds.append(fields)
    return preds


# ---------------------------------------------------------------- LLM systems
def run_llm(rows, args, judge_mode=False):
    client, client2, judge, system = make_llm(args)
    language = LANGUAGE_NAMES[args.language]
    preds = []
    for n, sent in enumerate(sentences(rows), 1):
        a = llm_tag_sentence(client, system, sent, language)
        final = dict(a)
        if judge_mode:
            b = llm_tag_sentence(client2, system, sent, language)
            disputes = {i: (a.get(i, ""), b.get(i, ""))
                        for i in range(1, len(sent) + 1) if a.get(i) != b.get(i)}
            for i, (ca, cb) in disputes.items():
                final[i] = ca or cb          # provisional: non-empty one
            if disputes and judge:
                numbered = "\n".join(f"{i + 1}: {r['token']}" for i, r in enumerate(sent))
                dtext = "\n".join(f"{i}: {ca or '(none)'} vs {cb or '(none)'}"
                                  for i, (ca, cb) in disputes.items())
                parsed, _ = judge.ask_json(
                    JUDGE_PROMPT.format(language=language, tokens=numbered,
                                        disputes=dtext), system=system)
                if isinstance(parsed, dict):
                    for k, v in parsed.items():
                        try:
                            final[int(k)] = normalise(v)
                        except (ValueError, TypeError):
                            continue
        preds.extend([final.get(i + 1, "")] for i in range(len(sent)))
        if n % 10 == 0:
            print(f"  {n} sentences")
    return preds


def run_hybrid(rows, args):
    rule_preds = run_rule(rows, args)
    # find sentences containing unmatched tokens; LLM tags only those tokens
    client, _, _, system = make_llm(args)
    language = LANGUAGE_NAMES[args.language]
    preds = list(rule_preds)
    idx = 0
    n_fallback = 0
    for sent in sentences(rows):
        span = list(range(idx, idx + len(sent)))
        unmatched = [i for i in span if not preds[i] or not preds[i][0]]
        if unmatched:
            llm_codes = llm_tag_sentence(client, system, sent, language)
            for i in unmatched:
                local = i - idx + 1
                if llm_codes.get(local):
                    preds[i] = [llm_codes[local]]
                    n_fallback += 1
        idx += len(sent)
    print(f"  hybrid: LLM filled {n_fallback} unmatched tokens")
    return preds


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--language", required=True,
                    help="fin/eng/cym/zho for the published gold, or any code (dan, nld) "
                         "with --gold-file")
    ap.add_argument("--gold-file",
                    help="benedict-format reference file (e.g. built by build_llm_gold.py) "
                         "to score against instead of the published gold")
    ap.add_argument("--language-name", help="display name for a custom --language")
    ap.add_argument("--system", required=True,
                    choices=("rule", "llm", "llm-judge", "hybrid"))
    ap.add_argument("--single-lexicon", help="lexicon TSV/URL (rule, hybrid)")
    ap.add_argument("--mwe-lexicon", help="MWE lexicon TSV/URL (rule, hybrid)")
    ap.add_argument("--spacy-model", help="spaCy model for the language (rule, hybrid)")
    ap.add_argument("--model", help="aisuite id of the (first) LLM")
    ap.add_argument("--model2", help="second annotator LLM (llm-judge)")
    ap.add_argument("--judge", help="judge LLM (llm-judge)")
    ap.add_argument("--limit", type=int, help="max sentences (smoke test)")
    ap.add_argument("--out")
    args = ap.parse_args()

    if args.gold_file:
        if args.language_name:
            LANGUAGE_NAMES.setdefault(args.language, args.language_name)
        rows = load_benedict(args.gold_file, args.language)
    elif args.language in ("fin", "eng", "cym", "zho"):
        rows = load_usas_wsd(args.language)
    else:
        ap.error(f"language {args.language!r} has no published gold — pass --gold-file")
        return
    if args.limit:
        keep = {s[0]["sent_id"] for s in sentences(rows)[:args.limit]}
        rows = [r for r in rows if r["sent_id"] in keep]
    print(f"{LANGUAGE_NAMES[args.language]}: {len(rows)} labelled tokens, "
          f"{len(sentences(rows))} sentences | system: {args.system}")

    if args.system == "rule":
        if not (args.single_lexicon and args.spacy_model):
            ap.error("rule needs --single-lexicon and --spacy-model")
        preds = run_rule(rows, args)
    elif args.system == "hybrid":
        if not (args.single_lexicon and args.spacy_model and args.model):
            ap.error("hybrid needs --single-lexicon, --spacy-model and --model")
        preds = run_hybrid(rows, args)
    elif args.system == "llm":
        if not args.model:
            ap.error("llm needs --model")
        preds = run_llm(rows, args)
    else:
        if not (args.model and args.model2 and args.judge):
            ap.error("llm-judge needs --model, --model2 and --judge")
        preds = run_llm(rows, args, judge_mode=True)

    acc_exact = score_predictions(rows, preds, level=None)
    acc_l1 = score_predictions(rows, preds, level=1)
    covered = sum(1 for p in preds if p and p[0]) / len(preds) if preds else 0.0

    print(f"\n=== USAS-WSD | {LANGUAGE_NAMES[args.language]} | {args.system} ===")
    print(f"Top-1 accuracy (exact codes, paper protocol): {acc_exact * 100:.1f}%")
    pub = PUBLISHED_RULE_BASED.get(args.language)
    if args.system == "rule" and pub:
        print(f"  published rule-based reference:             {pub}%")
    print(f"Accuracy at USAS level 1 (project measure):   {acc_l1 * 100:.1f}%")
    print(f"Tokens with a prediction:                     {covered * 100:.1f}%")

    out = Path(args.out) if args.out else (
        Path(__file__).parent / "results" /
        f"usas_wsd_{args.language}_{args.system}"
        f"{'_' + args.model.replace(':', '_') if args.model else ''}"
        f"{'_' + Path(args.single_lexicon).stem.replace('semantic_lexicon_', '')
           if args.single_lexicon else ''}"
        # a custom gold file is a DIFFERENT evaluation: name it, or runs on
        # the default gold get silently overwritten by e.g. par-leg runs
        f"{'_ON_' + Path(args.gold_file).stem.replace('benedict_', '')
           if args.gold_file else ''}.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({
        "eval": "usas_wsd_gold", "language": args.language, "system": args.system,
        "models": {k: getattr(args, k) for k in ("model", "model2", "judge")},
        "lexicon": args.single_lexicon, "run_utc": datetime.now(timezone.utc).isoformat(),
        "n_tokens": len(rows), "accuracy_exact": acc_exact, "accuracy_level1": acc_l1,
        "coverage": covered, "published_rule_based": pub,
        "predictions": [{"token": r["token"], "gold": r["gold_label"],
                         "pred": p[0] if p else ""} for r, p in zip(rows, preds)],
    }, ensure_ascii=False, indent=1))
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
