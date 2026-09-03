#!/usr/bin/env python3
"""Build the three-stage index page that fronts one language's review pages (runs anywhere).

Same layout in every language: three numbered stage cards (1 filtering, 2 voting,
3 retrospective), then background links, then what the data is. The page holds links
and explanation only — never candidate text — so it can sit beside private pages as well
as in the public demo. build_english_demo.py imports render_index(); for Danish and Dutch
run it over the directory that holds the stage pages:

  review_index.py --dir review_pages/da --title "Danish interviews and questionnaire" \\
      --data "Danish interviews and free-text questionnaire answers (private)"

A stage whose page is not there yet (stage 2 is produced only after stage-1 labels come
back) is shown as a card without a link.
"""

import argparse
import html
from pathlib import Path

CSS = """
:root { --ink:#1a1a1a; --mut:#5f5f5f; --line:#e2e2e2; --bg:#fff; --card:#fafafa; --acc:#2a78d6; }
@media (prefers-color-scheme: dark) { :root { --ink:#e8e8e8; --mut:#a0a0a0; --line:#333;
  --bg:#151515; --card:#1e1e1e; } }
body { font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; color:var(--ink);
  background:var(--bg); max-width:820px; margin:0 auto; padding:28px 20px; }
h1 { font-size:23px; margin:0 0 6px; } h2 { font-size:16px; margin:28px 0 10px; }
.lede { color:var(--mut); margin:0 0 20px; }
.card { display:block; border:1px solid var(--line); border-radius:10px; padding:15px 17px;
  margin-bottom:12px; text-decoration:none; color:inherit; background:var(--card); }
a.card:hover { border-color:var(--acc); }
.card.hero { border:2px solid var(--acc); margin:18px 0 26px; padding:18px 20px; }
.card.hero h3 { font-size:21px; }
.card.hero p { color:var(--ink); font-size:15px; }
.card h3 { margin:0 0 4px; font-size:17px; color:var(--acc); }
.card p { margin:0; color:var(--mut); font-size:14px; }
.who { font-size:12px; text-transform:uppercase; letter-spacing:.05em; color:var(--mut); }
.stage { display:grid; grid-template-columns:48px 1fr; column-gap:14px; align-items:start;
  border-width:2px; }
.stage .num { grid-row:1 / span 3; font-size:34px; font-weight:700; line-height:1;
  color:var(--acc); padding-top:2px; }
.stage h3 { font-size:19px; }
.stage.pending { opacity:.7; border-style:dashed; } .stage.pending h3 { color:var(--mut); }
.bg { background:transparent; padding:11px 15px; }
.bg h3 { font-size:15px; color:var(--ink); } .bg p { font-size:13px; }
.streams { display:block; margin-top:6px; color:var(--ink); }
.streams a { color:var(--acc); text-decoration:none; }
.note { border-left:3px solid var(--acc); padding:10px 14px; background:var(--card);
  border-radius:0 8px 8px 0; font-size:14px; }
"""

STAGES = [
    ("1", "Stage 1 · researchers", "Filtering",
     "Everything above a cut-off, plus a concealed sample from further down, shuffled together "
     "with the ranking hidden. Reviewers cannot tell which is which — which is what makes it "
     "possible to find out afterwards whether the ranking could be trusted."),
    ("2", "Stage 2 · PPI panel", "Voting",
     "Only what stage 1 passed on, shuffled, with no rank, no score and not even a position "
     "number. Several people vote independently; agreement is computed afterwards."),
    ("3", "Stage 3 · project team", "Retrospective",
     "After the votes are in: the full ranked list with scores, screen verdicts and filters, "
     "used to check where the expressions people kept had been sitting in the ranking — for "
     "example, whether everything that reached the menu was in the top few hundred. Not for "
     "collecting judgements."),
]
PENDING = {"2": "Not generated yet — this page is built from the stage-1 labels once they "
                "are back, so the panel only ever sees what researchers passed on."}


