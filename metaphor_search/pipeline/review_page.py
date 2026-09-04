#!/usr/bin/env python3
"""Build a standalone review-and-labelling page for one ranked candidate list (BOX-SIDE).

Vocabulary (see RANKER_EVAL_REPORT.md): **target-conditioned** retrieval puts the
illness target in the extraction prompt ("ask narrow"); **target-screened** retrieval
extracts openly and applies the target in a later screen ("ask wide, then filter").
These pages rank target-screened output and mark which candidates a target-conditioned
run also found.

One page per corpus, and deliberately **self-contained per corpus**: a page carries its own
summary, caveats and data-handling terms, and never links to or reports numbers from another
corpus. Bundles are shared with different partners, so a Dutch page must not carry Danish
material and vice versa.

The page makes no network requests, so it opens by double-click on any laptop, offline,
with nothing installed.

Two things it does beyond displaying a ranking:

  * **Provenance filtering.** With --old-spans, each candidate is marked as found by the
    earlier run, by this run only, or by both, and the reader can filter to any of those.
    This is how a reviewer sees what the new pipeline adds rather than re-finds.
  * **Human labelling, multi-rater.** A rater enters a name and a role (PPI panel member,
    researcher, clinician, other) and marks candidates. Labels autosave locally and export
    as JSON.

    PRIVACY BY DESIGN: the export contains **candidate ids and verdicts only — never any
    segment text** (an id is `<passage ref>|<short expression>`) — so rater files can be
    emailed and merged without moving participant passages. The page itself does contain text and stays local-only.

Usage:
  review_page.py --stack /work/speech/eval/danish_t4 --ranking danish_final_ranking.json \\
      --corpus "Danish (interviews + questionnaire)" --stratum-noun source \\
      --old-spans /work/speech/eval/danish_b2_old_spans.json
"""

import argparse
import html
import json
import re
import statistics as st
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--stack", required=True)
ap.add_argument("--ranking", required=True)
ap.add_argument("--jobs", default="screens/jobs.json")
ap.add_argument("--plant-prefix", default="PLANT")
ap.add_argument("--corpus", required=True)
ap.add_argument("--stratum-noun", default="stratum")
ap.add_argument("--source-note", default="")
ap.add_argument("--conditioned-spans", default="", dest="old_spans",
                help="JSON list of spans from a TARGET-CONDITIONED run")
ap.add_argument("--conditioned-label", default="target-conditioned retrieval",
                dest="old_label")
ap.add_argument("--out", default="",
                help="output filename; defaults to a name naming the AUDIENCE, "
                     "since these files are sent to people: "
                     "<corpus>_stage1_for_researchers.html, "
                     "<corpus>_stage2_for_PPI_panel.html, "
                     "<corpus>_working_copy_project_team.html")
ap.add_argument("--stage", choices=("explore", "filter", "vote"), default="explore",
                help="explore = working page with ranks and filters, for the team. "
                     "filter = stage 1, researcher filtering: the top of the ranking plus a "
                     "concealed deep sample, shuffled, no rank shown. "
                     "vote = stage 2, PPI voting on the stage-1 shortlist only.")
ap.add_argument("--filter-top", type=int, default=300,
                help="stage 1: how far down the ranking to review exhaustively")
ap.add_argument("--filter-deep", type=int, default=60,
                help="stage 1: how many items to draw from BELOW that cut. Without these the "
                     "retrospective check is circular — reviewers can only pick what they saw.")
ap.add_argument("--shortlist", default="",
                help="stage 2: JSON of ids that survived stage 1")
ap.add_argument("--exclude-plant-ids", default="",
                help="comma-separated planted segment ids to DROP (e.g. MENUDA_3,MENUDA_6). "
                     "Use for plants that were quoted as scoring anchors: they are scored "
                     "partly against themselves, they rank near the top, and putting them "
                     "in front of a reviewer wastes attention on contaminated items.")
ap.add_argument("--vehicle-tags", default="",
                help="JSONL of re-tagged source domains (retag_vehicle.py output). Adds a "
                     "source-domain pill and filter, so a reviewer can see that twenty "
                     "phrasings are one image.")
