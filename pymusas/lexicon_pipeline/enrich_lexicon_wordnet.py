#!/usr/bin/env python3
"""Open-resource lexicon enrichment from WordNets (Open Multilingual Wordnet).

Same mechanism as enrich_lexicon_wiktionary.py — for every entry of the ENGLISH
source lexicon (lemma, POS, USAS tags), collect target-language equivalents and
add (equivalent, POS, same tags) entries — but sourced from the target
language's WordNet instead of Wiktionary translations. Equivalence is
synset-level: an English lemma and a target lemma are equivalents iff they
belong to synsets linked by the same ILI (interlingual index), i.e. the same
concept in Princeton WordNet 3.0. The procedure never sees any evaluation
corpus; it is a general, resource-driven expansion, reportable as a ladder rung.

WordNet sources (all open):
  omw-da:1.4  DanNet             (license: wordnet/DanNet, open with attribution)
  omw-nl:1.4  Open Dutch WordNet (CC BY-SA 4.0)
  omw-fi:1.4  FinnWordNet        (CC BY 4.0)
  omw-en:1.4  Princeton WordNet 3.0 (wordnet license) — the English pivot

Setup:  pip install wn && python -m wn download omw-en:1.4 omw-da:1.4 ...

Example:
  python enrich_lexicon_wordnet.py --wordnet omw-da:1.4 \
      --base data/semantic_lexicon_dan_qwen_wiki.tsv \
      --out data/semantic_lexicon_dan_open_wn.tsv
"""

import argparse
from collections import defaultdict
from pathlib import Path

# WordNet synset POS -> the coarse POS values used in the Multilingual-USAS TSVs
POS_MAP = {"n": "noun", "v": "verb", "a": "adj", "s": "adj", "r": "adv"}


def load_equivalents(target_spec, english_spec):
    """english lemma(lower) -> pos -> set of target-language lemmas (single words)."""
    import wn
    en = wn.Wordnet(english_spec)
    tgt = wn.Wordnet(target_spec)

    def ili_id(ss):
        ili = ss.ili
        if ili is None:
            return None
        return ili if isinstance(ili, str) else ili.id

    # ILI -> English member lemmas
    en_by_ili = defaultdict(set)
    for ss in en.synsets():
        ili = ili_id(ss)
        if ili is None:
            continue
        pos = POS_MAP.get(ss.pos)
        if not pos:
            continue
        for lemma in ss.lemmas():
            w = lemma.strip().lower()
            if w and " " not in w and "_" not in w:
                en_by_ili[ili].add((w, pos))

    eq = defaultdict(lambda: defaultdict(set))
    n_syn, n_pairs = 0, 0
    for ss in tgt.synsets():
        ili = ili_id(ss)
        if ili is None or ili not in en_by_ili:
            continue
        pos = POS_MAP.get(ss.pos)
        if not pos:
            continue
        n_syn += 1
        tgt_words = set()
        for lemma in ss.lemmas():
            w = lemma.strip().lower()
            # single words only — MWEs are a separate lexicon with template syntax
            if w and " " not in w and "_" not in w and (w.replace("-", "").isalpha()):
                tgt_words.add(w)
        for ew, epos in en_by_ili[ili]:
            if epos != pos:
                continue
            for tw in tgt_words:
                eq[ew][pos].add(tw)
                n_pairs += 1
    print(f"{target_spec}: {n_syn} ILI-linked synsets -> "
          f"{sum(len(p) for p in eq.values())} english lemma+pos with equivalents "
          f"({n_pairs} pairs)")
    return eq


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--wordnet", required=True, help="target wn spec, e.g. omw-da:1.4")
    ap.add_argument("--english-wordnet", default="omw-en:1.4", help="English pivot wn spec")
    ap.add_argument("--base", required=True, help="existing target-language lexicon TSV to enrich")
    ap.add_argument("--english", default=str(Path(__file__).parent / "data/semantic_lexicon_en.tsv"),
                    help="English source lexicon (lemma, POS, tags)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--lemma-new-only", action="store_true",
                    help="add only lemmas the base lexicon has never seen under ANY "
                         "POS. Safe mode for enriching a strong (hand-built) base: "
                         "same-lemma/other-POS additions intercept the tagger's "
                         "POS-insensitive fallback on POS-tagging errors and can "
                         "replace superior native entries (measured: -6 pts on the "
                         "hand-built Finnish lexicon without this flag).")
    ap.add_argument("--pos-out", default="",
                    help="write added entries' POS in the BASE lexicon's scheme, "
                         "e.g. 'noun=Noun,verb=Verb,adj=Adjective,adv=Adverb'. "
                         "Without this, additions carry the English lexicon's POS "
                         "strings — correct for lexicons built by this pipeline, "
                         "WRONG for site lexicons with their own POS scheme "
                         "(mismatched entries shadow native ones via lookup "
                         "fallbacks and can reduce accuracy).")
    args = ap.parse_args()
    pos_out = dict(kv.split("=") for kv in args.pos_out.split(",")) if args.pos_out else {}

    eq = load_equivalents(args.wordnet, args.english_wordnet)

    base_lines = Path(args.base).read_text(encoding="utf-8").splitlines()
    header, base_rows = base_lines[0], base_lines[1:]
    existing, existing_lemmas = set(), set()
    for row in base_rows:
        parts = row.split("\t")
        if len(parts) >= 2:
            existing.add((parts[0].lower(), parts[1].lower()))
            existing_lemmas.add(parts[0].lower())

    added, seen_new = [], set()
    n_en = 0
    for row in Path(args.english).read_text(encoding="utf-8").splitlines()[1:]:
        parts = row.split("\t")
        if len(parts) < 3:
            continue
        lemma, pos, tags = parts[0].lower(), parts[1].lower(), parts[2]
        n_en += 1
        for w in sorted(eq.get(lemma, {}).get(pos, ())):
            key = (w, pos)
            if key in existing or key in seen_new:
                continue        # existing entries win; the wordnet only ADDS
            if args.lemma_new_only and w in existing_lemmas:
                continue
            seen_new.add(key)
            added.append(f"{w}\t{pos_out.get(pos, parts[1])}\t{tags}")

    out = Path(args.out)
    out.write_text("\n".join([header] + base_rows + added) + "\n", encoding="utf-8")
    print(f"{args.base}: {len(base_rows)} entries "
          f"+ {len(added)} wordnet additions -> {out} "
          f"({len(base_rows) + len(added)} total; EN source rows scanned: {n_en})")


if __name__ == "__main__":
    main()