def card(num, who, title, text, href):
    """href: a path, a list of (label, path) for one stage split into streams, or None."""
    inner = (f'<span class="num">{num}</span><span class="who">{html.escape(who)}</span>'
             f'<h3>{html.escape(title)}</h3><p>{html.escape(text)}</p>')
    if isinstance(href, (list, tuple)) and href:
        links = " · ".join(f'<a href="{html.escape(h)}"><strong>{html.escape(l)}</strong></a>'
                           for l, h in href)
        return (f'<div class="card stage">{inner[:-4]} <span class="streams">One list per '
                f'source, each with its own cut: {links}</span></p></div>')
    if href:
        return f'<a class="card stage" href="{html.escape(href)}">{inner}</a>'
    return (f'<div class="card stage pending">{inner[:-4]} <em>{html.escape(PENDING[num])}'
            f'</em></p></div>')


def render_demo_index(title, lede, stage_hrefs, background, data_note, tag, page_title=None):
    """Themed landing page for a language's review pages: same shell as the public demo
    (demo.css must sit next to the pages). stage_hrefs as in render_index."""
    s1, s2, s3 = stage_hrefs.get("1"), stage_hrefs.get("2"), stage_hrefs.get("3")
    def s1_links():
        if isinstance(s1, (list, tuple)):
            return " &middot; ".join(f'<a href="{html.escape(h)}">{html.escape(l)}</a>' for l, h in s1)
        return ""
    def card(num, who, name, txt, href, links="", featured=False, pending=False):
        cls = "workflow-card" + (" featured" if featured else "")
        inner = (f'<span class="step-number">{num}</span><span class="step-audience">{who}</span>'
                 f'<h3>{name}</h3><p>{txt}</p>' + (f'<p>{links}</p>' if links else ''))
        if pending:
            return f'<div class="{cls}" style="opacity:.65">{inner}<span class="card-link">Prepared after stage 1</span></div>'
        if isinstance(href, str) and href:
            return f'<a class="{cls}" href="{html.escape(href)}">{inner}<span class="card-link">Open &#8594;</span></a>'
        return f'<div class="{cls}">{inner}</div>'
    cards = (card("01", "Researchers", "Filter",
                  "Review a shuffled sample from across the list. The hidden rank prevents the software's judgement from influencing the reviewers.",
                  s1 if isinstance(s1, str) else None, s1_links())
             + card("02", "PPI panel", "Vote",
                    "Decide independently which expressions belong on a menu. Rank and score remain hidden.",
                    s2, pending=not s2)
             + card("03", "Project team", "Retrospective",
                    "The full ranked list with every score and screen verdict, the reference items marked, and the source-domain tables.",
                    s3, featured=True))
    bgs = "".join(f'<a class="workflow-card" href="{html.escape(h)}"><span class="step-audience">{html.escape(w)}</span>'
                  f'<h3>{html.escape(x)}</h3><p>{html.escape(q)}</p><span class="card-link">Open &#8594;</span></a>'
                  for h, w, x, q in background)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(page_title or title)}</title>
<link rel="stylesheet" href="demo.css"></head><body class="demo-home">
<header class="site-header" aria-label="Navigation">
  <a class="brand" href="index.html"><span class="brand-mark" aria-hidden="true">M</span><span>Metaphor discovery</span></a>
  <span class="header-tag">{html.escape(tag)}</span>
</header>
<main>
<section class="home-hero"><div class="hero-copy">
  <p class="eyebrow">FROM EXTRACTION TO HUMAN DECISION</p>
  <h1>{html.escape(title)}</h1>
  <p class="hero-lede">{lede}</p>
  <div class="hero-actions"><a class="button primary" href="{html.escape(s3 or '#')}">Explore the ranked output <span aria-hidden="true">&#8599;</span></a></div>
</div></section>
<section class="section-block" id="workflow">
  <div class="section-heading"><div><p class="eyebrow">THE REVIEW WORKFLOW</p>
  <h2>Three views, each with a different job.</h2></div>
  <p>Stages one and two conceal the rank on purpose. Only after the independent decisions are complete does the project team see the system's ordering.</p></div>
  <div class="workflow-grid">{cards}</div>
