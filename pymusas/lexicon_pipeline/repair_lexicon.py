"""Deterministic repair of a translated single-word USAS lexicon (any language).

The release gate UCREL's review asked for, without the Danish-specific paths and the
optional LLM re-translation of `fix_lexicon_errors.py`:

  * duplicate (lemma, POS) rows  -> one row, tags merged in order of first appearance
  * multi-token lemmas            -> dropped (they belong in an MWE list, not here)
  * POS tokens as words / empty or 'nan' lemmas or tags -> dropped

    python repair_lexicon.py --lexicon semantic_lexicon_xx_open.tsv --out semantic_lexicon_xx_fixed.tsv
"""
import argparse
import csv
import json
from collections import OrderedDict
from pathlib import Path

POS_TOKENS = {"NOUN", "VERB", "ADJ", "ADV", "PRON", "DET", "ADP", "NUM", "CONJ", "CCONJ", "SCONJ",
              "PART", "INTJ", "PROPN", "AUX", "PUNCT", "SYM", "X"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lexicon", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", help="JSON report path (default: <out>.report.json)")
    a = ap.parse_args()
    rows = list(csv.reader(open(a.lexicon, encoding="utf-8"), delimiter="\t"))
    header, body = rows[0], rows[1:]
    li, pi, ti = header.index("lemma"), header.index("pos"), header.index("semantic_tags")
    counts = {"input": len(body), "multi_token": 0, "pos_token": 0, "empty_or_nan": 0, "duplicates_merged": 0}
    merged = OrderedDict()
    for r in body:
        if len(r) <= max(li, pi, ti):
            counts["empty_or_nan"] += 1; continue
        lemma, pos, tags = r[li].strip(), r[pi].strip(), r[ti].strip()
        if not lemma or not tags or lemma.lower() == "nan" or tags.lower() == "nan":
            counts["empty_or_nan"] += 1; continue
        if len(lemma.split()) > 1 or "_" in lemma:
            counts["multi_token"] += 1; continue
        if lemma.upper() in POS_TOKENS and lemma.isupper():
            counts["pos_token"] += 1; continue
        key = (lemma, pos)
        if key in merged:
            counts["duplicates_merged"] += 1
            seen = merged[key].split()
            merged[key] = " ".join(seen + [t for t in tags.split() if t not in seen])
        else:
            merged[key] = tags
    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["lemma", "pos", "semantic_tags"])
        for (lemma, pos), tags in merged.items():
            w.writerow([lemma, pos, tags])
    counts["output"] = len(merged)
    rep = Path(a.report or (str(out) + ".report.json"))
    rep.write_text(json.dumps(counts, indent=1), encoding="utf-8")
    print(json.dumps(counts))


if __name__ == "__main__":
    main()
