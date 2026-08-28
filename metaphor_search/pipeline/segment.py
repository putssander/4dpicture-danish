"""Step 1 — cut texts into short passages a reader can judge on their own.

Rule used in the project: split on sentence ends, take windows of three sentences, keep a
window when it has at least `min_words` words (25 for interviews and long posts; 8 for
short questionnaire answers). Deterministic, so re-running extends rather than reshuffles.

    from pipeline import segment
    segs = segment.from_texts({"doc1": "text ...", "doc2": "..."}, min_words=15)
    segment.save(segs, work / "segments.json")
"""
import json
import re
from pathlib import Path

SENT = re.compile(r"(?<=[.!?])\s+")
TAG = re.compile(r"<[^>]+>")


def windows(text, window=3, min_words=15, max_words=2000):
    clean = re.sub(r"\s+", " ", TAG.sub(" ", text)).strip()
    if len(clean.split()) > max_words:
        return []
    if len(clean.split()) < min_words:
        return []
    sents = [s.strip() for s in SENT.split(clean) if s.strip()]
    out = []
    for w in range(0, len(sents), window):
        piece = " ".join(sents[w:w + window])
        if len(piece.split()) >= min_words:
            out.append(piece)
    if not out and len(clean.split()) >= min_words:      # short text, no sentence marks
        out.append(clean)
    return out


def from_texts(texts, window=3, min_words=15, prefix=""):
    """texts: {doc_id: text}. Returns [[segment_id, passage], ...] with ids '<doc>_<n>'."""
    segs = []
    for doc_id in sorted(texts):
        for i, piece in enumerate(windows(texts[doc_id], window, min_words)):
            segs.append([f"{prefix}{doc_id}_{i}", piece])
    return segs


def from_folder(folder, glob="*.txt", **kw):
    """Every text file in a folder is one document (file stem = document id)."""
    folder = Path(folder)
    texts = {p.stem: p.read_text(encoding="utf-8", errors="ignore") for p in sorted(folder.glob(glob))}
    return from_texts(texts, **kw)


def save(segs, path):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"segments": segs}, ensure_ascii=False), encoding="utf-8")
    return {"segments": len(segs), "path": str(path)}


def load(path):
    return [tuple(s) for s in json.loads(Path(path).read_text(encoding="utf-8"))["segments"]]
