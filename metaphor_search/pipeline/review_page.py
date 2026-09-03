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
    candidate or segment text** — so rater files can be emailed and merged without moving
    participant data. The page itself does contain text and stays local-only.

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
ap.add_argument("--blind-seed", type=int, default=20260819)
ap.add_argument("--top", type=int, default=500)
ap.add_argument("--bottom", type=int, default=50)
A = ap.parse_args()
A.blind = A.stage in ("filter", "vote")

# The audience belongs in the filename: these pages are emailed to researchers and to panel
# members, and a recipient should be able to tell at a glance that a file is meant for them.
SLUG = re.sub(r"[^a-z0-9]+", "_", A.corpus.lower()).strip("_")
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
    _CD = {c: str(d).lower() for c, d in json.loads((Path(__file__).resolve().parent / "usas_tags.json").read_text(encoding="utf-8")).items()}
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

btn_yes, btn_maybe, btn_no, btn_unsure = {
    "explore": ("belongs on the menu", "maybe", "no", "can't judge"),
    "filter":  ("put to the panel", "borderline", "reject", "can't judge"),
    "vote":    ("yes, this belongs", "maybe", "no", "can't judge"),
}[A.stage]

# ---- rows --------------------------------------------------------------------
rows_html, n_old, n_new = [], 0, 0
for r in chosen:
    job = jobs.get(r["id"], {})
    phrase = job.get("phrase") or r["id"].split("|")[-1]
    text = job.get("text", "")
    plant = r["cls"] == "plant"
    prov = "plant" if plant else ("both" if in_old(phrase) else "new")
    is_simile = bool(SIMILE and SIMILE.search(phrase))
    veh, veh_desc, veh_code = VEH.get(r["id"], ("", "", ""))
    veh_b, _, veh_code_b = VEH2.get(r["id"], ("", "", ""))
    _main = lambda c: re.match(r"[A-Z]+\d*", c).group(0) if c and re.match(r"[A-Z]+\d*", c) else ""
    veh_main, veh_main_b = _main(veh_code), _main(veh_code_b)
    main_agree = veh_main if (veh_main and veh_main == veh_main_b) else ""
    code_agree = veh_code if (veh_code and veh_code == veh_code_b) else ""
    cat_agree = veh if (veh and veh == veh_b) else ""
    _ly = LAYERS.get(r["id"], {})
    layer_attrs = "".join(f' data-{k}="{html.escape("" if str(_ly.get(k) or "").lower() == "none" else str(_ly.get(k) or ""))}"'
                          for k in ("head", "wn1", "wn2", "fn", "llm", "llm_c1", "llm_c2"))
    if prov == "both":
        n_old += 1
    elif prov == "new":
        n_new += 1
    tier = ("illness + lived experience" if r["tier"] == 0 else
            "about illness" if r["tier"] == 1 else "remaining candidate")
    provpill = ({"both": f'<span class="pill old">also found by {html.escape(A.old_label)}</span>',
                 "new": '<span class="pill new">target-screened only</span>',
                 "plant": '<span class="pill plant">PLANTED check item · Menu entry</span>'})[prov]
    if A.blind:
        # Nothing that could anchor a rater: no rank, score, tier, register, source or
        # provenance reaches the page. Only a sequence number, the expression, its context
        # and the buttons. The rater's judgement must not be a reaction to our ordering.
        head = (f'<div class="row" data-stratum="" data-tier="" data-prov="" '
                f'data-members="{html.escape(json.dumps([m["id"] for m in r.get("members", [])]))}" '
                f'data-id="{html.escape(r["id"])}">'
                + (f'<div class="meta"><span class="rank">'
                   f'{r["display_no"]} / {len(chosen)}</span></div>'
                   if A.stage == "filter" else '<div class="meta"></div>'))
    else:
        head = (f'<div class="row" data-stratum="{html.escape(r["stratum"])}" '
                f'data-tier="{r["tier"]}" data-prov="{prov}" '
                f'data-simile="{int(is_simile)}" data-veh="{veh}" data-vehcode="{html.escape(veh_code)}" '
                f'data-rank="{r.get("rank", "")}" data-vehb="{veh_b}" data-vehcodeb="{html.escape(veh_code_b)}" '
                f'data-codeagree="{html.escape(code_agree)}" data-catagree="{cat_agree}" '
                f'data-vehmain="{veh_main}" data-vehmainb="{veh_main_b}" data-mainagree="{main_agree}"{layer_attrs} '
                f'data-id="{html.escape(r["id"])}">'
                f'<div class="meta"><span class="rank">#{r["rank"]}</span>'
                f'<span class="pill s{r["tier"]}">{tier}</span>'
                f'<span class="pill">score {r["score"]:.0f}</span>'
                f'<span class="pill">'
                f'{"vivid" if r["vivid"] else "conventional"}</span>'
                f'<span class="pill src">{html.escape(r["stratum"])}</span>{provpill}'
                + ('<span class="pill sim">comparison marker</span>' if is_simile else '')
                + (f'<span class="pill veh">{html.escape(VEH_LABEL.get(veh, veh))}{(' &middot; ' + html.escape(veh_desc)) if veh_desc else ''}</span>' if veh else '')
                + '</div>')
    members = r.get("members", [])
    n_pass = 1 + len({m["id"].split("|")[0] for m in members} - {r["id"].split("|")[0]})
    count_pill = (f'<span class="pill cnt" title="this phrasing occurs in {n_pass} passages">'
                  f'&times;{n_pass} passages</span>' if members else '')
    variants = "".join(
        f'<p class="ctx">{highlight(jobs.get(m["id"], {}).get("text", "")[:900], _phrase_of(m))}</p>'
        for m in members[:12]) + (f'<p class="ctx"><em>… and {len(members) - 12} more passages</em></p>'
                                  if len(members) > 12 else '')
    rows_html.append(
        head +
        f'<div class="phrase">{html.escape(phrase)}{count_pill}</div>'
        f'<details><summary>context{(" · " + str(n_pass) + " passages") if members else ""}</summary>'
        f'<p class="ctx">{highlight(text[:900], phrase)}</p>{variants}</details>'
        f'<div class="lbl" data-for="{html.escape(r["id"])}">'
        f'<button data-v="yes">{btn_yes}</button>'
        f'<button data-v="maybe">{btn_maybe}</button>'
        f'<button data-v="no">{btn_no}</button>'
        f'<button data-v="unsure">{btn_unsure}</button></div></div>')

opts = "".join(f'<option value="{html.escape(s)}">{html.escape(s)}</option>'
               for s in sorted(by_str))
