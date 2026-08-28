"""Step 3 — keep only what BOTH model families found.

A candidate from model A counts when model B proposed, in the same passage, a phrase that
contains it or is contained by it (case-insensitive). Nested spans are agreement; exact
wording is not required. Surviving candidates become screening jobs
`screens/jobs.json`: {"id": "<tier>|<segment>|<phrase>", "phrase", "text"}.

Planted check items (published Menu entries) get tier "PLANT" and a class in their
segment id (MENU_n); everything mined from the corpus is tier "POOL".
"""
import json
from pathlib import Path

from .mine import ckpt_path, load_checkpoint
from .segment import load as load_segments


def _match(p, others):
    p = p.casefold().strip()
    return any(p in o or o in p for o in others)


def run(work, models, plant_prefix="PLANT"):
    work = Path(work)
    segs = dict(load_segments(work / "segments.json"))
    arms = {m: load_checkpoint(ckpt_path(work, m)) for m in models}
    jobs, seen = [], set()
    n_raw = 0
    for sid, text in segs.items():
        per_model = {m: [c["phrase"] for c in arms[m].get(sid, [])] for m in models}
        n_raw += sum(len(v) for v in per_model.values())
        for m in models:
            others = [o.casefold().strip() for om in models if om != m for o in per_model[om]]
            for phrase in per_model[m]:
                if len(models) > 1 and not _match(phrase, others):
                    continue
                key = (sid, phrase.casefold().strip())
                if key in seen:
                    continue
                seen.add(key)
                tier = plant_prefix if sid.startswith(plant_prefix + "_") or sid.startswith("MENU") else "POOL"
                seg_label = sid[len(plant_prefix) + 1:] if tier == plant_prefix and sid.startswith(plant_prefix + "_") else sid
                jobs.append({"id": f"{tier}|{seg_label}|{phrase}", "phrase": phrase, "text": text})
    out = work / "screens" / "jobs.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"jobs": jobs}, ensure_ascii=False), encoding="utf-8")
    return {"passages": len(segs), "raw_candidates": n_raw, "both_families": len(jobs), "path": str(out)}
