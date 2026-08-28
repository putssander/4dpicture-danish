"""Finer-than-USAS source-domain layers for the review pages.

USAS stops at G3 (all of war/battle/fight) and K5 (all sports). This adds, per candidate,
four alternative groupings so the stage-3 page can switch between them:

  head   the vehicle head word (spaCy lemma of the phrase's figurative head)   — lexical
  wn1    WordNet immediate hypernym of that head word (boxing -> contact sport) — lexical
  wn2    WordNet hypernym two levels up (boxing -> sport)                        — lexical
  fn     FrameNet frame of the head word (fight -> Hostile_encounter)            — English only
  llm    a 1-3 word source concept named in context by a LOCAL model on the box  — `llm` subcommand

Layers head/wn/fn are deterministic and CPU-only. The `llm` subcommand talks to a local
Ollama endpoint (http://localhost:11434) and is meant to run on the ucloud box; nothing
here calls a frontier API. Output is one JSONL row per candidate id, text-free except for
the head lemma and the model's short concept label.

    python vehicle_layers.py lexical --jobs <stack>/screens/jobs.json --language en \
        --out corona_vehicle_layers.jsonl
    python vehicle_layers.py llm --jobs <stack>/screens/jobs.json --language en \
        --inout corona_vehicle_layers.jsonl --model qwen3:32b        # on the box
"""
import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

# words that name the TENOR, never the vehicle — skipped when picking the head word
TENOR = {
    "en": {"cancer", "covid", "covid-19", "coronavirus", "virus", "disease", "illness", "ill",
           "sick", "sickness", "symptom", "symptoms", "infection", "pandemic", "tumour", "tumor",
           "chemo", "chemotherapy", "diagnosis", "treatment", "body", "health", "long", "haul"},
    "da": {"kræft", "kræften", "sygdom", "sygdommen", "syg", "kemo", "kemoterapi", "diagnose",
           "behandling", "krop", "kroppen", "symptom", "symptomer", "tumor", "knude"},
    "nl": {"kanker", "ziekte", "ziek", "chemo", "chemotherapie", "diagnose", "behandeling",
           "lichaam", "symptoom", "symptomen", "tumor", "gezwel", "bestraling"},
}
SPACY = {"en": "en_core_web_sm", "da": "da_core_news_sm", "nl": "nl_core_news_sm"}
OMW = {"en": "eng", "da": "dan", "nl": "nld"}


def load_jobs(path):
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    jobs = d["jobs"] if isinstance(d, dict) else d
    return {j["id"]: j for j in jobs}


LIGHT = {"come", "go", "get", "make", "take", "have", "want", "let", "keep", "stop", "turn", "put",
         "be", "do", "give", "see", "feel", "know", "think", "try", "start", "need", "say", "look",
         "become", "seem", "use", "find", "call", "mean", "live", "die", "happen", "deal"}


def head_word(nlp, phrase, stop):
    """The vehicle is nearly always a noun (tunnel, flood, lodger, stone): first content noun
    that is not a tenor word; else the root verb unless it is a light verb; else any verb/adj."""
    doc = nlp(phrase)
    def ok(t):
        return (not t.is_stop and t.is_alpha and t.lemma_.lower() not in stop
                and t.text.lower() not in stop)
    for t in doc:
        if t.pos_ in ("NOUN", "PROPN") and ok(t):
            return t.lemma_.lower(), "NOUN"
    root = next((t for t in doc if t.dep_ == "ROOT"), None)
    if root is not None and root.pos_ == "VERB" and ok(root) and root.lemma_.lower() not in LIGHT:
        return root.lemma_.lower(), "VERB"
    for pos in ("VERB", "ADJ"):
        for t in doc:
            if t.pos_ == pos and ok(t) and t.lemma_.lower() not in LIGHT:
                return t.lemma_.lower(), pos
    if root is not None and root.pos_ == "VERB" and ok(root):
        return root.lemma_.lower(), "VERB"
    return "", ""


def wordnet_layers(wn, lemma, pos, lang):
    if not lemma:
        return "", ""
    wpos = {"NOUN": "n", "PROPN": "n", "VERB": "v", "ADJ": "a"}.get(pos, "n")
    try:
        syns = wn.synsets(lemma, pos=wpos, lang=lang) or wn.synsets(lemma, lang=lang)
    except Exception:
        syns = []
    if not syns:
        return "", ""
    s = syns[0]
    def label(x):
        return x.lemma_names()[0].replace("_", " ")
    h1 = s.hypernyms() or s.instance_hypernyms()
    if not h1:
        return label(s), label(s)
    h2 = h1[0].hypernyms() or h1[0].instance_hypernyms()
    return label(h1[0]), (label(h2[0]) if h2 else label(h1[0]))


