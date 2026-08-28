#!/usr/bin/env python3
"""Open-resource lexicon enrichment — the measured version of the pipeline's
"approach 3" (open-dictionary lookups), applied to the single-word lexicon.

Mechanism: for every entry of the ENGLISH source lexicon (lemma, POS, USAS tags),
collect the target-language translations that the English Wiktionary lists for that
lemma+POS, and add (translation, POS, same tags) entries. This is the same
word-by-word tag transfer as the MT rungs, but sourced from a human-curated open
dictionary instead of a translator — so it adds equivalents (and native synonyms)
the translator never produces. The procedure never sees any evaluation corpus:
it is a general, resource-driven expansion, reportable as a ladder rung.

Input: a kaikki.org wiktextract JSONL of the English Wiktionary (each line one
word entry with optional "translations": [{"code": "da", "word": ...}, ...]).

Example:
  python enrich_lexicon_wiktionary.py --kaikki kaikki-en.jsonl.gz \
      --base data/semantic_lexicon_dan_qwen.tsv --lang-code da \
      --out data/semantic_lexicon_dan_qwen_wiki.tsv
"""

import argparse
import gzip
import json
from collections import defaultdict
from pathlib import Path

# wiktextract POS -> the coarse POS values used in the Multilingual-USAS TSVs
POS_MAP = {"noun": "noun", "verb": "verb", "adj": "adj", "adv": "adv",
           "prep": "prep", "conj": "conj", "pron": "pron", "det": "det",
           "num": "num", "intj": "intj"}


def load_translations(kaikki_path, lang_code):
    """lemma(lower) -> pos -> set of target-language translations (single words)."""
    tr = defaultdict(lambda: defaultdict(set))
    opener = gzip.open if str(kaikki_path).endswith(".gz") else open
    n_lines = 0
    with opener(kaikki_path, "rt", encoding="utf-8") as fh:
        for line in fh:
            n_lines += 1
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            pos = POS_MAP.get(e.get("pos", ""))
            word = e.get("word", "").lower()
            if not pos or not word:
                continue
            # kaikki puts most translations under senses[].translations,
            # some at the entry top level — read both
            buckets = [e.get("translations") or []]
            buckets += [s.get("translations") or [] for s in e.get("senses", []) or []]
            for bucket in buckets:
                for t in bucket:
                    if t.get("code") != lang_code:
                        continue
                    w = (t.get("word") or "").strip()
                    # single words only — MWEs are a separate lexicon with template syntax
                    if w and " " not in w and (w.isalpha() or "-" in w):
                        tr[word][pos].add(w.lower())
    print(f"scanned {n_lines} wiktionary entries; "
          f"{sum(len(p) for p in tr.values())} lemma+pos with {lang_code} translations")
    return tr


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--kaikki", required=True, help="kaikki.org English extract (.jsonl[.gz])")
    ap.add_argument("--base", required=True, help="existing target-language lexicon TSV to enrich")
    ap.add_argument("--english", default=str(Path(__file__).parent / "data/semantic_lexicon_en.tsv"),
                    help="English source lexicon (lemma, POS, tags)")
    ap.add_argument("--lang-code", required=True, help="wiktionary language code, e.g. da, nl")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    tr = load_translations(args.kaikki, args.lang_code)

    base_lines = Path(args.base).read_text(encoding="utf-8").splitlines()
    header, base_rows = base_lines[0], base_lines[1:]
    existing = set()
    for row in base_rows:
        parts = row.split("\t")
        if len(parts) >= 2:
            existing.add((parts[0].lower(), parts[1].lower()))

    added, seen_new = [], set()
    n_en = 0
    for row in Path(args.english).read_text(encoding="utf-8").splitlines()[1:]:
        parts = row.split("\t")
        if len(parts) < 3:
            continue
        lemma, pos, tags = parts[0].lower(), parts[1].lower(), parts[2]
        n_en += 1
        for w in tr.get(lemma, {}).get(pos, ()):
            key = (w, pos)
            if key in existing or key in seen_new:
                continue        # keep the translator's entry; wiktionary only ADDS
            seen_new.add(key)
            added.append(f"{w}\t{parts[1]}\t{tags}")

    out = Path(args.out)
    out.write_text("\n".join([header] + base_rows + added) + "\n", encoding="utf-8")
    print(f"{args.base}: {len(base_rows)} entries "
          f"+ {len(added)} wiktionary additions -> {out} "
          f"({len(base_rows) + len(added)} total; EN source rows scanned: {n_en})")


if __name__ == "__main__":
    main()