ps, po = stats(plants) if plants else None, stats(pool)
str_rows = "".join(
    f"<tr><td>{html.escape(s)}</td><td>{len(v):,}</td><td>{stats(v)['keep']:.1f}%</td>"
    f"<td>{stats(v)['exp']:.1f}%</td><td>{stats(v)['median']:,}</td></tr>"
    for s, v in sorted(by_str.items(), key=lambda kv: -len(kv[1])))
plant_row = ("" if not plants else
             f"<tr class='hi'><td>Planted check items (Menu entries)</td><td>{ps['n']:,}</td>"
             f"<td>{ps['keep']:.0f}%</td><td>{ps['exp']:.0f}%</td><td>{ps['median']:,}</td>"
             f"<td>{ps['top10']:.0f}%</td><td>{ps['bottom']:.0f}%</td></tr>")
plant_block = ("" if (not plants or A.blind) else f"""
<h2>What “planted” means</h2>
<p class="lede">The rows marked <span class="pill plant">PLANTED check item · Menu entry</span>
are not from this corpus. They are {'published' if A.simile_language == 'en' else 'translations of published'}
entries of the <a href="https://wp.lancs.ac.uk/melc/the-metaphor-menu/">Metaphor Menu</a>
(Lancaster University; 17 entries{', of which the 15 that are not among the Dutch scoring anchors were translated and planted' if A.simile_language == 'nl' else ''}),
inserted into the pool as a known-good check. They went through the same extraction as
everything else, so if the ranking works they should surface near the top — in this list the
{n_plant_entries} planted entries that yield a candidate sit at median position {ps['median']:,}
of {N:,}. {('A further ' + str(len(excl_entries)) + ' planted entries are not considered and were removed before ranking, because they are quoted as examples inside the scoring prompt and would be scored partly against themselves'
   + (' (' + str(excl_rows) + ' candidate rows)' if excl_rows else '') + '.') if excl_entries else ''}
Planted items show where <em>validated</em> expressions land; they do not prove that the
unvalidated candidates below them are well ordered.</p>""")
prov_block = ("" if (not old or A.blind) else f"""
<h2>What is new in this list</h2>
<p class="lede">This list comes from <strong>target-screened</strong> retrieval: extract metaphors openly,
then screen for the illness target. Candidates are marked against a
<strong>{html.escape(A.old_label)}</strong> run, which applies the same target constraint in
the extraction prompt instead. Of the
{len(chosen)-len([r for r in chosen if r['cls']=='plant']):,} shown here,
<strong>{n_old:,}</strong> were found by both approaches and <strong>{n_new:,}</strong> only by
target-screening. Use the <em>provenance</em> filter to read either group alone.</p>""")

# In blinded mode the ranking-derived filters are withheld along with everything else that
# could tell a rater what the software thought. The selects still exist, hidden, so the
# filtering script needs no separate blinded variant.
score_note = "" if A.blind else (
    f'<div class="note"><strong>Read the order, not the score.</strong> '
    f'Menu-likeness scores are compressed near the bottom of the 0-10 range '
    f'(mean {st.mean(scores):.2f}, median {st.median(scores):.1f}), so position '
    f'near the top rests on the screens rather than on score differences. '
    f'Planted items are translations and may read more formally than '
    f'spontaneous language.</div>')
PURPOSE = {
 "filter": ("<strong>Purpose:</strong> first-pass filtering. Mark which candidate expressions "
            "are worth putting to the panel. <strong>Data:</strong> {data}. Your judgements are "
            "compared with the software's ordering afterwards, which is how we learn whether "
            "that ordering can be trusted — so the ordering is deliberately hidden from you."),
 "vote": ("<strong>Purpose:</strong> deciding what goes on the menu. These expressions were "
          "already filtered by researchers; you are judging whether each one belongs. "
          "<strong>Data:</strong> {data}. Several people vote independently and disagreement "
          "is expected."),
 "explore": ("<strong>Purpose:</strong> stage 3, after the votes are in. The project team "
             "checks how the system ordered its output and where the expressions people kept "
             "had been sitting in the ranking — for example whether everything that reached "
             "the menu was in the top few hundred. Not for collecting judgements. "
             "<strong>Data:</strong> {data}."),
}[A.stage]
purpose = PURPOSE.format(data=html.escape(A.source_note or A.corpus).rstrip("."))

ROLE_OPTS = (("ppi", "PPI panel member"), ("researcher", "Researcher"),
             ("clinician", "Clinician"), ("other", "Other"))
DEFAULT_ROLE = {"vote": "ppi", "filter": "researcher", "explore": ""}[A.stage]
role_field = ("<label>Role <select id=\"rrole\">"
              + ("" if DEFAULT_ROLE else "<option value=\"\">choose…</option>")
              + "".join(f"<option value=\"{v}\"{' selected' if v == DEFAULT_ROLE else ''}>"
                        f"{lbl}</option>" for v, lbl in ROLE_OPTS)
              + "</select></label>")

STAGE_NO = {"filter": 1, "vote": 2, "explore": 3}[A.stage]
mode_title = {"filter": "stage 1 of 3 — filtering" + (f" · {STREAM_NAME}" if A.stream else ""),
              "vote": "stage 2 of 3 — voting",
              "explore": "stage 3 of 3 — retrospective (working copy)"}[A.stage]
STAGES = (("1", "Filtering", "researchers"), ("2", "Voting", "PPI panel"),
          ("3", "Retrospective", "project team"))
stage_strip = '<nav class="stages">' + "".join(
    f'<span class="st{" cur" if int(n) == STAGE_NO else ""}"><b>{n}</b> {name}'
    f'<small>{who}</small></span>' for n, name, who in STAGES) + "</nav>"
if A.blind:
    if A.stage == "filter":
        _merged = sum(len(r.get("members", [])) for r in chosen)
        lede = ((f"{STREAM_NAME.capitalize()} only. " if A.stream else "")
                + f"{len(chosen)} expressions in random order"
                + (f" (identical phrasings are shown once with a count; {_merged} further "
                   f"passages are folded under them, and one label covers all of them)" if _merged else "")
                + ". Nothing about how the software "
                f"rated or ranked them is shown, so your judgement is your own. Mark the ones "
                f"worth putting to the panel. Some of these were rated poorly by the software "
                f"and some highly — which is deliberate, and comparing your choices with its "
                f"order afterwards is how we find out whether the ordering can be trusted.")
    else:
        lede = (f"{len(chosen)} expressions that researchers selected as worth considering, "
                f"shown in random order. For each one: could this belong on a menu offered to "
                f"people living with cancer — something a patient might recognise and use for "
                f"their own experience? There are no right answers, and your view may differ "
                f"from other panel members. That is the point.")
else:
    lede = (f"{N:,} candidates ordered after second-family verification, then recorded screens for illness relevance, lived experience, and menu resemblance, with vividness as tiebreak. " + html.escape(A.source_note))
