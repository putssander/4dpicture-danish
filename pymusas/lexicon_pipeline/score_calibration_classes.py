"""Calibration card: how good are the committee's labels, measured on human gold?

Scores the saved API answers in data/calibration/ against the USAS-WSD human gold in
data/usas_wsd/ — offline, no API key. Prints, per language: each annotator alone, and the
precision of every committee label class (all three agree / two agree / all differ →
strongest annotator) plus the combined reference. Run:  python score_calibration_classes.py
"""
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from usas_wsd import load_usas_wsd, score_predictions, sentences  # noqa: E402

MODELS = ["fable", "gpt56", "gemini"]          # strongest first: settles all-differ tokens


def calibration_card(lang):
    rows = load_usas_wsd(lang)
    sents = sentences(rows)
    ans = {m: json.loads((HERE / "data/calibration" / f"{m}_calib_{lang}_answers_api.json")
                         .read_text()) for m in MODELS}
    flat = [(r, {m: ans[m].get(str(si), {}).get(str(ti), "") for m in MODELS})
            for si, sent in enumerate(sents, 1) for ti, r in enumerate(sent, 1)]
    rows_all = [r for r, _ in flat]

    def acc(pairs, level=None):
        return score_predictions([r for r, _ in pairs], [[p] for _, p in pairs], level=level) * 100

    print(f"\n=== {lang}: {len(sents)} sentences, {len(flat)} labelled tokens (human gold)")
    for m in MODELS:
        pairs = [(r, c[m]) for r, c in flat]
        print(f"  {m:7s} alone: exact {acc(pairs):5.1f}   level-1 {acc(pairs, 1):5.1f}")
    cls = {"all three agree": [], "two agree (majority)": [], "all differ -> strongest": []}
    for r, c in flat:
        codes = [c[m] for m in MODELS]
        nonempty = [x for x in codes if x]
        if not nonempty:
            continue
        if len(set(nonempty)) == 1 and len(nonempty) == 3:
            cls["all three agree"].append((r, nonempty[0]))
        else:
            top, k = Counter(nonempty).most_common(1)[0]
            (cls["two agree (majority)"] if k >= 2 else cls["all differ -> strongest"]).append(
                (r, top if k >= 2 else nonempty[0]))
    for name, pairs in cls.items():
        print(f"  {name:25s} {len(pairs)/len(flat)*100:5.1f}% of tokens  "
              f"precision exact {acc(pairs):5.1f}   level-1 {acc(pairs, 1):5.1f}")
    allp = [x for v in cls.values() for x in v]
    print(f"  combined reference (all classes): exact {acc(allp):5.1f}")


if __name__ == "__main__":
    for lang in ("fin", "eng"):
        calibration_card(lang)
    print("\nReading: unanimous labels are near human quality; majority and single-model labels are"
          " not. Report scores on unanimous tokens as the primary comparison.")
