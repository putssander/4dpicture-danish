"""Step 5 — sort the list.

Composite used in the project: tier first (0 = verify-keep AND experiential, 1 = keep only,
2 = verify-rejected), then menu-likeness score (high first), then register (vivid before
conventional). Nested duplicates within one passage ("a huge X closing in" / "X closing in")
collapse to the best-ranked member. Output `ranking.json`: one row per candidate with
rank, tier, score, flags, class (pool / menu / anchor / probe) and stratum — no text.
"""
import json
import re
from collections import defaultdict
from pathlib import Path

from .screens import load, out_path

CLS = {"MENU": "menu", "ANCHOR": "anchor", "PROBE": "probe"}


def cls_of(jid):
    parts = jid.split("|")
    if parts[0] != "PLANT":
        return "pool"
    return CLS.get(re.split(r"[_:]", parts[1])[0], "plant")


def stratum_of(jid):
    """Source label derived from the segment id: 'blogs_12_3' -> 'blogs'. Never text."""
    s = re.split(r"[_:]", jid.split("|")[1])[0]
    return s if re.match(r"^[A-Za-z0-9.-]+$", s) else "corpus"


def collapse_nested(records, phrase_of):
    by_seg = defaultdict(list)
    for r in records:
        by_seg["|".join(r["id"].split("|")[:2])].append(r)
    kept, dropped = [], 0
    for seg in sorted(by_seg):
        rows = sorted(by_seg[seg], key=lambda r: (r["tier"], -r["score"], not r["vivid"], len(phrase_of(r["id"])), r["id"]))
        chosen = []
        for r in rows:
            p = phrase_of(r["id"]).casefold()
            if any(p in c or c in p for c in chosen):
                dropped += 1
                continue
            chosen.append(p); kept.append(r)
    return kept, dropped


def run(work, models, exclude_plants=()):
    """models: {"verify": m, "register": m, "experiential": m, "score": m}.
    exclude_plants: planted Menu ids that were quoted inside the scoring prompt — they are
    not fair check items and are dropped before ranking (recorded in a sidecar)."""
    work = Path(work)
    jobs = json.loads((work / "screens" / "jobs.json").read_text(encoding="utf-8"))["jobs"]
    by_id = {j["id"]: j for j in jobs}
    verify = load(out_path(work, "verify", models["verify"]), "verdict")
    register = load(out_path(work, "register", models["register"]), "register")
    exper = load(out_path(work, "experiential", models["experiential"]), "experiential")
    score = load(out_path(work, "score", models["score"]), "score")
    records, seen = [], set()
    for j in jobs:
        jid = j["id"]
        if jid in seen:
            continue
        seen.add(jid)
        keep = verify.get(jid) == "keep"
        exp = exper.get(jid) is True
        vivid = register.get(jid) == "vivid"
        try:
            sc = float(score.get(jid))
        except (TypeError, ValueError):
            sc = 0.0
        records.append({"id": jid, "tier": 0 if (keep and exp) else (1 if keep else 2), "score": sc,
                        "vivid": vivid, "keep": keep, "exp": exp, "cls": cls_of(jid), "stratum": stratum_of(jid)})
    excl = set(exclude_plants)
    quoted = [r for r in records if r["cls"] == "menu" and r["id"].split("|")[1] in excl]
    records = [r for r in records if not (r["cls"] == "menu" and r["id"].split("|")[1] in excl)]
    (work / "excluded_quoted_plants.json").write_text(json.dumps(
        {"rule": "planted Menu entries quoted inside the scoring prompt are not considered",
         "entries": sorted({r["id"].split("|")[1] for r in quoted})}, ensure_ascii=False), encoding="utf-8")
    records.sort(key=lambda r: (r["tier"], -r["score"], not r["vivid"]))
    phrase_of = lambda jid: by_id.get(jid, {}).get("phrase") or jid.split("|")[-1]
    records, dropped = collapse_nested(records, phrase_of)
    records.sort(key=lambda r: (r["tier"], -r["score"], not r["vivid"]))
    for i, r in enumerate(records, 1):
        r["rank"] = i
    (work / "ranking.json").write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    return {"ranked": len(records), "nested_collapsed": dropped, "quoted_plants_dropped": len(quoted),
            "coverage": {"verify": len(verify), "register": len(register), "experiential": len(exper), "score": len(score)},
            "path": str(work / "ranking.json")}
