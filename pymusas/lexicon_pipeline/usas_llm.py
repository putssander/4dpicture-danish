"""Shared LLM annotation machinery for USAS token tagging (used by the gold-eval
harness and the LLM-gold builder, so calibration and construction use IDENTICAL
prompts and parsing)."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import json
from pathlib import Path

TAGSET_PATH = Path(__file__).resolve().parent / "data/usas_tags.json"

LLM_PROMPT = """\
You are a semantic annotator using the USAS (UCREL Semantic Analysis System) tagset.
The full tagset (code: description) was provided above.

Assign ONE USAS code to every numbered token below, choosing the code whose semantic
field best fits the token's meaning IN THIS SENTENCE ({language} text). Use the most
specific applicable code (e.g. I1.1 rather than I1 when the token is about affluence).
Use Z5 for grammatical/function words, Z8 for pronouns, Z1/Z2/Z3 for proper names.

Tokens:
{tokens}

Return ONLY a JSON object mapping token numbers to codes, e.g. {{"1": "F2", "2": "A3+"}}.
"""

JUDGE_PROMPT = """\
You are adjudicating USAS semantic tags for {language} text. The full USAS tagset was
provided above. Two annotators disagreed on some tokens of this sentence.

Sentence tokens:
{tokens}

Disputed tokens (number: annotator A's code vs annotator B's code):
{disputes}

For each disputed token, decide which code is correct — or supply a better one. Return
ONLY a JSON object mapping token numbers to your final codes, e.g. {{"3": "B2"}}.
"""


def normalise(code):
    """Bare code: strip +/- polarity and m/f/n/c markers, keep first field of a/b lists."""
    import re
    m = re.match(r"^([A-Z]\d*(?:\.\d+)*)", str(code).strip().split("/")[0])
    return m.group(1) if m else ""


def make_llm(args):
    from llm_client import Client
    tagset = json.loads(TAGSET_PATH.read_text())
    system = ("You are an expert USAS semantic annotator.\n\nUSAS tagset:\n"
              + "\n".join(f"{k}: {v}" for k, v in tagset.items()))
    return Client(args.model), (Client(args.model2) if args.model2 else None), \
        (Client(args.judge) if args.judge else None), system


def llm_tag_sentence(client, system, sent, language):
    numbered = "\n".join(f"{i + 1}: {r['token']}" for i, r in enumerate(sent))
    parsed, _ = client.ask_json(
        LLM_PROMPT.format(language=language, tokens=numbered), system=system)
    out = {}
    if isinstance(parsed, dict):
        for k, v in parsed.items():
            try:
                out[int(k)] = normalise(v)
            except (ValueError, TypeError):
                continue
    return out
