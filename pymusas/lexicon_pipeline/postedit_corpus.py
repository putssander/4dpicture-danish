#!/usr/bin/env python3
"""Cross-family post-edit of a machine-translated corpus — the API version of the
manual propositions workflow documented in GOLD_STRATEGY.md.

Two reviewer LLMs from DIFFERENT families each review the draft against the English
source, restricted to real errors (non-words, mistranslations, grammar) with
minimal-diff corrections. A fix is applied only when BOTH families flag the sentence
(single-family proposals are logged for an optional native pass, never applied);
the first reviewer's wording is adopted. This guardrail exists because for languages
without a native judge, a single annotator family must not become co-author of the
text it will later annotate. It also catches real reviewer errors — in the Danish run
GPT-5.6 "corrected" rainfall from mm to ml and produced the non-word "kvaering";
both were blocked/repaired by the cross-check.

Example:
  python postedit_corpus.py --source results/llm_gold/coffee_eng.txt \
      --draft results/llm_gold/coffee_dan_draft_qwen.txt \
      --reviewers openai:gpt-5.6 google:gemini-3.1-pro \
      --out results/llm_gold/coffee_dan_fixed.txt
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from llm_client import Client  # noqa: E402

REVIEW_PROMPT = """\
Below is an English source sentence and a draft translation (a coffee-website text,
plain informative register). Judge the draft ONLY for actual errors: non-existent
words, mistranslations relative to the English source, grammatical/agreement errors,
and calques no native text would use.

Reply with EXACTLY one line:
OK                          - if the draft has no such errors (even if you could phrase it more elegantly)
FIX<TAB>corrected sentence  - ONLY if the draft contains a real error

BE CONSERVATIVE - there is no native speaker to double-check you, so propose a FIX
only when you are confident something is wrong, never for style or taste. Keep the
correction minimal: change as few words as possible, keep the rest of the draft
wording untouched, keep it one sentence, no explanations.

EN: {source}
DRAFT: {draft}"""


def review(client, source_lines, draft_lines, ckpt_path):
    done = {}
    if ckpt_path.exists():
        done = {int(k): v for k, v in json.loads(ckpt_path.read_text()).items()}
    for i, (src, drf) in enumerate(zip(source_lines, draft_lines)):
        if i in done:
            continue
        raw = client.ask(REVIEW_PROMPT.format(source=src, draft=drf))
        line = raw.strip().splitlines()[0] if raw.strip() else "OK"
        if line.upper().startswith("FIX"):
            fix = line[3:].strip("\t :").strip()
            done[i] = {"verdict": "FIX", "text": " ".join(fix.split())} if fix else {"verdict": "OK"}
        else:
            done[i] = {"verdict": "OK"}
        ckpt_path.write_text(json.dumps(done, ensure_ascii=False))
        if (i + 1) % 10 == 0:
            print(f"  {i + 1}/{len(source_lines)}")
    return done


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", required=True, help="English source, one sentence per line")
    ap.add_argument("--draft", required=True, help="draft translation, one sentence per line")
    ap.add_argument("--reviewers", nargs=2, required=True,
                    help="two aisuite model ids from different families; "
                         "the FIRST reviewer's wording is adopted on agreement")
    ap.add_argument("--out", required=True, help="fixed corpus output path")
    args = ap.parse_args()

    src = [l.strip() for l in open(args.source) if l.strip()]
    drf = [l.strip() for l in open(args.draft) if l.strip()]
    assert len(src) == len(drf), f"line counts differ: {len(src)} vs {len(drf)}"

    out_path = Path(args.out)
    reviews = {}
    for m in args.reviewers:
        print(f"reviewer: {m}")
        slug = m.replace(":", "_").replace("/", "_")
        reviews[m] = review(Client(m), src, drf,
                            out_path.with_suffix(f".ckpt_{slug}.json"))

    r1, r2 = (reviews[m] for m in args.reviewers)
    fixed, log = [], {}
    for i, line in enumerate(drf):
        f1, f2 = r1[i]["verdict"] == "FIX", r2[i]["verdict"] == "FIX"
        if f1 and f2:
            fixed.append(r1[i]["text"])
            log[i] = {"status": "fixed", "note": "both flag; first reviewer's wording",
                      "old": line, "new": r1[i]["text"], "alt": r2[i]["text"]}
        elif f1 or f2:
            fixed.append(line)
            which = args.reviewers[0] if f1 else args.reviewers[1]
            log[i] = {"status": "flagged_only", "note": f"single family ({which}); not applied",
                      "old": line, "proposal": (r1 if f1 else r2)[i]["text"]}
        else:
            fixed.append(line)
    out_path.write_text("\n".join(fixed) + "\n")
    log_path = out_path.with_suffix(".postedit_log.json")
    log_path.write_text(json.dumps(log, ensure_ascii=False, indent=1))
    n_fix = sum(1 for v in log.values() if v["status"] == "fixed")
    n_flag = len(log) - n_fix
    print(f"wrote {out_path}: {n_fix} fixed (both families), {n_flag} flagged-only -> {log_path}")
    print("REVIEW THE LOG: single-family proposals go to the native pass, and applied "
          "fixes should be spot-checked (reviewers can be confidently wrong).")


if __name__ == "__main__":
    main()
