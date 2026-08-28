#!/usr/bin/env python3
"""Translate the English USAS single-word lexicon into a target language with an LLM.

Emulates the project's original Danish lexicon construction (translate every English
lemma, carry pos and semantic_tags over unchanged, merge collisions) so that different
translators are comparable rungs on one evaluation ladder:

  Google Translate (original, via notebooks/translate_tsv.ipynb)   <- Phase A
  gpt-5-mini / frontier API models                                 <- Phase B (closed)
  Qwen/other open models on local GPU via an OpenAI-compatible     <- Phase B (open)
  endpoint (vLLM, Ollama)

Every run uses the identical prompt, batching, and merge logic; only --model and
--base-url change, so accuracy differences on the USAS-WSD gold are attributable to the
translator alone.

Examples:
  # OpenAI API
  OPENAI_API_KEY=... python translate_lexicon.py --target Finnish --code fin --model gpt-5-mini
  # Qwen on a local B200 via vLLM (OpenAI-compatible server)
  python translate_lexicon.py --target Finnish --code fin \\
      --model Qwen/Qwen3.6-235B-A22B --base-url http://localhost:8000/v1 --api-key none
  # Danish, open pipeline
  python translate_lexicon.py --target Danish --code dan \\
      --model Qwen/Qwen3.6-235B-A22B --base-url http://gpu-node:8000/v1 --api-key none

Output: data/semantic_lexicon_<code>_<model>.tsv (PyMUSAS format) + a resumable
checkpoint. Evaluate with:
  python run_usas_wsd_eval.py --language fin --system rule \\
      --single-lexicon data/semantic_lexicon_fin_<model>.tsv --spacy-model fi_core_news_sm
"""

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

EVALS = Path(__file__).resolve().parent
SRC = EVALS / "data/semantic_lexicon_en.tsv"
SRC_URL = ("https://raw.githubusercontent.com/UCREL/Multilingual-USAS/master/"
           "English/semantic_lexicon_en.tsv")

PROMPT = (
    "Translate each English word to its single most common {target} equivalent, as a "
    "dictionary-form lemma (base/citation form). One {target} word per input word; no "
    "explanations. If there is no reasonable single-word {target} equivalent, output an "
    "empty string.\n"
    "Input lines are: id<TAB>word<TAB>part-of-speech.\n"
    "Return ONLY a JSON object mapping id to the {target} word, e.g. {{\"12\": \"...\"}}.\n\n"
    "{words}")

