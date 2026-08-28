"""Minimal LLM wrapper for the eval harnesses: aisuite (Ollama/OpenAI/...) at
temperature 0, with retries and JSON extraction. Records every raw response so
invalid outputs can be reported, per the reproducibility checklist."""

import json
import re
import time

import aisuite


class Client:
    def __init__(self, model, temperature=0.0, max_retries=3):
        self.model = model
        self.temperature = temperature
        self.max_retries = max_retries
        self.client = aisuite.Client()
        self.n_calls = 0
        self.n_invalid = 0

    def ask(self, prompt, system=None):
        messages = ([{"role": "system", "content": system}] if system else []) + \
                   [{"role": "user", "content": prompt}]
        last = None
        for attempt in range(self.max_retries):
            try:
                resp = self.client.chat.completions.create(
                    model=self.model, messages=messages, temperature=self.temperature)
                self.n_calls += 1
                return resp.choices[0].message.content
            except Exception as e:  # transient server/API errors
                last = e
                time.sleep(2 ** attempt)
        raise RuntimeError(f"LLM call failed after {self.max_retries} attempts: {last}")

    def ask_json(self, prompt, system=None):
        """Return (parsed_json_or_None, raw_text). Counts invalid outputs."""
        raw = self.ask(prompt, system=system)
        m = re.search(r"\{.*\}|\[.*\]", raw, re.S)
        if m:
            try:
                return json.loads(m.group(0)), raw
            except json.JSONDecodeError:
                pass
        self.n_invalid += 1
        return None, raw
