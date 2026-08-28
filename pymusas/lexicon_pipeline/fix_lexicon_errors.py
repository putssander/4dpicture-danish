#!/usr/bin/env python3
"""
Fix errors in the Danish pymusas lexicon files.

Phase 1 — ERROR DETECTION (fully programmatic, no LLM):
  All error detection is done with deterministic rules: string matching,
  counting, and set operations.  No LLM is involved in finding errors.

  Single Word Lexicon (SWL):
    1. Duplicate (lemma, POS) pairs with different semantic tags
    2. Multi-token lemmas (spaces in lemma field)

  Multi Word Expression Lexicon (MWE):
    1. POS-as-token: e.g. NOUN_NOUN instead of *_NOUN or actual_word_NOUN
    2. Single-word entries that belong in the SWL
    3. Excessive token repetition (likely LLM translation artifacts)
    4. nan entries (untranslated)

Phase 2 — ERROR CORRECTION (LLM-assisted where needed):
  Deterministic fixes (no retranslation):
    - Duplicates: keep first occurrence for each (lemma, POS) pair
    - POS-as-token in MWE: restore wildcard from English source
    - Single-word MWE: restore wildcards from English source

  Fixes requiring retranslation (skipped by default, enable with --retranslate):
    - Multi-token SWL lemmas, nan MWE entries, token-repetition MWE entries

Usage:
    python src/fix_lexicon_errors.py [--detect-only] [--batch-size 10] [--model qwen3:32b]
"""

import argparse
import copy
import json
import logging
import os
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import requests
from tqdm import tqdm

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
SWL_DA_PATH = BASE_DIR / "resources" / "Multilingual-USAS" / "Danish" / "semantic_lexicon_da.tsv"
MWE_DA_PATH = BASE_DIR / "resources" / "Multilingual-USAS" / "Danish" / "mwe_da.tsv"
SWL_EN_PATH = BASE_DIR / "resources" / "Multilingual-USAS" / "semantic_lexicon_en.tsv"
MWE_EN_PATH = BASE_DIR / "resources" / "Multilingual-USAS-en" / "mwe-en.tsv"

# Output paths (corrected files)
SWL_DA_OUT = BASE_DIR / "resources" / "Multilingual-USAS" / "Danish" / "semantic_lexicon_da_fixed.tsv"
MWE_DA_OUT = BASE_DIR / "resources" / "Multilingual-USAS" / "Danish" / "mwe_da_fixed.tsv"

VALID_POS = {
    "NOUN", "VERB", "ADJ", "ADV", "ADP", "DET", "PRON", "NUM",
    "SCONJ", "CCONJ", "PART", "INTJ", "PROPN", "AUX", "PUNCT", "SYM", "X",
}

LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Ollama helper
# ---------------------------------------------------------------------------
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")


