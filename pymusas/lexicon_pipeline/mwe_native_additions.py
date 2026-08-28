#!/usr/bin/env python3
"""Native MWE additions: extract target-language multiword entries from a kaikki
extract and tag them from their ENGLISH glosses via the hand-built English USAS
lexicon (majority tag over gloss content words). No LLM, fully local — the MWE
analogue of the measured single-word Wiktionary lever: idioms must be ADDED from
native inventories, not translated.

  python scripts/mwe_native_additions.py --kaikki kaikki-da.jsonl.gz \
      --spacy-model da_core_news_sm --out lexicons/da/mwe_da_native.tsv
"""
import argparse, gzip, json, re
from collections import Counter
from pathlib import Path

EN_LEX = "https://raw.githubusercontent.com/UCREL/Multilingual-USAS/master/English/semantic_lexicon_en.tsv"
STOP = set("a an the of to in on for with and or be is are was has have it its as by at that this".split())

def en_tag_index():
    import urllib.request
    idx = {}
    for line in urllib.request.urlopen(EN_LEX).read().decode().splitlines()[1:]:
        p = line.split("\t")
        if len(p) >= 3:
            idx.setdefault(p[0].lower(), p[2].split()[0])
    return idx

def bare(code):
    m = re.match(r"^([A-Z]+\d*(?:\.\d+)*)", str(code).split("/")[0])
    return m.group(1) if m else ""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kaikki", required=True)
    ap.add_argument("--spacy-model", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    import spacy
    nlp = spacy.load(args.spacy_model, exclude=["ner", "parser", "lemmatizer"])
    en_idx = en_tag_index()
    out, skipped = [], 0
    for line in gzip.open(args.kaikki, "rt"):
        e = json.loads(line)
        w = e.get("word", "")
        if " " not in w or len(w.split()) > 6:
            continue
        glosses = [g for s in e.get("senses", []) for g in (s.get("glosses") or [])]
        votes = Counter()
        for g in glosses[:3]:
            for tok in re.findall(r"[a-zA-Z']+", g.lower()):
                if tok in STOP: continue
                t = en_idx.get(tok)
                if t: votes[bare(t)] += 1
        if not votes:
            skipped += 1; continue
        tag = votes.most_common(1)[0][0]
        # build the MWE template: token_POS per token (spaCy POS, upper)
        doc = nlp(w)
        tmpl = " ".join(f"{t.text}_{t.pos_}" for t in doc if not t.is_space)
        out.append(f"{tmpl}\t{tag}")
    Path(args.out).write_text("mwe_template\tsemantic_tags\n" + "\n".join(out) + "\n")
    print(f"{len(out)} native MWE templates written ({skipped} skipped, no gloss votes)")

if __name__ == "__main__":
    main()
