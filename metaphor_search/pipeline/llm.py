"""One tiny model client: a local Ollama server, or a DRY-RUN stand-in that needs no GPU.

Ollama is the only endpoint the pipeline knows. Point it at your own machine with
`OLLAMA_URL` (default http://localhost:11434). The dry-run client answers every prompt
with a plausible canned reply so the whole plumbing can be exercised on a laptop.
"""
import json
import re
import urllib.request


class Ollama:
    def __init__(self, url="http://localhost:11434", timeout=600):
        self.url = url.rstrip("/")
        self.timeout = timeout

    def models(self):
        with urllib.request.urlopen(self.url + "/api/tags", timeout=30) as r:
            return [m["name"] for m in json.loads(r.read())["models"]]

    def generate(self, model, prompt, num_predict=512, think=False, num_ctx=4096):
        name = model.split(":", 1)[1] if model.startswith("ollama:") else model
        payload = {"model": name, "prompt": prompt, "stream": False,
                   "options": {"temperature": 0, "num_predict": num_predict, "num_ctx": num_ctx}}
        # gpt-oss needs its reasoning switched on to answer at all; the others answer faster without
        payload["think"] = "low" if "gpt-oss" in name else think
        req = urllib.request.Request(self.url + "/api/generate", data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode("utf-8")).get("response", "")


class DryRun:
    """Answers prompts without any model. Mining returns the first quoted-looking phrase or
    the first three words of the excerpt; screens answer deterministically from a hash, so
    runs are repeatable. Only for checking that the pipeline is wired correctly."""

    def models(self):
        return ["dry-run"]

    def generate(self, model, prompt, **_):
        body = prompt.rsplit("Excerpt:", 1)[-1] if "Excerpt:" in prompt else prompt
        h = sum(ord(c) for c in body) % 10
        if '"candidates"' in prompt:                      # mining prompt
            words = body.strip().split()
            phrase = " ".join(words[h % 3: h % 3 + 3]) if len(words) > 5 else ""
            cands = [{"phrase": phrase, "usas": "M1"}] if phrase and h % 2 == 0 else []
            return json.dumps({"candidates": cands})
        if '"verdict"' in prompt:
            return json.dumps({"verdict": "keep" if h % 3 else "reject"})
        if '"experiential"' in prompt:
            return json.dumps({"experiential": h % 2 == 0})
        if '"register"' in prompt:
            return json.dumps({"register": "vivid" if h % 4 == 0 else "conventional"})
        if '"score"' in prompt:
            return json.dumps({"score": h})
        if '"metaphorical"' in prompt:
            return json.dumps({"metaphorical": h % 2 == 0})
        return json.dumps([{"id": i, "concept": "journey"} for i in range(40)])


def client(url_or_dryrun):
    """`client('dryrun')` or `client('http://host:11434')`."""
    return DryRun() if str(url_or_dryrun).lower() in ("dryrun", "dry-run", "") else Ollama(url_or_dryrun)


def first_json(text):
    """The first {...} or [...] object in a model reply, or None."""
    m = re.search(r"\{.*\}|\[.*\]", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