def ollama_generate(prompt: str, model: str = "qwen3:32b", temperature: float = 0.2) -> str:
    """Call ollama generate API and return the response text."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": 4096},
    }
    try:
        resp = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=300)
        resp.raise_for_status()
        return resp.json().get("response", "")
    except requests.exceptions.RequestException as e:
        log.error("Ollama request failed: %s", e)
        return ""


def ollama_batch_json(prompt: str, model: str = "qwen3:32b") -> list | dict | None:
    """Call ollama and parse JSON from the response."""
    raw = ollama_generate(prompt, model=model)
    # Try to extract JSON from the response (may be wrapped in markdown code blocks)
    json_match = re.search(r"```(?:json)?\s*\n?(.*?)```", raw, re.DOTALL)
    text = json_match.group(1).strip() if json_match else raw.strip()
    # Also try to find JSON array or object directly
    for start_char, end_char in [("[", "]"), ("{", "}")]:
        idx_start = text.find(start_char)
        idx_end = text.rfind(end_char)
        if idx_start != -1 and idx_end != -1 and idx_end > idx_start:
            try:
                return json.loads(text[idx_start : idx_end + 1])
            except json.JSONDecodeError:
                continue
    # Last resort: try full text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        log.warning("Could not parse JSON from LLM response:\n%s", raw[:500])
        return None


# ---------------------------------------------------------------------------
# File I/O helpers
# ---------------------------------------------------------------------------
def load_swl(path: Path) -> list[dict]:
    """Load a single-word lexicon TSV.  Returns list of dicts with keys:
    line_num, index, lemma, pos, semantic_tags, (optional) extra columns."""
    entries = []
    with open(path, encoding="utf-8") as f:
        header = f.readline()  # skip header
        for line_num, line in enumerate(f, start=2):
            line = line.rstrip("\n")
            if not line:
                continue
            parts = line.split("\t")
            entry = {
                "line_num": line_num,
                "raw": line,
                "index": parts[0] if len(parts) > 0 else "",
                "lemma": parts[1] if len(parts) > 1 else "",
                "pos": parts[2] if len(parts) > 2 else "",
                "semantic_tags": parts[3] if len(parts) > 3 else "",
            }
            if len(parts) > 4:
                entry["extra"] = parts[4:]
            entries.append(entry)
    return entries


def load_mwe(path: Path) -> list[dict]:
    """Load a MWE lexicon TSV.  Returns list of dicts."""
    entries = []
    with open(path, encoding="utf-8") as f:
        header = f.readline()
        for line_num, line in enumerate(f, start=2):
            line = line.rstrip("\n")
            if not line:
                continue
            parts = line.split("\t")
            entry = {
                "line_num": line_num,
                "mwe_template": parts[0] if len(parts) > 0 else "",
                "semantic_tags": parts[1] if len(parts) > 1 else "",
                "raw": line,
            }
            entries.append(entry)
    return entries


def save_swl(entries: list[dict], path: Path):
    """Write corrected SWL file."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("\tlemma\tpos\tsemantic_tags\n")
        for i, e in enumerate(entries):
            f.write(f"{i}\t{e['lemma']}\t{e['pos']}\t{e['semantic_tags']}\n")
    log.info("Saved SWL (%d entries) to %s", len(entries), path)


