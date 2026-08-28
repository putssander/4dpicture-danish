"""Loader for the USAS-WSD gold evaluation data (Moore, Rayson et al. 2026).

Source: https://huggingface.co/datasets/ucrelnlp/USAS-WSD  (CC BY-NC-SA 4.0)
Paper:  https://arxiv.org/abs/2601.09648

Four languages of human-tagged or human-checked USAS data. **There is no Danish set** —
this is the closest available gold for validating a USAS tagging/lexicon method, by running
the method on a language that does have gold.

    Language  Texts  Tokens  Labelled  Multi-tag membership
    Chinese     46    2,312    1,747     1 (0%)      from scratch, 2 researchers, consensus
    English     73    3,899    3,468   212 (6.1%)    MT of Finnish, post-edited by a native speaker
    Finnish     72    2,439    2,068   254 (12.3%)   manually tagged original
    Welsh      611   14,876   12,800  1311 (10.2%)   corrected CyTag/CySemTagger output

Preprocessing follows the dataset card exactly, so token counts reproduce the published
table: punctuation tokens and the unmatched tag ``Z99`` are dropped, labels that cannot be
matched to the USAS tagset are dropped, and where a token carries several alternative
labels the first is used.

Note on *multi-tag membership*: a gold label such as ``I2.2/H1`` is ONE label asserting
membership of both fields (kaupan is both Business:Selling and Architecture). It is not a
list of alternatives. ``gold_fields`` therefore holds every field of the label, and a
prediction matching any of them is counted correct — see score_predictions().
"""

import csv
import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data" / "usas_wsd"
TAGSET = json.loads(
    (Path(__file__).resolve().parent / "data/usas_tags.json").read_text())

FILES = {
    "fin": "benedict_fin.txt",
    "eng": "benedict_eng.txt",
    "cym": "CorCenCC_cym.txt",
    "zho": "ToRCH2019_A26_zho.csv",
}
LANGUAGE_NAMES = {"fin": "Finnish", "eng": "English", "cym": "Welsh", "zho": "Chinese",
                  "dan": "Danish", "nld": "Dutch"}   # committee-built references

# published rule-based accuracy, for validating a reproduction (paper Table 12)
PUBLISHED_RULE_BASED = {"eng": 72.4, "cym": 70.6, "fin": 58.4, "zho": 32.6, "gle": 56.6}

PUNCT_MARKERS = {"PUNC", "PUNCT"}
UNMATCHED = "Z99"
# strip MWE markers: English "[i136.2.1", Finnish trailing "_i"
MWE_EN_RE = re.compile(r"\[i[\d.]+$")
CODE_RE = re.compile(r"^([A-Z]\d*(?:\.\d+)*)")


def _clean_label(label):
    """Strip MWE markers and whitespace from a raw gold label."""
    label = MWE_EN_RE.sub("", str(label).strip())
    if label.endswith("_i"):
        label = label[:-2]
    return label.strip()


def label_fields(label):
    """Split a USAS label into its constituent field codes.

    ``F4/S2mf`` -> ['F4', 'S2']  (dual membership: both fields are asserted)
    ``A1.8+``   -> ['A1.8']
    Markers (+ - m f n c i) and slashes are removed; only bare codes are returned.
    """
    out = []
    for part in _clean_label(label).split("/"):
        m = CODE_RE.match(part.strip())
        if m:
            out.append(m.group(1))
    return out


def _valid(fields):
    """A label is usable if at least one field is a real USAS tagset code."""
    return [f for f in fields if f in TAGSET]


def _add(rows, token, label, sent_id, lang):
    label = _clean_label(label)
    if not label or label in PUNCT_MARKERS or label.startswith(UNMATCHED):
        return
    # several alternative labels -> use the first (dataset card)
    first = label.split(";")[0]
    fields = _valid(label_fields(first))
    if not fields:
        return
    rows.append({"language": lang, "sent_id": sent_id, "token": token,
                 "gold_label": first, "gold_fields": fields})


