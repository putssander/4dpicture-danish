#!/usr/bin/env python3
"""Assemble the review app: ONE self-contained HTML page for every language and stage.

    build_review_app.py --css demo.css --out review.html            # start screen (file picker)
    build_review_app.py --css demo.css --bundle list.json --out x.html   # page with the list embedded

The page is review_app.html + review_i18n.json + review_app.js, with the theme stylesheet
inlined in a `<style data-theme="demo.css">` block (tests check that block against the
source stylesheet). review_page.py imports `embed_bundle()` to write the embedded variant.
"""
import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _safe_json(text):
    """JSON inside a <script> block must not contain '</' (would end the element)."""
    return text.replace("</", "<\\/")


def assemble(css_text, bundle_json="", title=None):
    tpl = (HERE / "review_app.html").read_text(encoding="utf-8")
    i18n = json.loads((HERE / "review_i18n.json").read_text(encoding="utf-8"))
    js = (HERE / "review_app.js").read_text(encoding="utf-8")
    theme = ('<style data-theme="demo.css">\n' + css_text + "\n</style>") if css_text else ""
    if title is None:
        title = "Metaphor review"
        if bundle_json:
            b = json.loads(bundle_json)
            title = f"{b.get('corpus', '')} — {i18n.get(b.get('lang', 'en'), i18n['en']).get('mode_' + b.get('stage', 'filter'), '')}"
    return (tpl.replace("__TITLE__", title.replace("<", "&lt;"))
               .replace("__THEME_CSS__", theme)
               .replace("__I18N__", _safe_json(json.dumps(i18n, ensure_ascii=False, separators=(",", ":"))))
               .replace("__BUNDLE__", _safe_json(bundle_json) if bundle_json else "")
               .replace("__APP_JS__", js))


def embed_bundle(bundle, css_path, out_path, title=None):
    css = Path(css_path).read_text(encoding="utf-8") if css_path and Path(css_path).exists() else ""
    bj = json.dumps(bundle, ensure_ascii=False, separators=(",", ":"))
    Path(out_path).write_text(assemble(css, bj, title), encoding="utf-8")
    return out_path


def build_loader(css_path, out_path):
    css = Path(css_path).read_text(encoding="utf-8") if css_path and Path(css_path).exists() else ""
    Path(out_path).write_text(assemble(css, "", None), encoding="utf-8")
    return out_path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--css", default="", help="theme stylesheet to inline (demo.css)")
    ap.add_argument("--bundle", default="", help="review bundle JSON to embed (omit for the start screen)")
    ap.add_argument("--out", required=True)
    A = ap.parse_args()
    if A.bundle:
        embed_bundle(json.loads(Path(A.bundle).read_text(encoding="utf-8")), A.css, A.out)
    else:
        build_loader(A.css, A.out)
    print(A.out)
