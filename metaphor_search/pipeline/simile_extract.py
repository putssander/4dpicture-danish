#!/usr/bin/env python3
"""Simile-marker extraction — the cheapest possible metaphor-finding arm.

Early in the project, explicit comparison markers were tried as a route to metaphor: find
"feels like" / "som en" and take what follows. The intuition is sound — a simile states the
comparison outright, so precision should be high — and the approach was set aside. This
measures it properly, on the same segments as the model-based arms, so the trade-off can be
quantified rather than recalled.

It needs no model, no GPU and no API: it is a regular expression. That makes it the floor
against which every more expensive method should be judged.

Markers are generous by design — this is the approach's best case, not a strawman.

PRIVACY: participant text stays on the box; stdout is counts only.

Usage:
  simile_extract.py --language en --segments /work/speech/eval/ranker_eval_2026/segments.json \\
      --extra-segments /work/speech/eval/ranker_eval_2026/planted/segments.json \\
      --out /work/speech/eval/ranker_eval_2026/screens_simile
  simile_extract.py --language da --segments /work/speech/eval/danish_t4/segments.json \\
      --extra-segments /work/speech/eval/metaphor_rerun_2026/segments.json \\
      --out /work/speech/eval/danish_simile
"""

import argparse
import json
import re
from pathlib import Path

MARKERS = {
    "en": [r"\bfeels?\s+like\b", r"\bfelt\s+like\b", r"\bit'?s\s+like\b", r"\bwas\s+like\b",
           r"\blike\s+(?:a|an|the|being|having|walking|running|carrying|drowning)\b",
           r"\bas\s+if\b", r"\bas\s+though\b", r"\bkind\s+of\s+like\b",
           r"\bsort\s+of\s+like\b", r"\bcompared\s+to\b", r"\breminds?\s+me\s+of\b",
           r"\bimagine\b"],
    # Danish: "som" is the workhorse comparison marker, plus the explicit feel/resemble verbs.
    # "som" alone is far too broad (relative pronoun, "such as"), so it is required to be
    # followed by an article or a verb of comparison.
    "da": [r"\bsom\s+(?:en|et|at|om|den|det)\b", r"\bligesom\b", r"\bf(?:ø|oe)les?\s+som\b",
           r"\bf(?:ø|oe)ltes\s+som\b", r"\bder\s+er\s+som\b", r"\bminder\s+om\b",
           r"\bsammenlignet\s+med\b", r"\bforestil\s+dig\b", r"\bp(?:å|aa)\s+en\s+m(?:å|aa)de\b",
           r"\ben\s+slags\b"],
    "nl": [r"\bvoelt\s+als\b", r"\bals\s+(?:een|het)\b", r"\bnet\s+als\b", r"\balsof\b",
           r"\bdoet\s+denken\s+aan\b", r"\bvergeleken\s+met\b", r"\been\s+soort\b"],
}
STOP = {"en": r"[.!?;,]|\band\b|\bbut\b",
        "da": r"[.!?;,]|\bog\b|\bmen\b",
        "nl": r"[.!?;,]|\ben\b|\bmaar\b"}

ap = argparse.ArgumentParser()
ap.add_argument("--language", required=True, choices=sorted(MARKERS))
ap.add_argument("--segments", required=True)
ap.add_argument("--extra-segments", default="")
ap.add_argument("--out", required=True)
A = ap.parse_args()

PAT = re.compile("|".join(MARKERS[A.language]), re.IGNORECASE)
CUT = re.compile(STOP[A.language], re.IGNORECASE)

segs = {s[0]: s[1] for s in json.loads(
    Path(A.segments).read_text(encoding="utf-8"))["segments"]}
if A.extra_segments and Path(A.extra_segments).exists():
    segs.update({s[0]: s[1] for s in json.loads(
        Path(A.extra_segments).read_text(encoding="utf-8"))["segments"]})

out = Path(A.out)
out.mkdir(parents=True, exist_ok=True)

jobs, seen, hit_segments = [], set(), 0
for sid, text in sorted(segs.items()):
    found = False
    for m in PAT.finditer(text):
        found = True
        rest = text[m.start():m.start() + 120]
        after = rest[len(m.group(0)):]
        c = CUT.search(after)
        phrase = rest[:len(m.group(0)) + (c.start() if c else 60)].strip()
        if len(phrase.split()) < 3:
            continue
        jid = f"SIMILE|{sid}|{phrase[:60]}"
        if jid in seen:
            continue
        seen.add(jid)
        jobs.append({"id": jid, "text": text[:1200], "phrase": phrase})
    if found:
        hit_segments += 1

(out / "jobs.json").write_text(json.dumps({"jobs": jobs}, ensure_ascii=False), encoding="utf-8")
print(json.dumps({
    "language": A.language,
    "segments_searched": len(segs),
    "segments_with_a_marker": hit_segments,
    "pct_segments_with_marker": round(100 * hit_segments / max(1, len(segs)), 1),
    "candidates": len(jobs),
    "path": str(out / "jobs.json")}, indent=1))