# S2 rung — sense-aware translation: the entry's USAS semantic fields disambiguate which
# sense of the English word to translate (the project's "translate within context" step).
PROMPT_TAGS = (
    "Translate each English word to its single most common {target} equivalent IN THE "
    "GIVEN SEMANTIC FIELD, as a dictionary-form lemma. Each input line is: "
    "id<TAB>word<TAB>part-of-speech<TAB>semantic field(s) of this sense of the word. "
    "Choose the {target} word that belongs to those semantic fields — if the English word "
    "is ambiguous, the fields tell you which sense is meant. One {target} word per line; "
    "empty string if no reasonable single-word equivalent exists.\n"
    "Return ONLY a JSON object mapping id to the {target} word, e.g. {{\"12\": \"...\"}}.\n\n"
    "{words}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--target", required=True, help="target language name, e.g. Finnish")
    ap.add_argument("--code", required=True, help="ISO 639-3 code for filenames, e.g. fin")
    ap.add_argument("--model", required=True)
    ap.add_argument("--base-url", help="OpenAI-compatible endpoint (vLLM/Ollama); "
                                       "default: api.openai.com")
    ap.add_argument("--api-key", help="key for the endpoint (default: env OPENAI_API_KEY)")
    ap.add_argument("--batch-size", type=int, default=150)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, help="translate only the first N entries (smoke)")
    ap.add_argument("--multi", action="store_true",
                    help="coverage rung: up to 3 target equivalents per English entry, "
                         "each becoming its own lexicon entry")
    ap.add_argument("--with-tags", action="store_true",
                    help="S2 rung: include each entry's USAS field descriptions so the "
                         "translator picks the sense-appropriate word")
    args = ap.parse_args()

    from openai import OpenAI
    kw = {}
    if args.base_url:
        kw["base_url"] = args.base_url
    if args.api_key:
        kw["api_key"] = args.api_key
    client = OpenAI(**kw)

    if not SRC.exists():
        import urllib.request
        SRC.parent.mkdir(parents=True, exist_ok=True)
        SRC.write_bytes(urllib.request.urlopen(SRC_URL).read())

    entries = []
    for i, line in enumerate(SRC.read_text().splitlines()):
        if i == 0:
            continue
        parts = line.split("\t")
        if len(parts) >= 3:
            entries.append((parts[0], parts[1], parts[2]))
    if args.limit:
        entries = entries[: args.limit]

    tag_desc = {}
    if args.with_tags:
        tags_path = EVALS / "data/usas_tags.json"
        tag_desc = json.loads(tags_path.read_text())

    slug = re.sub(r"[^A-Za-z0-9.-]+", "_", args.model) \
        + ("_ctx" if args.with_tags else "") + ("_multi" if args.multi else "")
    out_path = EVALS / f"data/semantic_lexicon_{args.code}_{slug}.tsv"
    ckpt_path = EVALS / f"data/ckpt_{args.code}_{slug}.jsonl"
    print(f"{len(entries)} entries -> {out_path.name} via {args.model} "
          f"@ {args.base_url or 'api.openai.com'}", flush=True)

    done = {}
    if ckpt_path.exists():
        for line in ckpt_path.read_text().splitlines():
            try:
                r = json.loads(line)
                done[r["i"]] = r["t"]
            except Exception:
                pass
        print(f"resuming: {len(done)} already translated", flush=True)

    def translate_batch(start):
        batch = entries[start:start + args.batch_size]
        if args.with_tags:
            def describe(tags):
                out = []
                for t in str(tags).split()[:3]:
                    code = re.match(r"[A-Z]\d*(?:\.\d+)*", t.split("/")[0])
                    if code and code.group(0) in tag_desc:
                        out.append(tag_desc[code.group(0)])
                return "; ".join(out) or "general"
            words = "\n".join(f"{start+j}\t{w}\t{pos}\t{describe(tg)}"
                               for j, (w, pos, tg) in enumerate(batch))
            prompt = PROMPT_TAGS.format(target=args.target, words=words)
        else:
            words = "\n".join(f"{start+j}\t{w}\t{pos}" for j, (w, pos, _) in enumerate(batch))
            if args.multi:
                prompt = PROMPT.format(target=args.target, words=words).replace(
                    "its single most common {t} equivalent, as a "
                    "dictionary-form lemma (base/citation form). One {t} word per input "
                    "word".format(t=args.target),
                    "up to THREE common single-word {t} equivalents (synonyms or the "
                    "translations of its different senses), as dictionary-form lemmas, "
                    "separated by commas".format(t=args.target))
            else:
                prompt = PROMPT.format(target=args.target, words=words)
        for attempt in range(4):
            try:
                kw = {}
                if args.base_url:
                    # self-hosted (vLLM): disable Qwen-style thinking preambles
                    kw["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
                r = client.chat.completions.create(
                    model=args.model, messages=[{"role": "user", "content": prompt}], **kw)
                text = r.choices[0].message.content or ""
                # take the LAST parseable flat JSON object (reasoning text may precede it
                # and may itself contain braces)
                parsed = None
                for m in reversed(list(re.finditer(r"\{[^{}]*\}", text, re.S))):
                    try:
                        parsed = json.loads(m.group(0))
                        break
                    except json.JSONDecodeError:
                        continue
                if parsed is None:
                    raise ValueError(f"no parseable JSON in response ({text[:80]!r})")
                return {int(k): (", ".join(str(x) for x in v) if isinstance(v, list)
                                 else str(v)).strip() for k, v in parsed.items()}
            except Exception as e:
                time.sleep(3 * (attempt + 1))
                if attempt == 3:
                    print(f"batch {start} FAILED: {e}", file=sys.stderr, flush=True)
        return {}

    starts = [s for s in range(0, len(entries), args.batch_size)
              if not all((s + j) in done
                         for j in range(min(args.batch_size, len(entries) - s)))]
    ck = ckpt_path.open("a")
    completed = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(translate_batch, s): s for s in starts}
        for fut in as_completed(futs):
            for i, t in fut.result().items():
                if 0 <= i < len(entries):
                    done[i] = t
                    ck.write(json.dumps({"i": i, "t": t}) + "\n")
            ck.flush()
            completed += 1
            if completed % 20 == 0:
                print(f"{completed}/{len(starts)} batches ({len(done)} words)", flush=True)
    ck.close()

    merged = {}
    n_dropped = 0
    for i, (w, pos, tags) in enumerate(entries):
        raw = done.get(i, "").strip()
        cands = [c.strip() for c in raw.split(",")] if args.multi else [raw]
        cands = [c for c in cands if c and " " not in c]
        if not cands:
            n_dropped += 1
            continue
        for t in cands[:3]:
            key = (t.lower(), pos)
            merged.setdefault(key, [])
            for tag in tags.split():
                if tag not in merged[key]:
                    merged[key].append(tag)

    with out_path.open("w") as f:
        f.write("lemma\tpos\tsemantic_tags\n")
        for (t, pos), tags in merged.items():
            f.write(f"{t}\t{pos}\t{' '.join(tags)}\n")
    print(f"wrote {out_path}: {len(merged)} entries ({n_dropped} dropped)", flush=True)


if __name__ == "__main__":
    main()
