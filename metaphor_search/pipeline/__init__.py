"""Metaphor search and ranking — the pipeline as a small library.

Steps (each a module, each callable from the notebooks or the command line):

    segment  — cut texts into 2–3-sentence passages            (no model)
    mine     — two local model families propose candidates      (Ollama)
    agree    — keep candidates BOTH families found               (no model)
    screens  — verify / experiential / register / score          (Ollama)
    rank     — composite ranking, nested-span collapse           (no model)
    report   — aggregate numbers only, never text                (no model)
    layers   — source-domain layers for the review page          (spaCy/WordNet/Ollama)
    page     — the blinded review pages (stage 1/2/3)            (no model)

Every step reads and writes plain JSON/JSONL files in one work directory, so a run can be
stopped and resumed, and every intermediate result can be inspected. Nothing here calls
a cloud API: the only model endpoint is an Ollama URL you configure.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
USAS_TAGS = HERE / "usas_tags.json"