</section>
{f'<section class="section-block"><div class="section-heading"><div><p class="eyebrow">BACKGROUND</p><h2>How the ranking was checked.</h2></div></div><div class="workflow-grid">{bgs}</div></section>' if bgs else ''}
<section class="section-block"><div class="note">{data_note}</div></section>
</main>
<footer class="site-footer">4D PICTURE &middot; private review pages &middot; keep on project machines</footer>
</body></html>"""


def render_index(title, lede, stage_hrefs, background, data_note, page_title=None):
    """stage_hrefs: {'1': href|None, '2': ..., '3': ...}; background: [(href, who, h3, p)]."""
    cards = "".join(card(n, who, t, txt, stage_hrefs.get(n))
                    for n, who, t, txt in STAGES)
    bgs = "".join(
        f'<a class="card bg" href="{html.escape(h)}"><span class="who">{html.escape(w)}</span>'
        f'<h3>{html.escape(t)}</h3><p>{html.escape(p)}</p></a>' for h, w, t, p in background)
    s3 = stage_hrefs.get("3")
    hero = (f'<a class="card hero" href="{html.escape(s3)}"><span class="who">start here</span>'
            f'<h3>&#9654; The ranked list — what the software found, best first</h3>'
            f'<p>Every candidate with its score and screen verdicts, the planted check items marked, and the '
            f'source-domain tables (USAS, head word, WordNet, model concept) to browse what illness is compared to. '
            f'Stages 1 and 2 below are the blinded review pages: they show the same candidates in random order '
            f'on purpose, so reviewers cannot see the ordering they are testing.</p></a>'
            if s3 else "")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(page_title or title)}</title><style>{CSS}</style></head><body>
<h1>{html.escape(title)}</h1>
<p class="lede">{lede}</p>
{hero}

<h2>The three stages</h2>
{cards}
{'<h2>Background</h2>' + bgs if bgs else ''}

<h2>Why the stages are separated</h2>
<div class="note">If reviewers see the ranking, their agreement with it proves nothing: they
would be confirming an order they were shown. And if they only ever see the top of the list,
a good expression buried lower can never be discovered. Both stages are therefore blind to
the ordering, and stage 1 deliberately includes material from deep in the list.</div>

<h2>What you are looking at</h2>
<p class="lede">{data_note}</p>
</body></html>"""


def find_stage_files(d):
    d = Path(d)
    pick = lambda suf: next((f.name for f in sorted(d.glob(f"*{suf}"))), None)
    s1 = sorted(d.glob("*_stage1_for_researchers*.html"))
    if len(s1) > 1:   # one page per source stream: label = the part after the audience
        s1 = [(f.stem.split("_stage1_for_researchers_", 1)[-1].replace("_", " ") or "all", f.name)
              for f in s1]
    else:
        s1 = s1[0].name if s1 else None
    return {"1": s1,
            "2": pick("_stage2_for_PPI_panel.html"),
            "3": pick("_working_copy_project_team.html")}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="directory holding the stage pages")
    ap.add_argument("--title", required=True)
    ap.add_argument("--data", required=True, help="one sentence: what corpus, what status")
    ap.add_argument("--lede", default=(
        "How candidate metaphors reach a decision: software proposes and orders candidates; "
        "people decide what belongs. Open the page for your stage — nothing to install, "
        "no sign-in; everything stays on this computer."))
    ap.add_argument("--background", nargs=4, action="append", default=[],
                    metavar=("HREF", "WHO", "TITLE", "TEXT"))
    ap.add_argument("--demo-theme", action="store_true",
                    help="use the public demo shell (demo.css next to the pages)")
    ap.add_argument("--theme-tag", default="Private review",
                    help="header tag for the themed shell")
    A = ap.parse_args()
    hrefs = find_stage_files(A.dir)
    out = Path(A.dir) / "index.html"
    render = (lambda *a, **k: render_demo_index(*a, tag=A.theme_tag, **k)) if A.demo_theme else render_index
    out.write_text(render(A.title, html.escape(A.lede), hrefs, A.background,
                          html.escape(A.data)), encoding="utf-8")
    print(f"{out}: " + ", ".join(f"stage {k}: {v or 'pending'}" for k, v in hrefs.items()))
