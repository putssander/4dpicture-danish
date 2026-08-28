"""Step 6 — numbers only. Prints counts, rates and ranks; never a phrase or a passage.

    from pipeline import report
    report.summary(work)          # how did the planted check items do, per class and stratum
"""
import json
import statistics as st
from collections import defaultdict
from pathlib import Path


def summary(work, print_=print):
    work = Path(work)
    records = json.loads((work / "ranking.json").read_text(encoding="utf-8"))
    N = len(records)
    best = {}
    for r in records:
        key = "|".join(r["id"].split("|")[:2]) if r["cls"] != "pool" else r["id"]
        if key not in best or r["rank"] < best[key]["rank"]:
            best[key] = r
    items = list(best.values())

    def block(name, rows):
        if not rows:
            return None
        ranks = [r["rank"] for r in rows]
        row = {"n": len(rows), "verify_keep": round(100 * sum(r["keep"] for r in rows) / len(rows), 1),
               "experiential": round(100 * sum(r["exp"] for r in rows) / len(rows), 1),
               "median_rank": int(st.median(ranks)),
               "top10pct": round(100 * sum(1 for x in ranks if x <= N * 0.1) / len(ranks), 1),
               "bottom_half": round(100 * sum(1 for x in ranks if x > N * 0.5) / len(ranks), 1)}
        print_(f"{name:26s} n={row['n']:5d}  verify-keep {row['verify_keep']:5.1f}%  experiential {row['experiential']:5.1f}%"
               f"  median rank {row['median_rank']:5d} of {N}  top-10% {row['top10pct']:5.1f}%  bottom-half {row['bottom_half']:5.1f}%")
        return row

    out = {"ranked": N}
    print_(f"candidates ranked: {N}")
    for label, key in (("planted Menu entries", "menu"), ("corpus candidates", "pool"),
                       ("ReframeCovid anchors", "anchor"), ("wrong-topic probes", "probe")):
        row = block(label, [r for r in items if r["cls"] == key])
        if row:
            out[key] = row
    by_str = defaultdict(list)
    for r in items:
        if r["cls"] == "pool":
            by_str[r["stratum"]].append(r)
    if len(by_str) > 1:
        print_("by source:")
        out["by_stratum"] = {s: block("  " + s, by_str[s]) for s in sorted(by_str, key=lambda k: -len(by_str[k]))}
    tiers = [sum(1 for r in records if r["tier"] == t) for t in (0, 1, 2)]
    print_(f"tiers: kept+experiential {tiers[0]}  kept only {tiers[1]}  verify-rejected {tiers[2]}")
    out["tiers"] = tiers
    return out
