"""Step 2 — two different model families read every passage and propose candidates.

Open prompt (no example USAS codes: examples anchored the models badly in 2024–25).
Each model writes its own checkpoint file `checkpoints/<model>.jsonl`, one line per passage,
so a run can be resumed. Errors are simply retried on the next run.

    from pipeline import mine, llm
    mine.run(llm.client(OLLAMA_URL), "qwen3:32b", work, language="English", workers=8)
"""
import json
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .llm import first_json
from .segment import load as load_segments

PROMPT = {
    "English": (
        'You are given one excerpt from an online illness-community post. Find all '
        'metaphorical expressions (figurative language), including everyday metaphors. '
        'Answer ONLY with JSON of the form '
        '{"candidates": [{"phrase": "...", "usas": "<USAS top-level category for the domain of the image>"}]} '
        'and with an empty list if there are none.\n\nExcerpt:\n'),
    "Danish": (
        'Du får ét uddrag fra en tekst om at leve med sygdom. Find alle metaforiske udtryk '
        '(billedsprog), også hverdagsmetaforer. Svar KUN med JSON på formen '
        '{"candidates": [{"phrase": "...", "usas": "<USAS top-level category for the domain of the image>"}]} '
        'og med en tom liste hvis der ingen er.\n\nUddrag:\n'),
    "Dutch": (
        'Je krijgt één fragment uit een tekst over leven met ziekte. Vind alle metaforische '
        'uitdrukkingen (beeldspraak), ook alledaagse metaforen. Antwoord ALLEEN met JSON van de vorm '
        '{"candidates": [{"phrase": "...", "usas": "<USAS top-level category for the domain of the image>"}]} '
        'en met een lege lijst als er geen zijn.\n\nFragment:\n'),
}


def ckpt_path(work, model):
    return Path(work) / "checkpoints" / (model.replace(":", "_").replace("/", "_") + ".jsonl")


def load_checkpoint(path):
    out = {}
    if Path(path).exists():
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line); out[d["seg"]] = d["cands"]
            except Exception:
                pass
    return out


def run(client, model, work, language="English", workers=4, limit=None, progress=print):
    work = Path(work)
    segs = load_segments(work / "segments.json")
    if limit:
        segs = segs[:limit]
    ck = ckpt_path(work, model)
    done = load_checkpoint(ck)
    todo = [(sid, text) for sid, text in segs if sid not in done]
    progress(f"{model}: {len(segs)} passages, {len(done)} already done, {len(todo)} to mine")
    prompt = PROMPT.get(language, PROMPT["English"])
    ck.parent.mkdir(parents=True, exist_ok=True)
    errors, lock, n = Counter(), threading.Lock(), [0]
    out = ck.open("a", encoding="utf-8")

    def work_one(item):
        sid, text = item
        try:
            raw = first_json(client.generate(model, prompt + text)) or {}
            cands = [{"phrase": c["phrase"], "usas": c.get("usas", "")} for c in raw.get("candidates", [])
                     if isinstance(c, dict) and c.get("phrase")]
            with lock:
                out.write(json.dumps({"seg": sid, "cands": cands}, ensure_ascii=False) + "\n"); out.flush()
        except Exception as exc:
            with lock:
                errors[type(exc).__name__] += 1
        finally:
            with lock:
                n[0] += 1
                if n[0] % 100 == 0:
                    progress(f"  {n[0]}/{len(todo)}")

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(work_one, todo))
    out.close()
    res = load_checkpoint(ck)
    return {"model": model, "passages": len(segs), "mined": len(res),
            "candidates": sum(len(v) for v in res.values()), "errors": dict(errors)}