def save_mwe(entries: list[dict], path: Path):
    """Write corrected MWE file."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("mwe_template\tsemantic_tags\n")
        for e in entries:
            f.write(f"{e['mwe_template']}\t{e['semantic_tags']}\n")
    log.info("Saved MWE (%d entries) to %s", len(entries), path)


# ===================================================================
# PHASE 1: Error Detection  (programmatic — NO LLM involved)
# ===================================================================

def detect_swl_duplicates(entries: list[dict]) -> dict[tuple, list[dict]]:
    """Find (lemma, pos) pairs that appear more than once with different semantic tags.
    Purely programmatic: groups entries by (lemma, pos) and checks for differing tags."""
    groups = defaultdict(list)
    for e in entries:
        groups[(e["lemma"], e["pos"])].append(e)
    duplicates = {}
    for key, group in groups.items():
        tags = set(e["semantic_tags"] for e in group)
        if len(tags) > 1:
            duplicates[key] = group
    return duplicates


def detect_swl_multi_token(entries: list[dict]) -> list[dict]:
    """Find entries where the lemma contains a space (multi-token).
    Purely programmatic: checks for whitespace in lemma string."""
    return [e for e in entries if " " in e["lemma"]]


def detect_mwe_pos_as_token(entries: list[dict]) -> list[dict]:
    """Find MWE entries where a POS tag is used as the word part, e.g. NOUN_NOUN.
    Purely programmatic: checks if word part matches a known POS tag."""
    errors = []
    for e in entries:
        template = e["mwe_template"]
        if template == "nan":
            continue
        for token in template.split():
            if "_" in token:
                word, pos = token.split("_", 1)
                if word in VALID_POS and pos in VALID_POS and word == pos:
                    errors.append(e)
                    break
    return errors


def detect_mwe_single_word(entries: list[dict]) -> list[dict]:
    """Find MWE entries that are actually single-word expressions.
    Purely programmatic: counts space-separated tokens in template."""
    results = []
    for e in entries:
        template = e["mwe_template"]
        if template == "nan":
            continue
        tokens = template.split()
        if len(tokens) == 1:
            results.append(e)
    return results


def detect_mwe_token_repetition(entries: list[dict], min_repeats: int = 3) -> list[dict]:
    """Find MWE entries with excessive token repetition.
    Purely programmatic: uses Counter to find tokens repeated >= min_repeats times."""
    results = []
    for e in entries:
        template = e["mwe_template"]
        if template == "nan":
            continue
        tokens = template.split()
        if len(tokens) >= min_repeats:
            counter = Counter(tokens)
            if any(cnt >= min_repeats for cnt in counter.values()):
                results.append(e)
    return results


def detect_mwe_nan(entries: list[dict]) -> list[dict]:
    """Find MWE entries where the template is 'nan' (untranslated).
    Purely programmatic: string equality check."""
    return [e for e in entries if e["mwe_template"] == "nan"]


# ===================================================================
# PHASE 2: Corrections  (deterministic or LLM-assisted)
# ===================================================================

def fix_swl_duplicates(duplicates: dict[tuple, list[dict]]) -> dict[tuple, str]:
    """Resolve duplicate (lemma, pos) entries deterministically.
    Keeps the first occurrence's semantic tags for each (lemma, pos) pair.
    Returns a dict mapping (lemma, pos) -> semantic_tags."""
    log.info("Fixing %d duplicate groups (keeping first occurrence)...", len(duplicates))
    resolved = {}
    for key, group in duplicates.items():
        resolved[key] = group[0]["semantic_tags"]
    return resolved


def fix_swl_multi_token(multi_token_entries: list[dict], model: str, batch_size: int) -> dict[int, dict]:
    """Use LLM to provide single-token Danish equivalents for multi-token lemmas.
    Returns dict mapping line_num -> corrected entry dict."""
    log.info("Fixing %d multi-token lemmas via LLM...", len(multi_token_entries))
    corrections = {}

    for i in tqdm(range(0, len(multi_token_entries), batch_size), desc="SWL multi-token"):
        batch = multi_token_entries[i : i + batch_size]
        batch_items = [
            {"line_num": e["line_num"], "lemma": e["lemma"], "pos": e["pos"], "semantic_tags": e["semantic_tags"]}
            for e in batch
        ]

        prompt = (
            "You are a linguistic expert in Danish.\n"
            "Below is a JSON array of Danish lexicon entries where each lemma contains multiple tokens (spaces).\n"
            "For a single-word lexicon, each lemma must be exactly ONE token (no spaces).\n\n"
            "For each entry, provide a corrected single-token Danish lemma that best captures the meaning.\n"
            "If the multi-token expression is actually a multi-word expression (e.g. 'afholde sig'), "
            "extract the main word (e.g. 'afholde').\n"
            "If it's a compound that should be written as one word in Danish (e.g. 'i flammer' → 'flammende'), "
            "provide the single-word form.\n"
            "Keep the POS and semantic_tags unchanged.\n\n"
            "IMPORTANT: Return ONLY a JSON array with keys: line_num, lemma, pos, semantic_tags\n"
            "Do NOT include any explanation outside the JSON.\n\n"
            f"Input:\n```json\n{json.dumps(batch_items, ensure_ascii=False, indent=2)}\n```\n"
        )

        result = ollama_batch_json(prompt, model=model)
        if isinstance(result, list):
            for item in result:
                ln = item.get("line_num")
                if ln is not None:
                    corrections[ln] = {
                        "lemma": item.get("lemma", ""),
                        "pos": item.get("pos", ""),
                        "semantic_tags": item.get("semantic_tags", ""),
                    }
        else:
            log.warning("Failed to parse LLM response for multi-token batch %d, keeping original", i)

    return corrections


def fix_mwe_pos_as_token(
    da_entries: list[dict],
    en_entries: list[dict],
    error_entries: list[dict],
) -> dict[int, str]:
    """Fix POS-as-token errors deterministically using English source.
    Replace e.g. NOUN_NOUN with *_NOUN based on English source pattern."""
    log.info("Fixing %d POS-as-token entries deterministically...", len(error_entries))
    corrections = {}

    for e in error_entries:
        ln = e["line_num"]
        # Find corresponding English entry (files are line-aligned)
        en_idx = ln - 2  # line_num is 1-based, header on line 1, data starts at line 2 → index 0
        if en_idx < 0 or en_idx >= len(en_entries):
            log.warning("No English source for MWE line %d", ln)
            continue

        en_template = en_entries[en_idx]["mwe_template"]
        da_template = e["mwe_template"]

        # Replace POS_POS tokens with *_POS (restoring the wildcard from English)
        fixed_tokens = []
        da_tokens = da_template.split()
        en_tokens = en_template.split()

        for tok in da_tokens:
            if "_" in tok:
                word, pos = tok.split("_", 1)
                if word in VALID_POS and pos in VALID_POS and word == pos:
                    # This is a POS-as-token error, replace with wildcard
                    fixed_tokens.append(f"*_{pos}")
                else:
                    fixed_tokens.append(tok)
            else:
                fixed_tokens.append(tok)

        corrections[ln] = " ".join(fixed_tokens)

    return corrections


def fix_mwe_single_word(
    da_entries: list[dict],
    en_entries: list[dict],
    error_entries: list[dict],
) -> tuple[dict[int, str], list[dict]]:
    """Fix single-word MWE entries.
    - If corresponding English entry has wildcards, restore them.
    - Otherwise, mark for moving to SWL.
    Returns (corrections for MWE, entries to move to SWL)."""
    log.info("Fixing %d single-word MWE entries...", len(error_entries))
    corrections = {}
    move_to_swl = []

    for e in error_entries:
        ln = e["line_num"]
        en_idx = ln - 2
        if en_idx < 0 or en_idx >= len(en_entries):
            # No English source - move to SWL
            move_to_swl.append(e)
            continue

        en_template = en_entries[en_idx]["mwe_template"]
        en_tokens = en_template.split()
        da_template = e["mwe_template"]

        # If English had more tokens (with wildcards), restore wildcards
        if len(en_tokens) > 1:
            # Rebuild: keep wildcard tokens from English, replace the non-wildcard token with Danish
            fixed_tokens = []
            da_word_used = False
            for en_tok in en_tokens:
                if "*" in en_tok.split("_")[0] or en_tok.startswith("{"):
                    # Wildcard or discontinuous marker - keep from English
                    fixed_tokens.append(en_tok)
                else:
                    if not da_word_used:
                        fixed_tokens.append(da_template)
                        da_word_used = True
                    else:
                        fixed_tokens.append(en_tok)
            if not da_word_used:
                fixed_tokens.append(da_template)
            corrections[ln] = " ".join(fixed_tokens)
        else:
            # English is also single word, genuinely a single-word entry
            move_to_swl.append(e)

    return corrections, move_to_swl


def fix_mwe_nan(
    en_entries: list[dict],
    nan_entries: list[dict],
    model: str,
    batch_size: int,
) -> dict[int, str]:
    """Use LLM to translate nan (untranslated) MWE entries from English."""
    log.info("Fixing %d nan MWE entries via LLM...", len(nan_entries))
    corrections = {}

    for i in tqdm(range(0, len(nan_entries), batch_size), desc="MWE nan"):
        batch = nan_entries[i : i + batch_size]
        batch_items = []
        for e in batch:
            ln = e["line_num"]
            en_idx = ln - 2
            en_template = en_entries[en_idx]["mwe_template"] if 0 <= en_idx < len(en_entries) else "UNKNOWN"
            en_tags = en_entries[en_idx]["semantic_tags"] if 0 <= en_idx < len(en_entries) else ""
            batch_items.append({
                "line_num": ln,
                "english_mwe": en_template,
                "semantic_tags": e["semantic_tags"],
            })

        prompt = (
            "You are a linguistic expert in Danish and the USAS MWE (Multi-Word Expression) format.\n"
            "The MWE format uses tokens tagged with POS: word_POS (e.g. hund_NOUN kat_NOUN).\n"
            "Wildcards * can be used: *_NOUN means any word with POS NOUN.\n"
            "Curly braces mark discontinuous items: {PRON/Np} means pronoun or proper noun.\n\n"
            "Below are English MWE entries that need to be translated to Danish.\n"
            "Translate ONLY the actual words to Danish. Keep POS tags, wildcards (*), "
            "and structural elements ({...}) unchanged.\n"
            "If the expression uses only wildcards and proper nouns that don't need translation, "
            "keep them as-is in the output.\n"
            "If it's impossible to translate (too English-specific), output 'SKIP'.\n\n"
            "IMPORTANT: Return ONLY a JSON array with keys: line_num, danish_mwe\n"
            "Do NOT include any explanation outside the JSON.\n\n"
            f"Input:\n```json\n{json.dumps(batch_items, ensure_ascii=False, indent=2)}\n```\n"
        )

        result = ollama_batch_json(prompt, model=model)
        if isinstance(result, list):
            for item in result:
                ln = item.get("line_num")
                mwe = item.get("danish_mwe", "")
                if ln is not None and mwe and mwe != "SKIP":
                    corrections[ln] = mwe
        else:
            log.warning("Failed to parse LLM response for nan batch %d", i)

    return corrections


def fix_mwe_repetition(
    en_entries: list[dict],
    rep_entries: list[dict],
    model: str,
    batch_size: int,
) -> dict[int, str]:
    """Use LLM to fix entries with excessive token repetition."""
    log.info("Fixing %d token-repetition MWE entries via LLM...", len(rep_entries))
    corrections = {}

    for i in tqdm(range(0, len(rep_entries), batch_size), desc="MWE repetition"):
        batch = rep_entries[i : i + batch_size]
        batch_items = []
        for e in batch:
            ln = e["line_num"]
            en_idx = ln - 2
            en_template = en_entries[en_idx]["mwe_template"] if 0 <= en_idx < len(en_entries) else "UNKNOWN"
            batch_items.append({
                "line_num": ln,
                "english_mwe": en_template,
                "danish_mwe_current": e["mwe_template"],
                "semantic_tags": e["semantic_tags"],
            })

        prompt = (
            "You are a linguistic expert in Danish and the USAS MWE (Multi-Word Expression) format.\n"
            "The MWE format uses tokens tagged with POS: word_POS (e.g. hund_NOUN).\n"
            "Wildcards: *_NUM means any number, *_NOUN means any noun.\n\n"
            "Below are Danish MWE entries that have excessive token repetition (likely translation errors).\n"
            "The English source is provided for reference.\n"
            "Fix each Danish MWE to properly translate the English expression.\n"
            "Use wildcards (*) where the English uses them.\n\n"
            "IMPORTANT: Return ONLY a JSON array with keys: line_num, danish_mwe\n"
            "Do NOT include any explanation outside the JSON.\n\n"
            f"Input:\n```json\n{json.dumps(batch_items, ensure_ascii=False, indent=2)}\n```\n"
        )

        result = ollama_batch_json(prompt, model=model)
        if isinstance(result, list):
            for item in result:
                ln = item.get("line_num")
                mwe = item.get("danish_mwe", "")
                if ln is not None and mwe:
                    corrections[ln] = mwe
        else:
            log.warning("Failed to parse LLM response for repetition batch %d", i)

    return corrections


# ===================================================================
# PHASE 3: Apply corrections & verify
# ===================================================================

def apply_swl_corrections(
    entries: list[dict],
    dup_resolved: dict[tuple, str],
    multi_token_fixed: dict[int, dict],
    move_from_mwe: list[dict],
) -> list[dict]:
    """Apply all SWL corrections and return the cleaned entry list."""
    # 1. Resolve duplicates: keep only the first occurrence with the resolved tag
    seen = {}
    cleaned = []
    for e in entries:
        key = (e["lemma"], e["pos"])
        if key in dup_resolved:
            if key not in seen:
                e_copy = dict(e)
                e_copy["semantic_tags"] = dup_resolved[key]
                cleaned.append(e_copy)
                seen[key] = True
            # skip subsequent duplicates
        else:
            cleaned.append(dict(e))

    # 2. Fix multi-token lemmas
    for i, e in enumerate(cleaned):
        if e["line_num"] in multi_token_fixed:
            fix = multi_token_fixed[e["line_num"]]
            cleaned[i]["lemma"] = fix["lemma"]
            cleaned[i]["pos"] = fix.get("pos", e["pos"])
            cleaned[i]["semantic_tags"] = fix.get("semantic_tags", e["semantic_tags"])

    # 3. Remove remaining multi-token lemmas (won't match single tokens anyway)
    before_multi = len(cleaned)
    cleaned = [e for e in cleaned if " " not in e["lemma"]]
    removed_multi = before_multi - len(cleaned)
    if removed_multi:
        log.info("Removed %d unfixed multi-token lemmas from SWL", removed_multi)

    # 4. Add entries moved from MWE
    for mwe_e in move_from_mwe:
        template = mwe_e["mwe_template"]
        if "_" in template:
            word, pos = template.rsplit("_", 1)
        else:
            word = template
            pos = "NOUN"
        cleaned.append({
            "line_num": -1,
            "index": "",
            "lemma": word,
            "pos": pos,
            "semantic_tags": mwe_e["semantic_tags"],
            "raw": "",
        })

    # 5. Final dedup pass: remove exact (lemma, pos, semantic_tags) duplicates
    seen_full = set()
    final = []
    for e in cleaned:
        key = (e["lemma"], e["pos"], e["semantic_tags"])
        if key not in seen_full:
            seen_full.add(key)
            final.append(e)

    return final


def apply_mwe_corrections(
    entries: list[dict],
    pos_fixes: dict[int, str],
    single_word_fixes: dict[int, str],
    nan_fixes: dict[int, str],
    rep_fixes: dict[int, str],
    remove_line_nums: set[int],
) -> list[dict]:
    """Apply all MWE corrections and return the cleaned entry list."""
    cleaned = []
    for e in entries:
        ln = e["line_num"]

        # Skip entries that are moved to SWL or are unfixable nan
        if ln in remove_line_nums:
            continue

        e_copy = dict(e)

        # Apply specific fixes in priority order
        if ln in pos_fixes:
            e_copy["mwe_template"] = pos_fixes[ln]
        if ln in single_word_fixes:
            e_copy["mwe_template"] = single_word_fixes[ln]
        if ln in nan_fixes:
            e_copy["mwe_template"] = nan_fixes[ln]
        if ln in rep_fixes:
            e_copy["mwe_template"] = rep_fixes[ln]

        # Skip remaining nan entries
        if e_copy["mwe_template"] == "nan":
            continue

        cleaned.append(e_copy)

    # Remove entries with excessive token repetition that weren't fixed
    before_rep = len(cleaned)
    clean_no_rep = []
    for e in cleaned:
        tokens = e["mwe_template"].split()
        if len(tokens) >= 3:
            c = Counter(tokens)
            if any(cnt >= 3 for cnt in c.values()):
                continue  # skip unfixed repetition
        clean_no_rep.append(e)
    removed_rep = before_rep - len(clean_no_rep)
    if removed_rep:
        log.info("Removed %d unfixed token-repetition entries from MWE", removed_rep)
    cleaned = clean_no_rep

    # Remove exact duplicates
    seen = set()
    final = []
    for e in cleaned:
        key = (e["mwe_template"], e["semantic_tags"])
        if key not in seen:
            seen.add(key)
            final.append(e)

    return final


# ===================================================================
# Verification
# ===================================================================

def verify_swl(entries: list[dict]) -> dict[str, int]:
    """Run all SWL error checks and return counts."""
    dups = detect_swl_duplicates(entries)
    multi = detect_swl_multi_token(entries)
    return {"duplicates": len(dups), "multi_token_lemmas": len(multi)}


def verify_mwe(entries: list[dict]) -> dict[str, int]:
    """Run all MWE error checks and return counts."""
    pos_err = detect_mwe_pos_as_token(entries)
    single = detect_mwe_single_word(entries)
    rep = detect_mwe_token_repetition(entries)
    nan_err = detect_mwe_nan(entries)
    return {
        "pos_as_token": len(pos_err),
        "single_word": len(single),
        "token_repetition": len(rep),
        "nan_entries": len(nan_err),
    }


def print_report(title: str, counts: dict[str, int]):
    """Print a formatted error report."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")
    total = 0
    for name, count in counts.items():
        status = "OK" if count == 0 else "ERRORS"
        print(f"  {name:30s}: {count:6d}  [{status}]")
        total += count
    print(f"  {'TOTAL':30s}: {total:6d}")
    print(f"{'='*60}\n")
    return total