# ---- status block: the first thing on the page, in bold, two lines ------------------
_rank_link = (f'<a href="{html.escape(A.ranked_page)}">the ranked list (stage 3)</a>' if A.ranked_page
              else 'stage 3')
STATUS = {
 "filter": ('<b>NOT RANKED.</b> Random order, on purpose — the ranking is hidden so your choices can test it.',
            '<b>YOUR JOB:</b> mark the expressions worth putting to the panel.',
            f'Some rows come from deep in the list. To see the ordering, open {_rank_link}.'),
 "vote":   ('<b>NOT RANKED.</b> Random order, no scores.',
            '<b>YOUR JOB:</b> say whether each expression belongs on a menu for people living with cancer.',
            'There are no right answers; panel members are expected to disagree.'),
 "explore": ('<b>RANKED.</b> Best candidates first, as the software ordered them.',
             '<b>PURPOSE:</b> see where the expressions people kept had been sitting, and browse by source domain.',
             'Not for collecting judgements. Planted check items are marked in blue.'),
}[A.stage]
status_block = ('<div class="status"><div class="l1">' + STATUS[0] + '</div><div class="l2">' + STATUS[1]
                + '</div><div class="l3">' + STATUS[2] + '</div></div>')

# The public English demo is also a project showcase. Its shared presentation layer keeps
# the ranked output easy to explore, while the normal self-contained pages remain suitable
# for private, offline hand-off in Danish and Dutch.
theme_link = '<link rel="stylesheet" href="demo.css">' if A.demo_theme else ''
body_class = ('ranked-page' if A.stage == 'explore' else 'review-page') if A.demo_theme else ''
site_header = ('' if not A.demo_theme else
    '<header class="site-header" aria-label="Demo navigation">'
    '<a class="brand" href="index.html" aria-label="Back to the metaphor discovery demo">'
    '<span class="brand-mark" aria-hidden="true">M</span><span>Metaphor discovery</span></a>'
    f'<span class="header-tag">{html.escape(A.theme_tag) if A.theme_tag else ("Public English demo" if A.stage == "explore" else "Blinded review")}</span>'
    '</header>')
if A.demo_theme and A.stage == "explore":
    tier0 = sum(1 for r in chosen if r["tier"] == 0)
    plant_phrases = sum(1 for r in chosen if r["cls"] == "plant")
    site_header += f'''
<section class="rank-hero">
  <div>
    <p class="eyebrow">PROJECT OUTPUT · RANKED VIEW</p>
    <h1>What the models found, in the order people would see it.</h1>
    <p class="hero-lede">Explore every {"" if A.theme_private else "public "}candidate, from the strongest signals to the weakest. Open the context, filter the list, or group expressions by the image they borrow.</p>
    <div class="hero-actions">
      <a class="button primary" href="#candidates">Browse the ranking <span aria-hidden="true">&#8595;</span></a>
      <button class="button secondary" id="labelToggle" type="button" aria-pressed="false">Switch to labelling</button>
    </div>
  </div>
  <div class="rank-metrics" aria-label="Ranked output summary">
    <div class="rank-metric"><strong>{len(chosen):,}</strong><span>{"" if A.theme_private else "public "}candidate expressions</span></div>
    <div class="rank-metric"><strong>{tier0:,}</strong><span>kept and experiential</span></div>
    <div class="rank-metric"><strong>{plant_phrases:,}</strong><span>phrases from known-good checks</span></div>
  </div>
</section>'''

data_note = ('''<div class="note"><strong>Public demonstration.</strong> This page contains
open-licensed text from #ReframeCovid and published Metaphor Menu entries. Patient and
participant text from the project's Danish and Dutch corpora is not redistributed here.</div>'''
             if A.demo_theme and not A.theme_private else '''<div class="note"><strong>Data handling.</strong> This page contains verbatim
patient/participant text and is <strong>local-only tier</strong>: keep it on local machines
and approved infrastructure — no cloud storage, no external API, no artifact host. Rephrase
before publication.</div>''')
candidate_heading = ('<h2 id="candidates">The ranked candidates</h2>\n'
                     '<p class="lede">Rank 1 is the first expression a reviewer would meet. '
                     'Use the controls to narrow the list, and open any row to read the '
                     'expression in context.</p>'
                     if A.demo_theme and A.stage == "explore" else '<h2>Candidates</h2>')
label_mode_js = ('''const labelToggle = document.getElementById('labelToggle');
function setLabelling(on) {
  document.body.classList.toggle('labelling', on);
  labelToggle.setAttribute('aria-pressed', String(on));
  labelToggle.textContent = on ? 'Return to explore mode' : 'Switch to labelling';
}
labelToggle.onclick = () => setLabelling(!document.body.classList.contains('labelling'));
setLabelling(Object.keys(L).length > 0);'''
                 if A.demo_theme and A.stage == "explore" else '')