ap.add_argument("--simile-language", default="",
                help="tag candidates whose expression carries an explicit comparison marker "
                     "(en/da/nl), using the same patterns as simile_extract.py, so reviewers "
                     "can filter to the simile arm and judge it directly")
ap.add_argument("--provenance", default="",
                help="the 'How this list was made' trail shown on every page: steps separated "
                     "by '||' — source material, extraction, screens, merge. The stage-specific "
                     "final step (what THIS page shows and why it has this many rows) is added "
                     "automatically. Reviewers must be able to see where the list comes from.")
ap.add_argument("--stream", default="",
                help="stage 1 per source stream: NAME=STRATUM[,STRATUM...] e.g. "
                     "interviews=colorectal,mamma,MENUDA. The cut and the deep sample are "
                     "taken within the stream, and the file is named after it. Use when one "
                     "source outranks another wholesale (the Danish questionnaire fills the "
                     "mixed top 300), so each reviewer group gets its own top of the list.")
ap.add_argument("--filter-deep-band", type=int, default=0,
                help="stage 1: take two thirds of the deep sample from positions "
                     "(filter-top, BAND] and one third from beyond BAND, instead of uniformly "
                     "over the whole tail — puts the retrospective's power where validated "
                     "items actually sit. 0 = uniform over the tail.")
ap.add_argument("--no-collapse", action="store_true",
                help="stages 1-2: do NOT merge identical phrasings. By default rows whose "
                     "expression is the same string (case/punctuation-insensitive) are shown "
                     "once, with a count and the variants' passages under the fold; one label "
                     "applies to all of them and the export carries every underlying id.")
ap.add_argument("--vehicle-layers", default="",
    help="JSONL from vehicle_layers.py: per-id head word, WordNet, FrameNet and LLM concept layers")
ap.add_argument("--ranked-page", default="",
    help="filename of the stage-3 ranked page; blind pages link to it from their banner")
ap.add_argument("--demo-theme", action="store_true",
    help="use the public demo shell and shared demo.css presentation layer")
ap.add_argument("--theme-tag", default="",
    help="header tag text for the themed shell (default: 'Public English demo' / 'Blinded review')")
ap.add_argument("--theme-private", action="store_true",
    help="themed shell for a PRIVATE corpus: no public-data strip, data-handling note kept")
ap.add_argument("--lang", default="", help="UI language of the review app for this list: en|da|nl (default: --simile-language, else en)")
ap.add_argument("--return-to", default="", help="e-mail address the exported labels go back to (shown after export)")
ap.add_argument("--corpus-key", default="", help="stable corpus id for label storage and exports (default: --corpus)")
ap.add_argument("--stream-label", default="", help="stream name as shown to reviewers, in their language (default: the stream name)")
ap.add_argument("--json-only", action="store_true", help="write only the review bundle (.json), no HTML page")
ap.add_argument("--translated-plants", action="store_true", help="planted Menu entries are translations (wording of the plant note)")
ap.add_argument("--blind-seed", type=int, default=20260819)
ap.add_argument("--top", type=int, default=500)
ap.add_argument("--bottom", type=int, default=50)
A = ap.parse_args()
A.blind = A.stage in ("filter", "vote")

# The audience belongs in the filename: these pages are emailed to researchers and to panel
# members, and a recipient should be able to tell at a glance that a file is meant for them.
SLUG = re.sub(r"[^a-z0-9]+", "_", (A.corpus_key or A.corpus).lower()).strip("_")   # stable file names, whatever the display language
STREAM_NAME, STREAM_STRATA = "", set()
if A.stream:
    STREAM_NAME, _st = A.stream.split("=", 1)
    STREAM_STRATA = {x.strip() for x in _st.split(",") if x.strip()}
    STREAM_SLUG = re.sub(r"[^a-z0-9]+", "_", STREAM_NAME.lower()).strip("_")
if not A.out:
    A.out = {"filter": f"{SLUG}_stage1_for_researchers{('_' + STREAM_SLUG) if A.stream else ''}.html",
             "vote": f"{SLUG}_stage2_for_PPI_panel.html",
             "explore": f"{SLUG}_working_copy_project_team.html"}[A.stage]