# ===================================================================
# Main
# ===================================================================

def main():
    parser = argparse.ArgumentParser(description="Fix Danish pymusas lexicon errors")
    parser.add_argument("--detect-only", action="store_true",
                        help="Only detect errors programmatically (no LLM), print report and exit")
    parser.add_argument("--dry-run", action="store_true",
                        help="Alias for --detect-only")
    parser.add_argument("--batch-size", type=int, default=10, help="Batch size for LLM calls")
    parser.add_argument("--model", type=str, default="qwen3:32b", help="Ollama model name")
    parser.add_argument("--retranslate", action="store_true",
                        help="Also fix errors that require LLM retranslation (multi-token, nan, repetition)")
    parser.add_argument("--verify-only", action="store_true", help="Only verify existing fixed files")
    args = parser.parse_args()

    # --- Load files ---
    log.info("Loading lexicon files...")
    swl_da = load_swl(SWL_DA_PATH)
    mwe_da = load_mwe(MWE_DA_PATH)
    swl_en = load_swl(SWL_EN_PATH)
    mwe_en = load_mwe(MWE_EN_PATH)

    log.info("Loaded: SWL_DA=%d, MWE_DA=%d, SWL_EN=%d, MWE_EN=%d",
             len(swl_da), len(mwe_da), len(swl_en), len(mwe_en))

    # --- Phase 1: Detect errors ---
    log.info("Phase 1: Detecting errors...")

    # SWL errors
    swl_dups = detect_swl_duplicates(swl_da)
    swl_multi = detect_swl_multi_token(swl_da)

    # MWE errors
    mwe_pos_err = detect_mwe_pos_as_token(mwe_da)
    mwe_single = detect_mwe_single_word(mwe_da)
    mwe_rep = detect_mwe_token_repetition(mwe_da)
    mwe_nan = detect_mwe_nan(mwe_da)

    swl_counts = {"duplicates": len(swl_dups), "multi_token_lemmas": len(swl_multi)}
    mwe_counts = {
        "pos_as_token": len(mwe_pos_err),
        "single_word": len(mwe_single),
        "token_repetition": len(mwe_rep),
        "nan_entries": len(mwe_nan),
    }

    print_report("BEFORE FIX - Single Word Lexicon Errors (programmatic detection)", swl_counts)
    print_report("BEFORE FIX - MWE Lexicon Errors (programmatic detection)", mwe_counts)

    if args.detect_only or args.dry_run or args.verify_only:
        if args.verify_only:
            # Verify the fixed files if they exist
            if SWL_DA_OUT.exists() and MWE_DA_OUT.exists():
                swl_fixed = load_swl(SWL_DA_OUT)
                mwe_fixed = load_mwe(MWE_DA_OUT)
                swl_v = verify_swl(swl_fixed)
                mwe_v = verify_mwe(mwe_fixed)
                print_report("AFTER FIX - Single Word Lexicon Errors", swl_v)
                print_report("AFTER FIX - MWE Lexicon Errors", mwe_v)
            else:
                log.warning("Fixed files not found. Run without --verify-only first.")
        return

    # --- Phase 2: Fix errors ---
    log.info("Phase 2: Applying corrections...")

    # 2a. Fix SWL duplicates (deterministic: keep first occurrence)
    dup_resolved = fix_swl_duplicates(swl_dups)

    # 2b. Fix SWL multi-token lemmas (requires retranslation)
    multi_token_fixed = {}
    if args.retranslate:
        multi_token_fixed = fix_swl_multi_token(swl_multi, model=args.model, batch_size=args.batch_size)
    else:
        log.info("Skipping %d multi-token lemma fixes (use --retranslate to enable)", len(swl_multi))

    # 2c. Fix MWE POS-as-token (deterministic)
    pos_fixes = fix_mwe_pos_as_token(mwe_da, mwe_en, mwe_pos_err)

    # 2d. Fix MWE single-word entries (deterministic: restore wildcards from English)
    single_word_fixes, move_to_swl = fix_mwe_single_word(mwe_da, mwe_en, mwe_single)
    remove_from_mwe = {e["line_num"] for e in move_to_swl}

    # 2e. Fix MWE nan entries (requires retranslation)
    nan_fixes = {}
    if args.retranslate:
        nan_fixes = fix_mwe_nan(mwe_en, mwe_nan, model=args.model, batch_size=args.batch_size)
        unfixed_nan = {e["line_num"] for e in mwe_nan if e["line_num"] not in nan_fixes}
        remove_from_mwe.update(unfixed_nan)
    else:
        log.info("Skipping %d nan entry fixes (use --retranslate to enable)", len(mwe_nan))
        # Remove all nan entries since they can't be used anyway
        remove_from_mwe.update(e["line_num"] for e in mwe_nan)

    # 2f. Fix MWE token repetition (requires retranslation)
    rep_fixes = {}
    if args.retranslate:
        rep_fixes = fix_mwe_repetition(mwe_en, mwe_rep, model=args.model, batch_size=args.batch_size)
    else:
        log.info("Skipping %d token-repetition fixes (use --retranslate to enable)", len(mwe_rep))

    # --- Phase 3: Apply & save ---
    log.info("Phase 3: Applying all corrections and saving...")

    swl_corrected = apply_swl_corrections(swl_da, dup_resolved, multi_token_fixed, move_to_swl)
    mwe_corrected = apply_mwe_corrections(
        mwe_da, pos_fixes, single_word_fixes, nan_fixes, rep_fixes, remove_from_mwe
    )

    save_swl(swl_corrected, SWL_DA_OUT)
    save_mwe(mwe_corrected, MWE_DA_OUT)

    # --- Phase 4: Verify ---
    log.info("Phase 4: Verifying corrected files...")
    swl_fixed = load_swl(SWL_DA_OUT)
    mwe_fixed = load_mwe(MWE_DA_OUT)

    swl_v = verify_swl(swl_fixed)
    mwe_v = verify_mwe(mwe_fixed)

    total_remaining = print_report("AFTER FIX - Single Word Lexicon Errors", swl_v)
    total_remaining += print_report("AFTER FIX - MWE Lexicon Errors", mwe_v)

    if total_remaining == 0:
        print("All errors resolved!")
    else:
        print(f"WARNING: {total_remaining} errors remain. Consider re-running or manual review.")

    # Save a summary report
    report = {
        "before": {"swl": swl_counts, "mwe": mwe_counts},
        "after": {"swl": swl_v, "mwe": mwe_v},
        "retranslate_enabled": args.retranslate,
        "fixes_applied": {
            "swl_duplicates_resolved": len(dup_resolved),
            "swl_multi_token_fixed": len(multi_token_fixed),
            "mwe_pos_as_token_fixed": len(pos_fixes),
            "mwe_single_word_restored": len(single_word_fixes),
            "mwe_single_word_moved_to_swl": len(move_to_swl),
            "mwe_nan_translated": len(nan_fixes),
            "mwe_nan_removed": len([e for e in mwe_nan if e['line_num'] in remove_from_mwe]),
            "mwe_repetition_fixed": len(rep_fixes),
        },
        "output_files": {
            "swl": str(SWL_DA_OUT),
            "mwe": str(MWE_DA_OUT),
        },
    }
    report_path = BASE_DIR / "resources" / "Multilingual-USAS" / "Danish" / "fix_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    log.info("Report saved to %s", report_path)


if __name__ == "__main__":
    main()