dataset_strip = ""
if A.demo_theme and A.stage == "explore" and not A.theme_private:
    reframe_count = sum(1 for r in chosen if r["stratum"] == "ReframeCovid")
    menu_phrase_count = sum(1 for r in chosen if r["cls"] == "plant")
    dataset_strip = f'''
<aside class="dataset-strip" aria-labelledby="covid-data-title">
  <div>
    <p class="eyebrow">ABOUT THE PUBLIC DATA</p>
    <h2 id="covid-data-title">COVID-19 metaphors make the method inspectable.</h2>
    <p><strong>#ReframeCovid</strong> is a crowdsourced, multilingual collection of alternatives to war language and other ways of framing COVID-19. This demo uses its English entries because they may be redistributed. It is not a patient cohort and does not validate a cancer Menu. The extraction, checks, categories and ranking were added by this project—not by the original dataset publishers.</p>
  </div>
  <div class="dataset-summary">
    <span><strong>{reframe_count:,}</strong> #ReframeCovid expressions</span>
    <span><strong>{menu_phrase_count:,}</strong> phrases from Menu check items</span>
    <a href="https://docs.google.com/spreadsheets/d/1TZqICUdE2CvKqZrN67LcmKspY51Kug7aU8oGvK5WEbA/edit" target="_blank" rel="noopener">Open the original collection <span aria-hidden="true">&#8599;</span></a>
    <small>Reddit benchmark text is not reproduced.</small>
  </div>
</aside>'''
rank_logic = ""
if A.demo_theme and A.stage == "explore":
    tier_counts = {i: sum(1 for r in chosen if r["tier"] == i) for i in (0, 1, 2)}
    category_counts = Counter(
        VEH[r["id"]][0] for r in chosen
        if r["id"] in VEH and VEH[r["id"]][0]
        and VEH[r["id"]][0] not in {"Other (outside crosswalk)", "not metaphorical"})
    category_examples = "".join(
        f'<span>{html.escape(name)} <b>{count}</b></span>'
        for name, count in category_counts.most_common(3))
    rank_logic = f'''
<section class="rank-logic" aria-labelledby="rank-logic-title">
  <div>
    <p class="eyebrow">TWO WAYS TO EXPLORE</p>
    <h2 id="rank-logic-title">Rank by strength. Browse by pattern.</h2>
    <p>The ranking brings strong individual candidates forward. Category frequencies reveal recurring images across the list.</p>
  </div>
  <div class="output-routes">
    <div class="rank-route">
      <span class="route-label">Ranked view</span>
      <ol class="tier-key">
        <li class="tier-top"><span>First</span><strong>{tier_counts[0]:,}</strong><p>illness + lived experience</p></li>
        <li><span>Next</span><strong>{tier_counts[1]:,}</strong><p>about illness</p></li>
        <li><span>Last</span><strong>{tier_counts[2]:,}</strong><p>remaining candidates</p></li>
      </ol>
    </div>
    <a class="category-route" href="#veh">
      <span class="route-label">Category view</span>
      <strong>Recurring images</strong>
      <p>Frequency shows patterns worth inspecting; it does not make an image better.</p>
      <div class="category-preview">{category_examples}</div>
      <span class="route-link">Browse categories &#8595;</span>
    </a>
  </div>
  <a class="rank-method-link" href="index.html#approach">See how the prompts work <span aria-hidden="true">&#8594;</span></a>
</section>'''
# ---- "How this list was made" — provenance the reviewer can see -----------------
prov_box = ""
if A.provenance:
    steps = [x.strip() for x in A.provenance.split("||") if x.strip()]
    if A.stage == "filter":
        _deep = len(chosen) - min(A.filter_top, len(chosen))
        steps.append(
            (f"This page: the {STREAM_NAME} candidates only — " if STREAM_NAME else "This page: ")
            + f"the {min(A.filter_top, len(chosen))} highest-placed candidates in the system's "
              f"ordering, plus {_deep} drawn unseen from deeper down the list, shuffled together "
              f"— {len(chosen)} rows in all (identical phrasings merged). Nothing is discarded: "
              f"the other candidates remain in the ranked list and in the project team's "
              f"working copy.")
    elif A.stage == "vote":
        steps.append(f"This page: the {len(chosen)} expressions researchers passed on in "
                     f"stage 1, shuffled, with no ordering information.")
    else:
        steps.append(f"This page: the full ranked list, all {N:,} candidates, with every "
                     f"screen verdict and filter.")
    prov_box = ('<details id="how"><summary>More about this page and how the list was made</summary>'
                f'<div id="purpose">{purpose}</div><p class="lede">{lede}</p><ol>'
                + "".join(f"<li>{html.escape(t)}</li>" for t in steps) + "</ol></details>")
else:
    prov_box = ('<details id="how"><summary>More about this page</summary>'
                f'<div id="purpose">{purpose}</div><p class="lede">{lede}</p></details>')

if A.blind:
    rank_filters = ('<span style="display:none"><select id="fs"></select>'
                    '<select id="ft"></select><select id="fp"></select>'
                    '<select id="fm"></select><select id="fv"></select><select id="fc"></select></span>')
else:
    rank_filters = (
        f'<label>{html.escape(A.stratum_noun)} <select id="fs">'
        f'<option value="">all</option>{opts}</select></label>'
        f'<label>screen result <select id="ft"><option value="">all</option>'
        f'<option value="0">illness + lived experience</option>'
        f'<option value="1">about illness</option>'
        f'<option value="2">remaining candidates</option></select></label>'
        + (('<label>source domain <select id="fv"><option value="">all</option>'
            + "".join(f'<option value="{html.escape(k)}">{html.escape(k)} ({c})</option>'
                      for k, c in sorted(Counter(
                          VEH[r["id"]][0] for r in chosen
                          if r["id"] in VEH and VEH[r["id"]][0]).items(), key=lambda kv: -kv[1]))
            + '</select></label>') if VEH else '')
        + (('<label>USAS code <select id="fc"><option value="">all</option>'
            + "".join(f'<option value="{html.escape(k)}">{html.escape(k)} — {html.escape(_CD.get(k.rstrip("+-"), ""))} ({c})</option>'
                      for k, c in sorted(Counter(
                          VEH[r["id"]][2] for r in chosen
                          if r["id"] in VEH and VEH[r["id"]][2]).items(), key=lambda kv: -kv[1]))
            + '</select></label>') if VEH else '')
        + (f'<label>expression <select id="fm"><option value="">all</option>'
           f'<option value="1">with a comparison marker</option>'
           f'<option value="0">without</option></select></label>' if SIMILE else '')
        + f'<label>provenance <select id="fp"><option value="">all</option>'
        f'<option value="new">found only by target-screening</option>'
        f'<option value="both">also found by {html.escape(A.old_label)}</option>'
        f'<option value="plant">planted items</option></select></label>')