DROP = {x.strip() for x in A.exclude_plant_ids.split(",") if x.strip()}

B = Path(A.stack)
ranking = json.loads((B / A.ranking).read_text(encoding="utf-8"))
# Planted entries the scoring screen was shown are never considered: the rank scripts flag
# them (`leak`, see plant_leak.py) and they are dropped here automatically; --exclude-plant-ids
# remains for rankings produced before the flag existed.
_before = len(ranking)
_flagged = {(r["id"].split("|")[1] if r["id"].startswith("PLANT|") else r["id"].split("|")[0])
            for r in ranking if r.get("leak")}
DROP |= _flagged
if DROP:
    ranking = [r for r in ranking
               if not r.get("leak")
               and r["id"].split("|")[0] not in DROP
               and (len(r["id"].split("|")) < 2 or r["id"].split("|")[1] not in DROP)]
    print(json.dumps({"excluded_anchor_leaked_plants": sorted(DROP),
                      "rows_dropped": _before - len(ranking)}), file=__import__("sys").stderr)
# planted ENTRIES recovered as candidates (ids are "MENUDA_3|phrase" or "PLANT|MENU_3|phrase");
# the rank script drops entries quoted in the scoring prompt before ranking and records them
# in a sidecar next to the ranking, which the page reports so the count is explained
_pk = lambda i: i.split("|")[1 if i.startswith("PLANT|") else 0]
n_plant_entries = len({_pk(r["id"]) for r in ranking if r["cls"] == "plant"})
_side = sorted(B.glob("*_excluded_quoted_plants.json"))
if _side:
    _x = json.loads(_side[0].read_text(encoding="utf-8"))
    excl_entries = sorted({_pk(r["id"]) for r in _x["rows"]})
    excl_rows = len(_x["rows"])
else:
    excl_entries, excl_rows = sorted(DROP), 0
jobs = {j["id"]: j for j in json.loads(
    (B / A.jobs).read_text(encoding="utf-8"))["jobs"]}
N = len(ranking)

# ---- provenance against an earlier run --------------------------------------
PUNCT, WS = re.compile(r"[^\w\s]", re.UNICODE), re.compile(r"\s+")


def norm(s):
    s = unicodedata.normalize("NFKC", str(s)).casefold()
    return WS.sub(" ", PUNCT.sub(" ", s)).strip()


old = set()
if A.old_spans:
    raw = json.loads(Path(A.old_spans).read_text(encoding="utf-8"))
    old = {norm(x) for x in (raw["spans"] if isinstance(raw, dict) else raw)}
old_sorted = sorted(old, key=len)


def in_old(phrase):
    n = norm(phrase)
    if len(n) < 3 or not old:
        return False
    if n in old:
        return True
    for o in old_sorted:
        if len(o) < len(n) * 0.5:
            continue
        if n in o or o in n:
            return True
    return False



def highlight(text, phrase):
    """Escape the context, then mark the candidate expression inside it.

    Reviewers scan hundreds of items; finding the expression inside two or three sentences
    of surrounding text is the slowest part of the task. Matching is case-insensitive and
    whitespace-tolerant, because extractors normalise spacing. If the expression cannot be
    located (models sometimes paraphrase slightly) the context is shown unmarked rather
    than mangled.
    """
    esc = html.escape(text)
    ph = phrase.strip()
    if len(ph) < 3:
        return esc
    pattern = r"\s+".join(re.escape(w) for w in html.escape(ph).split())
    try:
        return re.sub(f"({pattern})", r"<mark>\1</mark>", esc, count=1, flags=re.IGNORECASE)
    except re.error:
        return esc


# ---- source-domain tags -------------------------------------------------------
# --vehicle-tags takes one file, or "label=file,label=file" for two model families
# (retag_vehicle_v3 output). VEH = first family, VEH2 = second; each id -> (analyst, domain, code).
VEH, VEH2, VEH_LABEL = {}, {}, {}
VEH_NAMES = []
def _load_tags(path, into):
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        if "_header" in d or "id" not in d:
            continue
        key = d.get("analyst") or ""
        if key:
            into[d["id"]] = (key, d.get("domain", ""), d.get("code", ""))
