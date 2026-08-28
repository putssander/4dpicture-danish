#!/usr/bin/env python3
"""Validate (and optionally repair) MWE-template syntax, per upstream UCREL feedback.

When the Danish lexicons were merged into the official Multilingual-USAS repository,
UCREL's review removed 127 of 17,977 MWE entries for template-syntax issues and repaired
17 more. This validator encodes those exact categories so the same filtering is
reproducible in-repo and can be applied to any future lexicon (Danish v2, Dutch, ...):

  B1  bare POS-alternation slot        *_NOUN a_DET ADJ/INTJ *_NOUN
      (a POS alternation must be wrapped in curly braces: {ADJ/INTJ})
  B2  square brackets around a slot    hvert_DET andet_ADJ [egennavn_PROPN]
                                       binde_VERB [pron/ADV/Np] over_ADV
                                       East_PROPN [Name]_PROPN 6th_ADJ ...
  B3  POS tag in token position        ulykkesudsat_ADJ noun_NOUN   |   NUM_ADJ hundrede_NUM
      (extends the existing POS-as-token check to lower/mixed case; Danish words that
      merely spell a POS name — det, art — are whitelisted)
  B4  too many underscores in a slot   Undervisnings_NOUN-_PUNCT ...   |   B_*_X og_CCONJ Q_*_X
  B5  missing POS tag                  7_NUM & C_PROPN   |   Kommandør_PROPN *
      (repairable: a bare * becomes *_*; other bare tokens get _* appended)

Usage:
  python validate_mwe_syntax.py LEXICON.tsv                 # report only
  python validate_mwe_syntax.py LEXICON.tsv --fix OUT.tsv   # drop B1-B4, repair B5
"""

import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path

# Upstream POS tagset used in MWE templates (USAS core / UPOS-style)
POS_TAGS = {"NOUN", "VERB", "ADJ", "ADV", "PRON", "DET", "ADP", "NUM", "CCONJ", "SCONJ",
            "CONJ", "INTJ", "PART", "PROPN", "PUNCT", "SYM", "X", "AUX", "PREP", "ART"}
CURLY_RE = re.compile(r"\{[^}]*\}")
TOKEN_RE = re.compile(r"^[^_]+_[^_]+$")
# Danish words that legitimately spell a POS-tag name and must not be flagged as B3
DANISH_WHITELIST = {"det", "art"}
SYMBOL_POS = {"&": "PUNCT", "+": "SYM", "%": "SYM", "=": "SYM"}


def analyse_template(template):
    """Return the list of error codes for one MWE template."""
    errors = []
    t = str(template).strip()
    if "\n" in t or "\t" in t:
        return ["B6_malformed_row"]
    if t.lower() == "nan" or not t:
        return ["B7_nan_or_empty"]
    if "[" in t or "]" in t:
        errors.append("B2_square_brackets")
    # remove legal curly-brace alternations before slot-level checks
    stripped = CURLY_RE.sub("", t)
    for slot in stripped.split():
        n_underscores = slot.count("_")
        if n_underscores == 0:
            if "/" in slot and all(p.upper() in POS_TAGS or p == "*"
                                   for p in slot.split("/")):
                errors.append("B1_bare_pos_alternation")
            else:
                errors.append("B5_missing_pos")
        elif n_underscores > 1:
            # legal: token containing underscore is not expected in these lexicons
            errors.append("B4_extra_underscores")
        else:
            token, _, pos = slot.partition("_")
            if token == "*":
                continue
            # uppercase POS literally used as token (NOUN_NOUN, NUM_ADJ) or an English
            # lowercase POS name as token (noun_NOUN) — but not real Danish words (det, art)
            if (token in POS_TAGS) or (
                    token.lower() in {p.lower() for p in POS_TAGS}
                    and token.lower() not in DANISH_WHITELIST):
                errors.append("B3_pos_in_token_position")
            elif "/" in pos and not pos.startswith("{"):
                # POS alternation must use curly braces ({ADJ/INTJ}), not a bare slash
                errors.append("B1_bare_pos_alternation")
    return errors


def repair_template(template):
    """Repair B5 errors the way upstream did.

    Most 'missing POS' slots are actually a token FUSED with its POS tag (the underscore
    was lost): 'PART -> '_PART, *PROPN -> *_PROPN. Symbols get their real POS (& ->
    &_PUNCT); a bare * becomes *_*; anything else gets a wildcard POS appended.
    """
    out = []
    t = str(template).strip()
    protected = {}
    for i, m in enumerate(CURLY_RE.finditer(t)):
        protected[f"\x00{i}\x00"] = m.group(0)
        t = t.replace(m.group(0), f"\x00{i}\x00", 1)
    for slot in t.split():
        if slot in protected:
            out.append(protected[slot])
        elif "_" not in slot:
            fused = next((pos for pos in sorted(POS_TAGS, key=len, reverse=True)
                          if slot.endswith(pos) and len(slot) > len(pos)), None)
            if slot == "*":
                out.append("*_*")
            elif slot in SYMBOL_POS:
                out.append(f"{slot}_{SYMBOL_POS[slot]}")
            elif fused:
                out.append(f"{slot[:-len(fused)]}_{fused}")
            else:
                out.append(f"{slot}_*")
        else:
            out.append(slot)
    return " ".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("lexicon", help="MWE lexicon TSV (mwe_template <tab> semantic_tags)")
    ap.add_argument("--fix", metavar="OUT",
                    help="write a cleaned lexicon: drop B1-B4 entries, repair B5")
    args = ap.parse_args()

    rows = []
    with open(args.lexicon, newline="", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        header = next(reader)
        tpl_col = 0
        for i, name in enumerate(header):
            if "template" in name.lower():
                tpl_col = i
        for row in reader:
            if not row or len(row) <= tpl_col:
                continue
            # recover rows corrupted by an embedded newline (a quoted multi-line field):
            # split into the individual template<TAB>tags lines they contain
            if "\n" in row[tpl_col]:
                for part in row[tpl_col].split("\n"):
                    bits = part.strip().strip('"').replace('""', '"').split("\t")
                    if bits and bits[0]:
                        rows.append(bits + row[tpl_col + 1:] if len(bits) == 1 else bits)
                continue
            rows.append(row)

    counts = Counter()
    flagged = {}
    for i, row in enumerate(rows):
        errs = analyse_template(row[tpl_col])
        if errs:
            flagged[i] = errs
            for e in set(errs):
                counts[e] += 1

    print(f"{args.lexicon}: {len(rows)} entries, {len(flagged)} flagged")
    for code, n in sorted(counts.items()):
        print(f"  {code:<28} {n}")
    examples = {}
    for i, errs in flagged.items():
        for e in errs:
            examples.setdefault(e, rows[i][tpl_col])
    for e, ex in sorted(examples.items()):
        print(f"  e.g. {e}: {ex!r}")

    if args.fix:
        kept, dropped, repaired = [], 0, 0
        for i, row in enumerate(rows):
            errs = set(flagged.get(i, []))
            if errs - {"B5_missing_pos"}:  # B1-B4, B6, B7 -> drop (as upstream did)
                dropped += 1
                continue
            if "B5_missing_pos" in errs:
                row = list(row)
                row[tpl_col] = repair_template(row[tpl_col])
                repaired += 1
            kept.append(row)
        with open(args.fix, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter="\t")
            w.writerow(header)
            w.writerows(kept)
        print(f"wrote {args.fix}: kept {len(kept)}, dropped {dropped}, repaired {repaired}")

    return 1 if flagged and not args.fix else 0


if __name__ == "__main__":
    sys.exit(main())
