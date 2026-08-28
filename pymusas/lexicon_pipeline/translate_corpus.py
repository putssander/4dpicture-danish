#!/usr/bin/env python3
"""Translate the reference corpus EN -> target language, one sentence per line.

Uses any aisuite model id. For the family-separation design the translator must be a
DIFFERENT family from every committee annotator (the project used Qwen on a local vLLM
endpoint: set OPENAI_BASE_URL=http://localhost:8000/v1 OPENAI_API_KEY=none and pass
openai:qwen). Checkpointed per line — safe to interrupt and rerun.

Example:
  python translate_corpus.py --source results/llm_gold/coffee_eng.txt \
      --language Danish --model openai:qwen --out results/llm_gold/coffee_dan_draft.txt
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from llm_client import Client  # noqa: E402

PROMPT = """\
Translate the following English sentence(s) into {language}. Plain informative
register (it is text from a coffee website). Reply with ONLY the translation,
one line, no commentary.

{line}"""


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", required=True, help="English source, one sentence per line")
    ap.add_argument("--language", required=True, help="target language name, e.g. Danish")
    ap.add_argument("--model", required=True, help="aisuite model id (independent family!)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    src = [l.strip() for l in open(args.source) if l.strip()]
    out_path = Path(args.out)
    ckpt = out_path.with_suffix(".ckpt.json")
    done = {int(k): v for k, v in json.loads(ckpt.read_text()).items()} if ckpt.exists() else {}

    client = Client(args.model)
    for i, line in enumerate(src):
        if i in done:
            continue
        done[i] = " ".join(client.ask(PROMPT.format(language=args.language, line=line)).split())
        ckpt.write_text(json.dumps(done, ensure_ascii=False))
        if (i + 1) % 10 == 0:
            print(f"  {i + 1}/{len(src)}")
    out_path.write_text("\n".join(done[i] for i in range(len(src))) + "\n")
    print(f"wrote {out_path} ({len(src)} lines)")


if __name__ == "__main__":
    main()