veh_section = ""
if (VEH or LAYERS) and not A.blind:
    _ids = {r["id"] for r in chosen}
    _n_usas = sum(1 for i in _ids if i in VEH)
    _n_lay = sum(1 for i in _ids if i in LAYERS)
    _nl = lambda k: sum(1 for i in _ids if LAYERS.get(i, {}).get(k))   # per-layer coverage (FrameNet is English-only)
    _n_llm = sum(1 for i in _ids if LAYERS.get(i, {}).get("llm"))
    _n_c1 = sum(1 for i in _ids if LAYERS.get(i, {}).get("llm_c1"))
    _n_c2 = sum(1 for i in _ids if LAYERS.get(i, {}).get("llm_c2"))
    _fa = VEH_NAMES[0] if VEH_NAMES else "model A"
    _fb = VEH_NAMES[1] if len(VEH_NAMES) > 1 else ""
    _n_usas2 = sum(1 for i in _ids if i in VEH2)
    _n_agree = sum(1 for i in _ids if i in VEH and i in VEH2 and VEH[i][2] == VEH2[i][2])
    _opts = [("usas", "USAS codes (main code › sub-codes)", _n_usas), ("veh", "USAS category (Demmen-style)", _n_usas),
             ("head", "head word of the vehicle", _nl("head")), ("wn1", "WordNet hypernym", _nl("wn1")),
             ("wn2", "WordNet, two levels up", _nl("wn2")), ("fn", "FrameNet frame", _nl("fn")),
             ("llm", "concept named by a local model (as labelled)", _n_llm),
             ("llm_c1", "model concept — near-duplicates merged", _n_c1),
             ("llm_c2", "model concept — broader groups", _n_c2)]
    _fam_sel = ""
    if _fb:
        _fam_sel = (f'<div class="ctlrow"><label>USAS tags from model <select id="vfam"><option value="a">{html.escape(_fa)}</option>'
                    f'<option value="b">{html.escape(_fb)}</option>'
                    f'<option value="agree">both models agree ({_n_agree} rows)</option></select></label></div>')
    _sub_default = ""                                   # default view: USAS category alone
    _top_default = "veh" if _n_usas else ("head" if _n_lay else "")
    _sel = "".join(f'<option value="{k}"{" disabled" if not n else ""}{" selected" if k == _top_default else ""}>'
                   f'{lbl}{"" if n else " — not computed yet"}</option>' for k, lbl, n in _opts)
    try:
        _alltags = json.loads((Path(__file__).resolve().parent / "usas_tags.json")
                              .read_text(encoding="utf-8"))
    except Exception:
        _alltags = {}
    _used = {v[2] for v in list(VEH.values()) + list(VEH2.values()) if v[2]}
    _used |= {m.group(0) for c in list(_used) for m in [re.match(r"[A-Z]+\d*", c)] if m}
    CODE_DESC = {c: str(_alltags.get(c.rstrip("+-"), "")).lower() for c in sorted(_used)}
    code_desc_js = json.dumps(CODE_DESC, ensure_ascii=False)
    _sel2 = '<option value="">— nothing —</option>' + "".join(
        f'<option value="{k}"{" disabled" if not n else ""}{" selected" if k == _sub_default else ""}>{lbl}</option>'
        for k, lbl, n in _opts if k != "usas")
    veh_section = (f'<div id="veh"><h2>What illness is compared to</h2>'
                   f'<p class="lede">Explore the image each metaphor borrows. Group candidates by a broad '
                   f'category, a key word, WordNet or FrameNet, or a concept named by a local model. Counts use '
                   f'the top <em>X</em> candidates; set <em>X</em> to the total for the full list. Click a row '
                   f'to filter the candidates below.</p>'
                   f'<div id="vehctl">{_fam_sel}<div class="ctlrow"><label>group by <select id="vlayer">{_sel}</select></label> '
                   f'<label>then by <select id="vlayer2">{_sel2}</select></label> '
                   f'<label>top <input id="vtop" type="number" min="1" max="{len(chosen)}" value="{len(chosen)}" size="5"> of {len(chosen):,}</label> '
                   f'<span id="vcov" style="color:var(--mut)"></span>'
                   f'<button id="vclear" title="show all candidates again">&times; clear filter</button></div></div>'
                   f'<div class="tw"><table id="vtab"></table></div></div>'
                   f'<script>const CODE_DESC = {code_desc_js}; const FAM = {json.dumps([_fa, _fb])};</script>')

page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="Explore real metaphor candidates and the human review workflow used to evaluate them.">
<title>{html.escape(A.corpus)} — {mode_title}</title><style>
:root {{ --ink:#1a1a1a; --mut:#5f5f5f; --line:#e2e2e2; --bg:#fff; --card:#fafafa;
  --acc:#2a78d6; --warn:#c2571f; --ok:#1a7f4b; --alt:#7a4fc9; }}
/* colour code, identical on every page of the workflow:
   blue = planted known-good check item (and the reader's own selections),
   green = passed both screens, orange = rejected by the topic screen / disregard,
   purple = found only by target-screened retrieval, grey = descriptive. */
@media (prefers-color-scheme: dark) {{ :root {{ --ink:#e8e8e8; --mut:#a0a0a0; --line:#333;
  --bg:#151515; --card:#1e1e1e; }} }}
body {{ font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  color:var(--ink); background:var(--bg); max-width:880px; margin:0 auto; padding:24px 20px; }}
h1 {{ font-size:21px; margin:0 0 4px; }} h2 {{ font-size:15px; margin:26px 0 8px; }}
.lede {{ color:var(--mut); font-size:14px; margin:0 0 16px; }}
table {{ border-collapse:collapse; width:100%; font-size:13.5px; margin-bottom:6px; }}
th,td {{ text-align:right; padding:6px 8px; border-bottom:1px solid var(--line); }}
th:first-child, td:first-child {{ text-align:left; }}
th {{ color:var(--mut); font-weight:600; font-size:12px; }}
tr.hi td {{ font-weight:700; color:var(--acc); }}
.tw {{ overflow-x:auto; }}
.note {{ border-left:3px solid var(--warn); padding:9px 13px; background:var(--card);
  border-radius:0 8px 8px 0; font-size:13.5px; margin:14px 0; }}
#purpose {{ border:1px solid var(--line); border-left:4px solid var(--acc);
  border-radius:0 8px 8px 0; padding:11px 15px; margin:0 0 18px;
  background:var(--card); font-size:13.5px; color:var(--mut); }}
#purpose strong {{ color:var(--ink); }}
#how {{ border:1px solid var(--line); border-radius:9px; padding:9px 14px; margin:0 0 16px;
  background:var(--card); font-size:13.5px; }}
#how summary {{ color:var(--ink); font-weight:600; cursor:pointer; font-size:13.5px; }}
#how ol {{ margin:8px 0 2px; padding-left:22px; color:var(--mut); }}
#how li {{ margin-bottom:6px; }}
#rater {{ border:1px solid var(--acc); border-radius:9px; padding:12px 14px; margin:16px 0;
  background:var(--card); }}
#rater input, #rater select {{ font:inherit; padding:5px 8px; border-radius:6px;
  border:1px solid var(--line); background:var(--bg); color:var(--ink); margin-right:8px; }}
#bar {{ position:sticky; top:0; background:var(--bg); border-bottom:1px solid var(--line);
  padding:10px 0; display:flex; gap:9px; flex-wrap:wrap; align-items:center;
  font-size:13px; z-index:5; }}
select, button {{ font:inherit; padding:5px 9px; border:1px solid var(--line);
  border-radius:6px; background:var(--card); color:var(--ink); cursor:pointer; }}
#count {{ color:var(--mut); margin-left:auto; }}
.row {{ border-bottom:1px solid var(--line); padding:11px 0; }}
.row.done {{ border-left:3px solid var(--ok); padding-left:9px; }}
.meta {{ display:flex; gap:6px; flex-wrap:wrap; align-items:center; margin-bottom:4px; }}
.rank {{ font-weight:700; color:var(--mut); font-size:12px; min-width:52px; }}
.pill {{ font-size:11px; padding:2px 7px; border-radius:10px; background:var(--card);
  border:1px solid var(--line); color:var(--mut); }}