def framenet_frame(fn, lemma, pos):
    if not lemma:
        return ""
    fpos = {"NOUN": "n", "PROPN": "n", "VERB": "v", "ADJ": "a"}.get(pos, "n")
    try:
        lus = fn.lus(r"^" + re.escape(lemma) + r"\." + fpos + r"$")
        if not lus:
            lus = fn.lus(r"^" + re.escape(lemma) + r"\.")
        return lus[0].frame.name if lus else ""
    except Exception:
        return ""


def cmd_lexical(A):
    import spacy
    import nltk
    from nltk.corpus import wordnet as wn
    nlp = spacy.load(SPACY[A.language])
    fn = None
    if A.language == "en":
        from nltk.corpus import framenet as fn
    stop = TENOR[A.language]
    jobs = load_jobs(A.jobs)
    prev = {}
    if A.out.exists():
        for line in A.out.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line); prev[r["id"]] = r
    rows = []
    for i, j in jobs.items():
        lemma, pos = head_word(nlp, j.get("phrase", ""), stop)
        w1, w2 = wordnet_layers(wn, lemma, pos, OMW[A.language])
        r = {"id": i, "head": lemma, "wn1": w1, "wn2": w2,
             "fn": framenet_frame(fn, lemma, pos) if fn else ""}
        if i in prev and prev[i].get("llm"):
            r["llm"] = prev[i]["llm"]
        rows.append(r)
    A.out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    n = len(rows)
    print(f"{A.out}: {n} rows; head {sum(1 for r in rows if r['head'])}/{n}, "
          f"wordnet {sum(1 for r in rows if r['wn1'])}/{n}, framenet {sum(1 for r in rows if r['fn'])}/{n}, "
          f"llm {sum(1 for r in rows if r.get('llm'))}/{n}")


LLM_SYSTEM = ("You label the SOURCE CONCEPT of figurative expressions about illness. For each item, "
              "name in 1-3 plain words the concrete thing or activity the expression borrows its image "
              "from - be specific: 'boxing match' not 'sport', 'trench war' not 'violence', "
              "'rollercoaster' not 'ride', 'train journey' not 'journey'. If the expression is not "
              "figurative, answer 'none'. Reply with JSON only: a list of {\"id\": ..., \"concept\": ...}.")


def ollama_chat(model, system, user, host):
    body = json.dumps({"model": model, "stream": False, "think": False,
                       "options": {"temperature": 0, "num_ctx": 4096},
                       "messages": [{"role": "system", "content": system},
                                    {"role": "user", "content": user}]}).encode()
    req = urllib.request.Request(f"{host}/api/chat", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read())["message"]["content"]


def cmd_llm(A):
    jobs = load_jobs(A.jobs)
    rows = {}
    for line in A.inout.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line); rows[r["id"]] = r
    todo = [i for i in rows if not rows[i].get("llm") and i in jobs]
    out_path = A.inout
    if A.shard:
        k, n = (int(x) for x in A.shard.split("/"))
        todo = todo[k::n]
        out_path = A.inout.with_suffix(f".shard{k}.jsonl")   # merge with `merge` afterwards
    print(f"{len(todo)} to label with {A.model} at {A.host}" + (f" (shard {A.shard})" if A.shard else ""))
    lang = {"en": "English", "da": "Danish", "nl": "Dutch"}[A.language]
    for b in range(0, len(todo), A.batch):
        ids = todo[b:b + A.batch]
        items = [{"id": str(k), "expression": jobs[i]["phrase"], "context": jobs[i].get("text", "")[:400]}
                 for k, i in enumerate(ids)]
        user = (f"Language: {lang}. Answer in English. Items:\n" + json.dumps(items, ensure_ascii=False))
        for attempt in range(3):
            try:
                raw = ollama_chat(A.model, LLM_SYSTEM, user, A.host)
                m = re.search(r"\[.*\]", raw, re.S)
                out = json.loads(m.group(0)) if m else []
                got = {str(o.get("id")): str(o.get("concept", "")).strip().lower() for o in out if isinstance(o, dict)}
                for k, i in enumerate(ids):
                    c = got.get(str(k), "")
                    rows[i]["llm"] = c if c and c != "none" else "none"
                break
            except Exception as e:
                print("  retry:", e); time.sleep(2 ** attempt)
        done_ids = set(todo[:b + A.batch]) if A.shard else rows.keys()
        out_path.write_text("".join(json.dumps(rows[i], ensure_ascii=False) + "\n" for i in rows if i in done_ids), encoding="utf-8")
        print(f"  {min(b + A.batch, len(todo))}/{len(todo)}")
    print("done:", sum(1 for r in rows.values() if r.get("llm")), "labelled")