if A.vehicle_tags:
    _specs = [x.strip() for x in A.vehicle_tags.split(",") if x.strip()]
    for k, spec in enumerate(_specs[:2]):
        name, _, path = spec.rpartition("=")
        if Path(path).exists():
            _load_tags(path, VEH if k == 0 else VEH2)
            VEH_NAMES.append(name or ("model A" if k == 0 else "model B"))
    _tags = json.loads((Path(__file__).resolve().parent / "usas_tags.json").read_text(encoding="utf-8")) \
        if (Path(__file__).resolve().parent / "usas_tags.json").exists() else {}
    for _c, _d in _tags.items():
        _l = _c[0]
        if _l.isalpha() and (_l not in VEH_LABEL or len(_c) < 3):
            VEH_LABEL[_l] = _d.lower()

try:
    _CD = {c: str(d).lower() for c, d in json.loads((Path(__file__).resolve().parent.parent.parent
           / "resources/usas/usas_tags.json").read_text(encoding="utf-8")).items()}
except Exception:
    _CD = {}
LAYERS = {}
def norm_label(s):
    """Free-text model concepts vary in punctuation and articles ('star wars (jedi knights)' vs
    'star wars jedi knights', 'a rollercoaster' vs 'rollercoaster'): fold those before counting."""
    s = re.sub(r"[^\w\s]", " ", str(s or "").lower().replace("-", " "))
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"^(a|an|the|some) ", "", s)
    return s
if A.vehicle_layers and Path(A.vehicle_layers).exists():
    for line in Path(A.vehicle_layers).read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                d = json.loads(line)
                for k in ("llm", "llm_c1", "llm_c2", "head", "wn1", "wn2"):
                    if d.get(k):
                        d[k] = norm_label(d[k])
                LAYERS[d["id"]] = d
            except Exception:
                pass