.pill.s0 {{ border-color:var(--ok); color:var(--ok); }}
.pill.s2 {{ border-color:var(--warn); color:var(--warn); }}
.pill.plant {{ border-color:var(--acc); color:var(--acc); font-weight:700; }}
.pill.new {{ border-color:var(--alt); color:var(--alt); font-weight:700; }}
.pill.sim, .pill.veh, .pill.old {{ border-color:var(--mut); }}
.stages {{ display:flex; gap:8px; flex-wrap:wrap; margin:0 0 14px; }}
.stages .st {{ border:1px solid var(--line); border-radius:8px; padding:6px 11px;
  font-size:13px; color:var(--mut); background:var(--card); }}
.stages .st b {{ font-size:17px; margin-right:5px; color:var(--mut); }}
.stages .st small {{ display:block; font-size:11px; }}
.stages .st.cur {{ border:2px solid var(--acc); color:var(--ink); }}
.stages .st.cur b {{ color:var(--acc); }}
.legend {{ display:flex; gap:8px; flex-wrap:wrap; font-size:12.5px; color:var(--mut);
  margin:0 0 10px; }}
.phrase {{ font-size:17px; font-weight:600; }}
.phrase .pill.cnt {{ margin-left:8px; vertical-align:middle; border-color:var(--acc); color:var(--acc); font-weight:600; }}
summary {{ color:var(--acc); font-size:12px; cursor:pointer; margin-top:4px; }}
.ctx {{ color:var(--mut); font-size:13px; border-left:2px solid var(--line);
  padding-left:9px; margin:6px 0 0; }}
mark {{ background:transparent; color:var(--ink); font-weight:700; border-bottom:2px solid var(--acc); }}
.status {{ margin:10px 0 16px; padding:14px 18px; border:2px solid var(--acc); border-radius:8px;
  background:var(--card); }}
.status .l1 {{ font-size:20px; line-height:1.3; }}
.status .l2 {{ font-size:17px; margin-top:6px; }}
.status .l3 {{ color:var(--mut); margin-top:6px; font-size:14px; }}
.status b {{ color:var(--acc); }}
#veh table td:first-child {{ cursor:pointer; }}
#vehctl {{ margin:6px 0 10px; }}
#vehctl .ctlrow {{ display:flex; gap:16px; flex-wrap:wrap; align-items:center; margin-bottom:8px; }}
#vtab tr.sub td {{ font-size:13.5px; color:var(--mut); border-top:none; padding-top:2px; padding-bottom:2px; }}
#vtab tr.sub td:first-child {{ padding-left:28px; color:var(--ink); }}
#vtab tr.grp td {{ font-weight:600; }}
#vtab tr.more td {{ padding-left:28px; font-size:12.5px; color:var(--acc); cursor:pointer; border-top:none; }}
#vtab .bar {{ display:inline-block; height:10px; background:var(--acc); opacity:.55; vertical-align:middle; }}
#veh .codes span {{ display:inline-block; margin:0 6px 2px 0; cursor:pointer; color:var(--acc); }}
#veh tr.on td {{ font-weight:700; background:rgba(42,120,214,.14); }}
#vclear {{ display:none; margin-left:12px; padding:3px 10px; border:1px solid var(--acc); color:var(--acc);
  border-radius:12px; cursor:pointer; font-size:13px; background:transparent; }}
