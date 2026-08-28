"""Step 4 — four screens, each one model question per candidate.

  verify        is it a genuine metaphor about the illness experience?      (strict; qwen3)
  experiential  is its topic living with the illness, not the disease itself? (gpt-oss / gemma4)
  register      fixed everyday phrase, or a personal vivid image?             (gemma4)
  score         how much does it resemble published Menu entries (0–10)?     (gpt-oss / gemma4)

Answers go to `screens/<screen>_<model>.jsonl`, resumable. English prompts are the ones
used in the project; Danish and Dutch prompts ask the same questions in those languages.
"""
import json
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .llm import first_json

MENU_ANCHORS = {
    "English": ("a fairground ride; a journey on which you look up and notice the scenery; "
                "a road walked at your own pace; a boxing match you train for; not a fight "
                "but a relationship lived with day in, day out; working with the illness "
                "rather than battling it; getting out of bed and keeping going"),
    "Danish": ("en tur i forlystelsesparken; en rejse hvor man kigger op og lægger mærke til "
               "landskabet; en vej man går i sit eget tempo; en boksekamp man træner til; ikke en "
               "kamp men et forhold man lever med dag ud og dag ind; at arbejde med sygdommen i "
               "stedet for at bekæmpe den; at komme ud af sengen og blive ved"),
    "Dutch": ("een kermisattractie; een reis waarop je opkijkt en het landschap ziet; een weg die "
              "je in je eigen tempo loopt; een bokswedstrijd waarvoor je traint; geen gevecht maar "
              "een relatie waarmee je dag in dag uit leeft; samenwerken met de ziekte in plaats van "
              "ertegen vechten; uit bed komen en doorgaan"),
}

PROMPTS = {
    "verify": (
        'A candidate metaphor was extracted from a {lang} text about living with illness. Judge it '
        'STRICTLY against three conditions:\n'
        '(a) it is a genuine metaphor (something described in terms of something else),\n'
        '(b) its TENOR — what is really being talked about — is the illness/health experience '
        '(disease, treatment, body, being a patient). The tenor may be implicit as long as the text '
        'makes it the topic.\n'
        '(c) its VEHICLE comes from a different domain than health.\n'
        'Common traps to REJECT: figurative uses of disease words about NON-illness topics (e.g. '
        '"this traffic is cancer"); idioms whose real tenor is an emotion or wish rather than the '
        'illness; literal medical terminology.\n\n'
        'Text: {text}\nCandidate expression: {phrase}\n\n'
        'Answer with JSON only: {{"verdict": "keep" or "reject"}}'),
    "experiential": (
        'The Metaphor Menu for people living with illness contains almost exclusively metaphors '
        'whose TENOR is the lived EXPERIENCE of illness: the course of life with the disease, '
        "coping, daily struggle, identity, the felt relation to one's own body, fear, hope, "
        'acceptance. Metaphors about the disease as a biomedical entity, medical terminology, or '
        'unrelated topics are NOT in this class.\n\nCandidate expression: {phrase}\nContext: {text}\n\n'
        "Is this candidate's tenor the lived experience of illness in the sense above? "
        'Answer ONLY JSON: {{"experiential": true or false}}'),
    "register": (
        'Classify this metaphorical expression from a {lang} text. Is it a FIXED, common, everyday '
        'way of speaking (something you would hear daily), or a CREATIVE / personal / vivid image '
        'the writer formed for their own experience?\n\nText: {text}\nExpression: {phrase}\n\n'
        'Answer with JSON only: {{"register": "conventional" or "vivid"}}'),
    "score": (
        'A researcher is building a "metaphor menu" for people living with illness: a curated list '
        'of metaphors that patients found vivid, personal and meaningful for making sense of their '
        'own illness experience.\n\nExamples of the class (from the published Metaphor Menu): '
        '{anchors}\n\nScore the following candidate for how strongly it belongs in that same class '
        '— vivid, experience-near, something a patient might recognise and adopt. Dead everyday '
        'idioms and medical terminology score low; personal images score high.\n\n'
        'Candidate metaphor: {phrase}\nFrom this text: {text}\n\nAnswer ONLY JSON: {{"score": <0-10>}}'),
}
KEY = {"verify": "verdict", "experiential": "experiential", "register": "register", "score": "score"}


def out_path(work, screen, model):
    return Path(work) / "screens" / f"{screen}_{model.replace(':', '_').replace('/', '_')}.jsonl"


def load(path, key):
    out = {}
    if Path(path).exists():
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line); out[d["id"]] = d.get(key)
            except Exception:
                pass
    return out


def run(client, screen, model, work, language="English", workers=4, only_ids=None, progress=print):
    work = Path(work)
    jobs = json.loads((work / "screens" / "jobs.json").read_text(encoding="utf-8"))["jobs"]
    if only_ids is not None:
        jobs = [j for j in jobs if j["id"] in only_ids]
    op = out_path(work, screen, model)
    done = load(op, KEY[screen])
    todo = [j for j in jobs if j["id"] not in done]
    progress(f"{screen}/{model}: {len(jobs)} candidates, {len(done)} done, {len(todo)} to judge")
    template = PROMPTS[screen]
    anchors = MENU_ANCHORS.get(language, MENU_ANCHORS["English"])
    errors, lock, n = Counter(), threading.Lock(), [0]
    op.parent.mkdir(parents=True, exist_ok=True)
    out = op.open("a", encoding="utf-8")

    def work_one(job):
        try:
            prompt = template.format(text=job["text"][:1200], phrase=job["phrase"][:300], lang=language, anchors=anchors)
            verdict = first_json(client.generate(model, prompt, num_predict=64)) or {}
            if KEY[screen] not in verdict:
                raise ValueError("no verdict")
            with lock:
                out.write(json.dumps({"id": job["id"], **verdict}, ensure_ascii=False) + "\n"); out.flush()
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
    return {"screen": screen, "model": model, "judged": len(load(op, KEY[screen])), "errors": dict(errors)}


def run_all(client, work, models, language="English", workers=4, progress=print):
    """The project's cascade: verify + register on everything; experiential + score only on
    verify-keepers and planted items (saves ~half the calls, changes no rank)."""
    res = [run(client, "verify", models["verify"], work, language, workers, progress=progress),
           run(client, "register", models["register"], work, language, workers, progress=progress)]
    verify = load(out_path(work, "verify", models["verify"]), "verdict")
    jobs = json.loads((Path(work) / "screens" / "jobs.json").read_text(encoding="utf-8"))["jobs"]
    stage2 = {j["id"] for j in jobs if verify.get(j["id"]) == "keep" or j["id"].startswith("PLANT|")}
    res += [run(client, "experiential", models["experiential"], work, language, workers, stage2, progress),
            run(client, "score", models["score"], work, language, workers, stage2, progress)]
    return res