# ---- simile marking -----------------------------------------------------------
# Same patterns as simile_extract.py, imported rather than copied so the page and the
# measured arm can never disagree about what counts as a simile.
SIMILE = None
if A.simile_language:
    # Read the marker table out of simile_extract.py rather than importing it: that module
    # runs its extraction at import time, so importing it here would execute a pipeline.
    # Parsing the literal keeps the page and the measured arm on one definition of a simile.
    import ast
    src = (Path(__file__).resolve().parent / "simile_extract.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    markers = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "MARKERS":
            markers = ast.literal_eval(node.value)
            break
    if markers and A.simile_language in markers:
        SIMILE = re.compile("|".join(markers[A.simile_language]), re.IGNORECASE)


def _phrase_of(r):
    return (jobs.get(r["id"], {}).get("phrase") or r["id"].split("|")[-1])


def collapse_phrasings(rows):
    """Merge rows whose expression is the same string. The best-ranked row represents the
    group and carries the others in r["members"]; reviewers see one row with a count and
    the variants' passages under the fold, and one label covers them all. Frequency is
    then visible instead of costing the reviewer repeated reads."""
    for r in rows:
        r["members"] = []
    if A.no_collapse or A.stage == "explore":
        return rows
    rep_of, out = {}, []
    for r in rows:
        k = norm(_phrase_of(r))
        if k in rep_of:
            rep_of[k]["members"].append(r)
        else:
            rep_of[k] = r
            out.append(r)
    return out


# ---- selection ---------------------------------------------------------------
if A.stage == "filter":
    # STAGE 1 — researcher filtering.
    # Everything down to --filter-top, PLUS a random sample from below it, shuffled together
    # so a reviewer cannot tell which is which. The deep sample is what makes the later
    # retrospective check meaningful: if nothing from it survives to the menu, the ranking
    # is vindicated; if some does, the cut is too shallow and we learn by how much.
    import random
    rng = random.Random(A.blind_seed)
    # positional, not by rank value: after --exclude-plant-ids the stored ranks have
    # gaps, and a value cut would silently shrink the head by the number excluded
    srt = sorted(ranking, key=lambda r: r["rank"])
    if STREAM_STRATA:
        srt = [r for r in srt if r["stratum"] in STREAM_STRATA]
    srt = collapse_phrasings(srt)
    head, tail = srt[:A.filter_top], srt[A.filter_top:]
    if A.filter_deep_band and A.filter_deep_band > A.filter_top:
        near, far = tail[:A.filter_deep_band - A.filter_top], tail[A.filter_deep_band - A.filter_top:]
        n_near = min(len(near), round(A.filter_deep * 2 / 3))
        n_far = min(len(far), A.filter_deep - n_near)
        deep = rng.sample(near, n_near) + rng.sample(far, n_far)
    else:
        deep = rng.sample(tail, min(A.filter_deep, len(tail)))
    chosen = head + deep
    rng.shuffle(chosen)
    for i, r in enumerate(chosen, 1):
        r["display_no"] = i
elif A.stage == "vote":
    # STAGE 2 — PPI voting on the stage-1 shortlist only. No sequence number is shown:
    # even a position in a list nudges judgement.
    import random
    rng = random.Random(A.blind_seed)
    keep_ids = json.loads(Path(A.shortlist).read_text(encoding="utf-8"))
    keep_ids = set(keep_ids["ids"] if isinstance(keep_ids, dict) else keep_ids)
    chosen = collapse_phrasings([r for r in sorted(ranking, key=lambda r: r["rank"])
                                 if r["id"] in keep_ids])
    rng.shuffle(chosen)
    for i, r in enumerate(chosen, 1):
        r["display_no"] = i
else:
    chosen, seen = [], set()
    for r in ranking[:A.top]:
        chosen.append(r); seen.add(r["id"])
    for r in ranking:
        if r["cls"] == "plant" and r["id"] not in seen:
            chosen.append(r); seen.add(r["id"])
    for r in ranking[-A.bottom:]:
        if r["id"] not in seen:
            chosen.append(r); seen.add(r["id"])
    chosen.sort(key=lambda r: r["rank"])

# ---- summary from THIS corpus only -------------------------------------------
best = {}
for r in ranking:
    key = r["id"].split("|")[0] if r["cls"] == "plant" else r["id"]
    if key not in best or r["rank"] < best[key]["rank"]:
        best[key] = r
items = list(best.values())


def stats(rows):
    rk = [r["rank"] for r in rows]
    return {"n": len(rows), "keep": 100*sum(r["keep"] for r in rows)/len(rows),
            "exp": 100*sum(r["exp"] for r in rows)/len(rows),
            "median": int(st.median(rk)),
            "top10": 100*sum(1 for x in rk if x <= N*0.1)/len(rk),
            "bottom": 100*sum(1 for x in rk if x > N*0.5)/len(rk)}


plants = [r for r in items if r["cls"] == "plant"]
pool = [r for r in items if r["cls"] == "pool"]
by_str = defaultdict(list)
for r in pool:
    by_str[r["stratum"]].append(r)
scores = [r["score"] for r in ranking if r["tier"] < 2]

# ---- the review bundle -----------------------------------------------------------
# Everything below used to be HTML assembly. The page is now ONE app (review_app/) that
# renders a JSON bundle in the reviewer's language; this script writes that bundle and,
# unless --json-only, the same app with the bundle embedded (the public demo pages).
import sys
LANG = (A.lang or A.simile_language or "en").lower()
if LANG not in ("en", "da", "nl"):
    LANG = "en"
_main = lambda c: re.match(r"[A-Z]+\d*", c).group(0) if c and re.match(r"[A-Z]+\d*", c) else ""

rows_out, n_old, n_new = [], 0, 0
for r in chosen:
    job = jobs.get(r["id"], {})
    phrase = job.get("phrase") or r["id"].split("|")[-1]
    text = job.get("text", "")[:900]
    plant = r["cls"] == "plant"
    prov = "plant" if plant else ("both" if in_old(phrase) else "new")
    if prov == "both":
        n_old += 1
    elif prov == "new":
        n_new += 1
    members = r.get("members", [])
    d = {"id": r["id"], "phrase": phrase, "text": text, "members": [m["id"] for m in members]}
    if members:
        d["n_pass"] = 1 + len({m["id"].split("|")[0] for m in members} - {r["id"].split("|")[0]})
        d["n_variants"] = len(members)
        d["variants"] = [{"id": m["id"], "text": jobs.get(m["id"], {}).get("text", "")[:900],
                          "phrase": _phrase_of(m)} for m in members[:12]]
    if A.stage == "filter":
        d["no"] = r["display_no"]
    if not A.blind:
        veh, veh_desc, veh_code = VEH.get(r["id"], ("", "", ""))
        veh_b, _, veh_code_b = VEH2.get(r["id"], ("", "", ""))
        veh_main, veh_main_b = _main(veh_code), _main(veh_code_b)
        _ly = LAYERS.get(r["id"], {})
        d.update({"rank": r["rank"], "tier": r["tier"], "score": r["score"], "vivid": bool(r["vivid"]),
                  "stratum": r["stratum"], "prov": prov, "plant": plant,
                  "simile": bool(SIMILE and SIMILE.search(phrase)),
                  "veh": veh, "veh_label": VEH_LABEL.get(veh, veh), "veh_desc": veh_desc, "veh_code": veh_code,
                  "veh_b": veh_b, "veh_code_b": veh_code_b, "veh_main": veh_main, "veh_main_b": veh_main_b,
                  "main_agree": veh_main if (veh_main and veh_main == veh_main_b) else "",
                  "code_agree": veh_code if (veh_code and veh_code == veh_code_b) else "",
                  "cat_agree": veh if (veh and veh == veh_b) else "",
                  "layers": {k: ("" if str(_ly.get(k) or "").lower() == "none" else str(_ly.get(k) or ""))
                             for k in ("head", "wn1", "wn2", "fn", "llm", "llm_c1", "llm_c2")}})
    rows_out.append(d)

n_plants_in_rows = sum(1 for r in chosen if r["cls"] == "plant")
counts = {"n_total": N, "n_rows": len(chosen), "n_plants_in_rows": n_plants_in_rows,
          "n_folded": sum(len(r.get("members", [])) for r in chosen)}
if A.stage == "filter":
    counts["n_top"] = min(A.filter_top, len(chosen))
    counts["n_deep"] = len(chosen) - counts["n_top"]

bundle = {
    "format": "metaphor-review-bundle", "version": 1,
    "lang": LANG, "corpus": A.corpus, "corpus_key": A.corpus_key or A.corpus,
    "list_id": Path(A.out).stem, "stage": A.stage, "stream": STREAM_NAME,
    "stream_label": A.stream_label or STREAM_NAME, "stratum_noun": A.stratum_noun,
    "private": bool(A.theme_private or not A.demo_theme), "header_tag": A.theme_tag,
    "return_to": A.return_to, "ranked_page": A.ranked_page if not A.json_only else "",
    "source_note": A.source_note, "translated_plants": bool(A.translated_plants or LANG != "en"),
    "provenance_steps": [x.strip() for x in A.provenance.split("||") if x.strip()],
    "counts": counts, "rows": rows_out,
}
if not A.blind:
    po = stats(pool)
    ps = stats(plants) if plants else None
    bundle["stats"] = {"plant": ps, "pool": po,
                       "by_stratum": [[s_, stats(v)] for s_, v in sorted(by_str.items(), key=lambda kv: -len(kv[1]))]}
    if scores:
        bundle["stats"]["score_mean"] = st.mean(scores)
        bundle["stats"]["score_median"] = st.median(scores)
    bundle["plants"] = {"n_entries": n_plant_entries, "N": N, "excl_entries": excl_entries, "excl_rows": excl_rows,
                        "ranks": sorted([[r["id"].split("|")[0], r["rank"], _phrase_of(r)] for r in plants],
                                        key=lambda x: x[1])}
    bundle["tier_counts"] = [sum(1 for r in chosen if r["tier"] == i) for i in (0, 1, 2)]
    bundle["category_top"] = Counter(
        VEH[r["id"]][0] for r in chosen if r["id"] in VEH and VEH[r["id"]][0]
        and VEH[r["id"]][0] not in {"Other (outside crosswalk)", "not metaphorical"}).most_common(3)
    bundle["strata"] = sorted(by_str)
    bundle["veh_cats"] = sorted(Counter(VEH[r["id"]][0] for r in chosen if r["id"] in VEH and VEH[r["id"]][0]).items(),
                                key=lambda kv: -kv[1])
    bundle["veh_codes"] = [[k, _CD.get(k.rstrip("+-"), ""), c] for k, c in sorted(
        Counter(VEH[r["id"]][2] for r in chosen if r["id"] in VEH and VEH[r["id"]][2]).items(), key=lambda kv: -kv[1])]
    _ids = {r["id"] for r in chosen}
    _nl = lambda k: sum(1 for i in _ids if LAYERS.get(i, {}).get(k))
    bundle["layers_cov"] = {"usas": sum(1 for i in _ids if i in VEH), "head": _nl("head"), "wn1": _nl("wn1"),
                            "wn2": _nl("wn2"), "fn": _nl("fn"), "llm": _nl("llm"), "llm_c1": _nl("llm_c1"), "llm_c2": _nl("llm_c2")}
    bundle["fam"] = [VEH_NAMES[0] if VEH_NAMES else "model A", VEH_NAMES[1] if len(VEH_NAMES) > 1 else ""]
    bundle["n_agree"] = sum(1 for i in _ids if i in VEH and i in VEH2 and VEH[i][2] == VEH2[i][2])
    _used = {v[2] for v in list(VEH.values()) + list(VEH2.values()) if v[2]}
    _used |= {m.group(0) for c in list(_used) for m in [re.match(r"[A-Z]+\d*", c)] if m}
    bundle["code_desc"] = {c: _CD.get(c.rstrip("+-"), "") for c in sorted(_used)}
    bundle["has_old"] = bool(old); bundle["old_label"] = A.old_label
    bundle["n_old"], bundle["n_new"] = n_old, n_new
    bundle["simile"] = bool(SIMILE)
    if A.demo_theme and not A.theme_private:
        reframe_count = sum(1 for r in chosen if r["stratum"] == "ReframeCovid")
        bundle["dataset_strip_html"] = f"""
<aside class="dataset-strip" aria-labelledby="covid-data-title">
  <div>
    <p class="eyebrow">ABOUT THE PUBLIC DATA</p>
    <h2 id="covid-data-title">COVID-19 metaphors make the method inspectable.</h2>
    <p><strong>#ReframeCovid</strong> is a crowdsourced, multilingual collection of alternatives to war language and other ways of framing COVID-19. This demo uses its English entries because they may be redistributed. It is not a patient cohort and does not validate a cancer Menu. The extraction, checks, categories and ranking were added by this project—not by the original dataset publishers.</p>
  </div>
  <div class="dataset-summary">
    <span><strong>{reframe_count:,}</strong> #ReframeCovid expressions</span>
    <span><strong>{n_plants_in_rows:,}</strong> phrases from Menu check items</span>
    <a href="https://docs.google.com/spreadsheets/d/1TZqICUdE2CvKqZrN67LcmKspY51Kug7aU8oGvK5WEbA/edit" target="_blank" rel="noopener">Open the original collection <span aria-hidden="true">&#8599;</span></a>
    <small>Reddit benchmark text is not reproduced.</small>
  </div>
</aside>"""

json_path = B / (Path(A.out).stem + ".json")
json_path.write_text(json.dumps(bundle, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
html_path = None
if not A.json_only:
    sys.path.insert(0, str(Path(__file__).resolve().parent / "review_app"))
    from build_review_app import embed_bundle
    html_path = B / A.out
    embed_bundle(bundle, B / "demo.css", html_path)

print(json.dumps({"corpus": A.corpus, "lang": LANG, "stream": STREAM_NAME or None, "rendered": len(chosen),
                  "rows_folded_under_them": counts["n_folded"], "of_total": N,
                  "plants_included": n_plants_in_rows, "strata": len(by_str),
                  "provenance": ({"also_in_old": n_old, "new": n_new} if old else "not compared"),
                  "json": str(json_path), "path": str(html_path or json_path)}, indent=1))