#vclear.show {{ display:inline-block; }}
.lbl {{ margin-top:7px; display:flex; gap:6px; flex-wrap:wrap; }}
.lbl button {{ font-size:12.5px; padding:4px 10px; }}
.lbl button.sel {{ background:var(--acc); color:#fff; border-color:var(--acc); }}
textarea {{ width:100%; height:110px; margin-top:10px; display:none;
  font-family:ui-monospace,monospace; font-size:12px; }}
</style>{theme_link}</head><body{' class="' + body_class + '"' if body_class else ''}>

{site_header}
{stage_strip}
{dataset_strip}
{rank_logic}
<h1>{html.escape(A.corpus)} — {mode_title}</h1>
{status_block}
{veh_section}
{prov_box}

<div id="rater">
  <strong>{"Optional labelling mode" if A.demo_theme and A.stage == "explore" else "Before you start — who is labelling?"}</strong><br>
  <label>Name <input id="rname" placeholder="your name" size="18"></label>
  {role_field}
  <span id="rstate" style="color:var(--mut);font-size:13px"></span>
  <p class="lede" style="margin:8px 0 0">Your labels are saved in this browser and never
  leave it until you press <em>Export</em>. The exported file contains <strong>only
  candidate numbers and your verdicts — no quoted text</strong>, so it is safe to email back
  for merging.</p>
</div>

{"" if A.blind else "<h2>How the ranking behaved on this corpus</h2>"}
<div class="tw"><table>
<tr><th></th><th>items</th><th>verify-keep</th><th>experiential</th><th>median rank</th>
<th>top 10%</th><th>bottom half</th></tr>{plant_row}
<tr><td>Pool</td><td>{po['n']:,}</td><td>{po['keep']:.1f}%</td><td>{po['exp']:.1f}%</td>
<td>{po['median']:,}</td><td>{po['top10']:.1f}%</td><td>{po['bottom']:.1f}%</td></tr>
</table></div>
{plant_block}{prov_block}

<h2>By {html.escape(A.stratum_noun)}</h2>
<div class="tw"><table>
<tr><th>{html.escape(A.stratum_noun)}</th><th>items</th><th>verify-keep</th>
<th>experiential</th><th>median rank</th></tr>{str_rows}</table></div>

{score_note}<div class="note" style="display:none"><strong>x</strong> Menu-likeness scores are
compressed near the bottom of the 0–10 range (mean {st.mean(scores):.2f}, median
{st.median(scores):.1f}), so position near the top rests on the screens rather than on score
differences. Planted items are translations and may read more formally than spontaneous
language.</div>

{data_note}

{candidate_heading}
{"" if A.blind else '<div class="legend"><span class="pill plant">known-good check</span>'
 '<span class="pill s0">illness + lived experience</span><span class="pill s1">about illness</span>'
 '<span class="pill s2">remaining candidate</span>'
 '<span class="pill new">target-screened only</span>'
 '<span class="pill old">descriptive (source, register, domain, marker)</span></div>'}
<div id="bar">
  {rank_filters}
  <label>show <select id="fl"><option value="">everything</option>
    <option value="todo">unlabelled only</option>
    <option value="yes">labelled: belongs</option>
    <option value="maybe">labelled: maybe</option></select></label>
  <label>search <input id="fq" placeholder="any word" size="14"></label>
  <button id="fr">reset</button><button id="ex">Export labels</button>
  <span id="count"></span></div>
{''.join(rows_html)}
<textarea id="out"></textarea>
<script>
const KEY = "labels::{html.escape(A.corpus)}";
let L = {{}};
try {{ L = JSON.parse(localStorage.getItem(KEY) || "{{}}"); }} catch(e) {{ L = {{}}; }}
const rn = document.getElementById('rname'), rr = document.getElementById('rrole');
try {{ rn.value = localStorage.getItem(KEY+"::name") || "";
       rr.value = localStorage.getItem(KEY+"::role") || ""; }} catch(e) {{}}
function saveRater() {{
  try {{ localStorage.setItem(KEY+"::name", rn.value);
         localStorage.setItem(KEY+"::role", rr.value); }} catch(e) {{}}
  document.getElementById('rstate').textContent =
    (rn.value && rr.value) ? "\\u2713 saved" : "name and role needed before exporting";
}}
rn.oninput = saveRater; rr.onchange = saveRater; saveRater();

const rows = [...document.querySelectorAll('.row')];
function paint(r) {{
  const id = r.dataset.id, v = L[id];
  r.classList.toggle('done', !!v);
  r.querySelectorAll('.lbl button').forEach(b =>
    b.classList.toggle('sel', b.dataset.v === v));
}}
document.querySelectorAll('.lbl').forEach(g => g.addEventListener('click', ev => {{
  const b = ev.target.closest('button'); if (!b) return;
  const id = g.dataset.for;
  L[id] = (L[id] === b.dataset.v) ? undefined : b.dataset.v;
  if (L[id] === undefined) delete L[id];
  try {{ localStorage.setItem(KEY, JSON.stringify(L)); }} catch(e) {{}}
  paint(g.closest('.row')); apply();
}}));

function apply() {{
  const s = document.getElementById('fs').value, t = document.getElementById('ft').value,
        p = document.getElementById('fp').value, l = document.getElementById('fl').value,
        mk = (document.getElementById('fm')||{{value:''}}).value,
        vh = (document.getElementById('fv')||{{value:''}}).value,
        vc = (document.getElementById('fc')||{{value:''}}).value,
        q = (document.getElementById('fq')||{{value:''}}).value.trim().toLowerCase();
  let n = 0;
  for (const r of rows) {{
    const v = L[r.dataset.id];
    const ok = (!s || r.dataset.stratum === s) && (!t || r.dataset.tier === t)
      && (!p || r.dataset.prov === p) && (!mk || r.dataset.simile === mk) && (!vh || r.dataset.veh === vh)
      && (!vc || r.dataset.vehcode === vc) && (!q || r.textContent.toLowerCase().includes(q))
      && GX.every(g => (r.dataset[g.layer] || '(no label)') === g.val)
      && (!l || (l === 'todo' ? !v : v === l));
    r.style.display = ok ? '' : 'none'; if (ok) n++;
  }}
  document.getElementById('count').textContent =
    n + ' shown \\u00b7 ' + Object.keys(L).length + ' labelled'
    + (GX.length ? ' \\u00b7 filter: ' + gxLabel() : '');
}}
['fs','ft','fp','fl','fm','fv','fc'].forEach(i => {{ const el=document.getElementById(i); if(el) el.onchange = apply; }});
{{ const fq = document.getElementById('fq'); if (fq) fq.oninput = apply; }}
let GX = [];   // active source-domain filter: [{{layer, val}}, ...] (outer, inner)
const LAYER_NAME = {{usas:'USAS codes', veh:'USAS category', vehmain:'USAS main code', vehcode:'USAS sub-code',
                     catagree:'USAS category (agreed)', codeagree:'USAS code (agreed)', head:'head word',
                     wn1:'WordNet hypernym', wn2:'WordNet 2-up', fn:'FrameNet frame', llm:'model concept',
                     llm_c1:'model concept (merged)', llm_c2:'model concept (broad)'}};
const CODE_LAYERS = new Set(['vehcode', 'vehcodeb', 'codeagree', 'vehmain', 'vehmainb', 'mainagree']);
const USAS_LAYERS = new Set(['veh','vehmain','vehcode']);
function famKey(layer) {{   // which data attribute holds this layer for the chosen model family
  if (!USAS_LAYERS.has(layer)) return layer;
  const f = (document.getElementById('vfam') || {{value:'a'}}).value;
  if (f === 'b') return layer + 'b';
  if (f === 'agree') return {{veh:'catagree', vehmain:'mainagree', vehcode:'codeagree'}}[layer];
  return layer;
}}
function famName() {{
  const el = document.getElementById('vfam'); if (!el) return '';
  return ' (' + el.options[el.selectedIndex].text.replace(/ \\(.*\\)$/, '') + ')';
}}
const SHOW_SUB = 8;                      // sub-rows shown per group before "more"
const OPEN = new Set();                  // groups expanded to show all sub-rows
function gxHas(layer, val) {{ return GX.some(g => g.layer === layer && g.val === val); }}
const BASE = {{vehb:'veh', vehmainb:'vehmain', vehcodeb:'vehcode', catagree:'veh', mainagree:'vehmain', codeagree:'vehcode'}};
function gxLabel() {{ return GX.map(g => LAYER_NAME[BASE[g.layer] || g.layer] + ' = ' + g.val).join(' \u203a '); }}
function esc(s) {{ return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;'); }}
function show(layer, v) {{   // display label: USAS codes get their description
  if (!CODE_LAYERS.has(layer) || typeof CODE_DESC === 'undefined') return esc(v);
  const d = CODE_DESC[v] || CODE_DESC[v.replace(/[+-]+$/, '')] || '';
  return esc(v) + (d ? ' <span style="color:var(--mut);font-weight:400"> \u2014 ' + esc(d)
    + (/[+-]$/.test(v) ? ' (' + (v.endsWith('+') ? 'positive' : 'negative') + ' pole)' : '') + '</span>' : '');
}}
function levelsFor() {{   // the data attributes that make up the table's levels, outer to inner
  const g1 = document.getElementById('vlayer').value;
  const g2 = (document.getElementById('vlayer2') || {{value:''}}).value;
  const lv = g1 === 'usas' ? ['vehmain', 'vehcode'] : [g1];
  if (g2 && g2 !== g1) lv.push(g2);
  return lv.map(famKey);
}}
function levelName(k) {{ return LAYER_NAME[BASE[k] || k] || k; }}
function group(list, key) {{
  const m = new Map();
  for (const r of list) {{ const v = r.dataset[key] || '(no label)'; if (!m.has(v)) m.set(v, []); m.get(v).push(r); }}
  return [...m.entries()].sort((a, b) => b[1].length - a[1].length);
}}
function pathOn(path) {{ return path.length === GX.length && path.every((g, i) => GX[i].layer === g.layer && GX[i].val === g.val); }}
function buildVeh() {{
  const tab = document.getElementById('vtab'); if (!tab) return;
  const LV = levelsFor();
  const X = parseInt(document.getElementById('vtop').value) || rows.length;
  const inTop = rows.filter(r => {{ const rk = parseInt(r.dataset.rank); return rk && rk <= X; }});
  const labelled = inTop.filter(r => r.dataset[LV[0]]);
  const max = Math.max(1, ...group(labelled, LV[0]).map(([, l]) => l.length));
  let h = '<tr><th>' + LV.map(levelName).join(' \u203a ') + (USAS_LAYERS.has(BASE[LV[0]] || LV[0]) ? famName() : '')
        + '</th><th>n</th><th>%</th><th></th></tr>';
  let distinct = 0;
  const render = (list, depth, path, parentN, parentLabel) => {{
    const key = LV[depth];
    let items = group(list, key);
    if (depth > 0 && items.length === 1 && items[0][0] === path[path.length - 1].val)   // sub-code = main code: skip the level
      return depth + 1 < LV.length ? render(list, depth + 1, path, parentN, parentLabel) : '';
    if (depth === 0) distinct = items.length;
    const okey = path.map(g => g.val).join('\u241f');
    const lim = (depth === 0 || OPEN.has(okey)) ? items.length : SHOW_SUB;
    let out = '';
    items.slice(0, lim).forEach(([v, l]) => {{
      if (depth === 0 && v === '(no label)') return;
      const p = path.concat([{{layer: key, val: v}}]);
      const share = depth === 0 ? (100 * l.length / labelled.length).toFixed(1) + '%'
                                : (100 * l.length / parentN).toFixed(0) + '% of ' + esc(parentLabel);
      out += '<tr class="' + (depth === 0 ? 'grp' : 'sub') + (pathOn(p) ? ' on' : '') + '" data-path="'
           + esc(JSON.stringify(p)) + '"><td style="padding-left:' + (depth * 22 + 8) + 'px">' + show(key, v)
           + '</td><td>' + l.length + '</td><td>' + share + '</td><td><span class="bar" style="width:'
           + Math.round(160 * l.length / max) + 'px;opacity:' + (depth ? .3 : .55) + '"></span></td></tr>';
      if (depth + 1 < LV.length) out += render(l, depth + 1, p, l.length, v);
    }});
    if (items.length > lim) out += '<tr class="more" data-open="' + esc(okey) + '"><td colspan="4" style="padding-left:'
      + (depth * 22 + 8) + 'px">+ ' + (items.length - lim) + ' more \u2026</td></tr>';
    else if (depth > 0 && OPEN.has(okey) && items.length > SHOW_SUB)
      out += '<tr class="more" data-close="' + esc(okey) + '"><td colspan="4" style="padding-left:' + (depth * 22 + 8) + 'px">show fewer</td></tr>';
    return out;
  }};
  h += render(labelled, 0, [], labelled.length, '');
  tab.innerHTML = h;
  document.getElementById('vcov').textContent = labelled.length + ' of the top ' + inTop.length
    + ' have a label at this level (' + distinct + ' distinct)';
  const vcl = document.getElementById('vclear');
  vcl.className = GX.length ? 'show' : ''; vcl.textContent = GX.length ? '\u00d7 clear filter: ' + gxLabel() : '';
  const go = () => {{ buildVeh(); apply(); document.getElementById('bar').scrollIntoView({{behavior:'smooth'}}); }};
  tab.querySelectorAll('tr[data-path]').forEach(tr => tr.onclick = () => {{
    const p = JSON.parse(tr.dataset.path);
    GX = pathOn(p) ? [] : p;
    ['fv','fc'].forEach(i => {{ const el = document.getElementById(i); if (el) el.value = ''; }}); go(); }});
  tab.querySelectorAll('tr.more').forEach(tr => tr.onclick = () => {{
    if (tr.dataset.open !== undefined) OPEN.add(tr.dataset.open); else OPEN.delete(tr.dataset.close); buildVeh(); }});
}}
{{ const vcl = document.getElementById('vclear');
   if (vcl) vcl.onclick = () => {{ GX = []; buildVeh(); apply(); }}; }}
{{ const vl = document.getElementById('vlayer'), vl2 = document.getElementById('vlayer2'), vt = document.getElementById('vtop');
   const vf = document.getElementById('vfam');
   if (vf) vf.onchange = () => {{ GX = []; OPEN.clear(); buildVeh(); apply(); }};
   if (vl) {{ vl.onchange = vl2.onchange = () => {{ GX = []; OPEN.clear(); buildVeh(); apply(); }};
             vt.oninput = buildVeh; buildVeh(); }} }}
document.getElementById('fr').onclick = () => {{
  ['fs','ft','fp','fl','fm','fv','fc','fq'].forEach(i => {{ const el=document.getElementById(i); if(el) el.value=''; }});
  GX = []; buildVeh(); apply(); }};
document.getElementById('ex').onclick = () => {{
  if (!rn.value || !rr.value) {{ alert("Please enter your name and role first."); return; }}
  // one label per shown row; identical phrasings were merged, so the same verdict is
  // written for every underlying candidate id (data-members) — the export stays ids + verdicts only
  const ALL = {{}};
  for (const r of rows) {{
    const v = L[r.dataset.id]; if (!v) continue;
    ALL[r.dataset.id] = v;
    try {{ for (const m of JSON.parse(r.dataset.members || "[]")) ALL[m] = v; }} catch(e) {{}}
  }}
  const blob = JSON.stringify({{
    corpus: {json.dumps(A.corpus)}, stage: {json.dumps(A.stage)}, stream: {json.dumps(STREAM_NAME)},
    rater: {{ name: rn.value, role: rr.value }},
    n_labelled: Object.keys(L).length, n_candidate_ids: Object.keys(ALL).length, labels: ALL }}, null, 1);
  const t = document.getElementById('out'); t.style.display = 'block'; t.value = blob; t.select();
  const u = URL.createObjectURL(new Blob([blob], {{type:'application/json'}}));
  const a = document.createElement('a');
  a.href = u; a.download = 'labels_' + rn.value.replace(/\\W+/g,'_') + '_' + rr.value + '.json';
  a.click();
}};
{label_mode_js}
rows.forEach(paint); apply();
</script></body></html>"""

(B / A.out).write_text(page, encoding="utf-8")
print(json.dumps({"corpus": A.corpus, "stream": STREAM_NAME or None, "rendered": len(chosen),
                  "rows_folded_under_them": sum(len(r.get("members", [])) for r in chosen),
                  "of_total": N,
                  "plants_included": sum(1 for r in chosen if r["cls"] == "plant"),
                  "strata": len(by_str),
                  "provenance": ({"also_in_old": n_old, "new": n_new} if old else "not compared"),
                  "path": str(B / A.out)}, indent=1))