def load_benedict(path, language):
    """Parse a benedict-format gold file (``token_TAG`` per token, one sentence per
    line) — the format of the Finnish/English gold and of LLM-committee-built gold
    for new languages (Danish, Dutch)."""
    rows = []
    sent_id = 0
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():              # blank lines are not sentences
            continue
        for annotated in line.split():
            # Finnish marks MWE membership with a trailing "_i" AFTER the tag
            # ("näppinsä_A1.8+_i"), so strip it before splitting off the label.
            if annotated.endswith("_i"):
                annotated = annotated[:-2]
            token, _, label = annotated.rpartition("_")
            if not token:                # no underscore: unlabelled token
                continue
            _add(rows, token, label, sent_id, language)
        sent_id += 1
    return rows


def load_usas_wsd(language, data_dir=DATA_DIR):
    """Load one language's gold data as a list of labelled-token dicts."""
    path = Path(data_dir) / FILES[language]
    rows = []

    if language in ("fin", "eng"):
        return load_benedict(path, language)

    elif language == "cym":
        for sent_id, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
            for annotated in line.split():
                parts = annotated.split("|")
                if len(parts) >= 7:
                    _add(rows, parts[0], parts[6], sent_id, language)

    elif language == "zho":
        sent_id = 0
        with path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                _add(rows, row["Token"], row.get("Corrected-USAS", ""), sent_id, language)
                if str(row.get("sentence-break", "")).strip().lower() == "true":
                    sent_id += 1
    else:
        raise ValueError(f"unknown language {language!r}; expected one of {list(FILES)}")

    return rows


def sentences(rows):
    """Group labelled tokens into sentences, preserving order."""
    out, current, cur_id = [], [], None
    for r in rows:
        if cur_id is not None and r["sent_id"] != cur_id:
            out.append(current)
            current = []
        cur_id = r["sent_id"]
        current.append(r)
    if current:
        out.append(current)
    return out


def usas_level(code, level=1):
    """Truncate a USAS code to a hierarchy level (see metaphor_extraction GRANULARITY.md)."""
    if not code:
        return ""
    code = str(code).strip().rstrip("+-")
    head = code.split(".")[0]
    alpha = "".join(c for c in head if c.isalpha())
    if level is None:
        return code
    if level <= 0:
        return alpha
    digits = head[len(alpha):]
    parts = ([digits] if digits else []) + code.split(".")[1:]
    return alpha + ".".join(parts[:level]) if parts[:level] else alpha


def score_predictions(rows, predictions, level=None):
    """Accuracy of predicted codes against the gold labels.

    ``predictions`` is a list parallel to ``rows``; each entry is a predicted code or a
    list of codes (an empty entry counts as wrong, never as a skip).

    A prediction is correct when it matches ANY field of the gold label, since a
    multi-membership label such as ``I2.2/H1`` asserts both fields. ``level`` truncates
    both sides to a USAS hierarchy level (None = exact codes, which is what the paper's
    n=1 accuracy uses).
    """
    correct = 0
    for row, pred in zip(rows, predictions):
        preds = [pred] if isinstance(pred, str) else list(pred or [])
        if not preds:
            continue
        gold = {usas_level(g, level) for g in row["gold_fields"]}
        if any(usas_level(p, level) in gold for p in preds if p):
            correct += 1
    return correct / len(rows) if rows else 0.0


def dataset_stats(data_dir=DATA_DIR):
    """Labelled-token counts per language, for checking against the published table."""
    stats = {}
    for lang in FILES:
        rows = load_usas_wsd(lang, data_dir)
        stats[lang] = {
            "language": LANGUAGE_NAMES[lang],
            "labelled_tokens": len(rows),
            "sentences": len(sentences(rows)),
            "multi_tag_membership": sum(1 for r in rows if len(r["gold_fields"]) > 1),
        }
    return stats