def cmd_merge(A):
    """Fold *.shardK.jsonl label files back into the main layers file, then delete them."""
    rows = {}
    for line in A.inout.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line); rows[r["id"]] = r
    n = 0
    for sh in sorted(A.inout.parent.glob(A.inout.stem + ".shard*.jsonl")):
        for line in sh.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("llm") and r["id"] in rows:
                    rows[r["id"]]["llm"] = r["llm"]; n += 1
        sh.unlink()
    A.inout.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows.values()), encoding="utf-8")
    print(f"merged {n} labels; {sum(1 for r in rows.values() if r.get('llm'))}/{len(rows)} labelled")


def cmd_cluster(A):
    """Embedding-based normalisation of the free-text model concepts: sentence-transformer
    embeddings + agglomerative clustering (cosine distance <= --threshold). Each cluster is named
    by its most frequent member label. Writes --field (default `llm_cluster`) next to `llm`. CPU, seconds.
    Used twice by the page build: --threshold 0.25 --field llm_c1 (near-duplicates only) and
    --threshold 0.45 --field llm_c2 (broader groups)."""
    import re as _re
    import numpy as np
    from sentence_transformers import SentenceTransformer
    from sklearn.cluster import AgglomerativeClustering
    rows = {}
    for line in A.inout.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line); rows[r["id"]] = r
    def norm(s):
        s = _re.sub(r"[^\w\s]", " ", str(s or "").lower().replace("-", " "))
        s = _re.sub(r"\s+", " ", s).strip()
        return _re.sub(r"^(a|an|the|some) ", "", s)
    from collections import Counter
    freq = Counter(norm(r["llm"]) for r in rows.values() if r.get("llm") and r["llm"].lower() != "none")
    freq.pop("", None)
    labels = sorted(freq, key=lambda k: -freq[k])
    if not labels:
        print("no labels to cluster"); return
    model = SentenceTransformer(A.model)
    emb = model.encode(labels, normalize_embeddings=True, batch_size=256, show_progress_bar=False)
    if len(labels) == 1:
        assign = [0]
    else:
        cl = AgglomerativeClustering(n_clusters=None, metric="cosine", linkage="average",
                                     distance_threshold=A.threshold)
        assign = cl.fit_predict(emb)
    name = {}
    for lab, c in zip(labels, assign):
        if c not in name:                      # labels are frequency-sorted: first seen = most frequent
            name[c] = lab
    lab2name = {lab: name[c] for lab, c in zip(labels, assign)}
    for r in rows.values():
        if r.get("llm") and r["llm"].lower() != "none":
            r[A.field] = lab2name.get(norm(r["llm"]), norm(r["llm"]))
        else:
            r.pop(A.field, None)
    A.inout.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows.values()), encoding="utf-8")
    sizes = Counter(lab2name.values())
    print(f"{len(labels)} distinct labels -> {len(sizes)} clusters (threshold {A.threshold}, {A.model})")
    if A.show:
        members = {}
        for lab, nm in lab2name.items():
            members.setdefault(nm, []).append(lab)
        for nm, ms in sorted(members.items(), key=lambda kv: -sum(freq[m] for m in kv[1]))[:A.show]:
            if len(ms) > 1:
                print(f"  {nm} ({sum(freq[m] for m in ms)}): " + ", ".join(m for m in ms if m != nm)[:200])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("lexical"); a.add_argument("--jobs", required=True); a.add_argument("--language", default="en")
    a.add_argument("--out", type=Path, required=True)
    b = sub.add_parser("llm"); b.add_argument("--jobs", required=True); b.add_argument("--language", default="en")
    b.add_argument("--inout", type=Path, required=True); b.add_argument("--model", default="qwen3:32b")
    b.add_argument("--host", default="http://localhost:11434"); b.add_argument("--batch", type=int, default=20)
    b.add_argument("--shard", default="", help="k/n: label every n-th pending item starting at k, write a .shardK file")
    c = sub.add_parser("merge"); c.add_argument("--inout", type=Path, required=True)
    d = sub.add_parser("cluster"); d.add_argument("--inout", type=Path, required=True)
    d.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2")
    d.add_argument("--threshold", type=float, default=0.35, help="cosine distance; smaller = stricter merging")
    d.add_argument("--show", type=int, default=25, help="print the N largest merged clusters")
    d.add_argument("--field", default="llm_cluster", help="output field name (run twice with different thresholds)")
    A = ap.parse_args()
    {"lexical": cmd_lexical, "llm": cmd_llm, "merge": cmd_merge, "cluster": cmd_cluster}[A.cmd](A)
