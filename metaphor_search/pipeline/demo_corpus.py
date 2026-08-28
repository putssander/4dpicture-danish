"""A public corpus to run the whole pipeline on, with known-good items hidden inside.

* the CC-licensed **#ReframeCovid collection** (community-collected COVID-19 metaphors;
  138 English, 34 Danish entries) — the "posts";
* the 17 published **Metaphor Menu** entries (Lancaster) — planted as check items, so the
  run can show whether known-good metaphors surface near the top.

Both may be quoted verbatim; nothing patient-derived is involved. The project's real
English evaluation used 600 Reddit posts, which cannot be redistributed.

    from pipeline import demo_corpus
    texts, plants = demo_corpus.build(language="English")
"""
import csv
import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"


def reframecovid(language="English"):
    rows = list(csv.reader(open(DATA / "reframecovid.csv", encoding="utf-8")))
    hdr_i = next(i for i, r in enumerate(rows) if "Language" in r)
    hdr = rows[hdr_i]
    out = {}
    for n, r in enumerate(rows[hdr_i + 1:]):
        d = dict(zip(hdr, r))
        if (d.get("Language") or "").strip() != language:
            continue
        text = (d.get("Example text or description of visual") or "").strip()
        if len(text.split()) < 6:
            continue
        out[f"reframe{n}"] = text
    return out


def menu():
    return {f"MENU_{i}": e["metaphor"] for i, e in enumerate(json.loads((DATA / "metaphor_menu.json").read_text(encoding="utf-8")))}


def build(language="English", plant_menu=True):
    """Returns (texts, planted_ids): the corpus as {doc_id: text}; planted ids start with 'MENU_'.
    Menu entries are planted only for English (they are English text)."""
    texts = reframecovid(language)
    plants = []
    if plant_menu and language == "English":
        m = menu(); texts.update(m); plants = sorted(m)
    return texts, plants
