# 4DPICTURE — Danish work package

Deliverables of the Danish team of the [4DPICTURE](https://4dpicture.eu) project, working
toward a Danish counterpart to Lancaster University's
[Metaphor Menu for people living with cancer](https://wp.lancs.ac.uk/melc/the-metaphor-menu/).

**▶ Live demo: https://putssander.github.io/4dpicture-danish/** — the ranked output and the
blinded review workflow on public English data. Nothing to install.

Only final, reusable material is here. No patient or participant text is included; every
demo runs on public, open-licensed data.

| | What | Where |
|---|---|---|
| **Results** | One-page summary of what was done and what was found | [`RESULTS.md`](RESULTS.md) |
| **Method** | How the metaphor finder works, in plain language | [`METHOD.md`](METHOD.md) |
| **Demo** | **[Open the live demo](https://putssander.github.io/4dpicture-danish/)** (GitHub Pages) — the ranked output first, then the three review stages (filtering → PPI voting → ranked retrospective with source-domain tables). The same pages work offline from [`demo/index.html`](demo/index.html). | [`demo/`](demo/) |
| **Metaphor search** | *Understand it*: [`ranker_walkthrough.ipynb`](metaphor_search/ranker_walkthrough.ipynb) — the pipeline step by step on the public benchmark, no GPU. *Run it*: [`run_on_your_data.ipynb`](metaphor_search/run_on_your_data.ipynb) — runs the whole pipeline on a public corpus (dry-run without any model, or live against your own Ollama server), then on your own texts. Code in [`pipeline/`](metaphor_search/pipeline/). | [`metaphor_search/`](metaphor_search/) |
| **USAS dictionaries** | Final PyMUSAS-format semantic dictionaries for **Danish** (43,169 entries) and **Dutch** (58,303), built from open sources only, plus the Danish idiom list | [`pymusas/lexicons/`](pymusas/lexicons/) |
| **Build a dictionary for a new language** | *Understand it*: [`build_a_language.ipynb`](pymusas/build_a_language.ipynb) — how the dictionaries were built and evaluated, with the measured numbers, no GPU. *Run it*: [`build_your_language.ipynb`](pymusas/build_your_language.ipynb) — the six stages as runnable cells (smoke setting: minutes; the committee stage is optional and costs about $20 per language in API calls). The committee's calibration against human gold re-scores offline from shipped files. Code in [`lexicon_pipeline/`](pymusas/lexicon_pipeline/). | [`pymusas/`](pymusas/) |
| **Transcription** | Local speech-to-text + speaker diarization for interviews (faster-whisper `large-v3`, pyannote 3.1) | [`speech_to_text/`](speech_to_text/) |

## Running the notebooks

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements-notebooks.txt
.venv/bin/jupyter lab
```

- The two *understand it* notebooks run offline in seconds; they read result files that ship
  with the repo.
- The two *run it* notebooks run without a GPU in their default setting (`DRYRUN` /
  `SMOKE`). For real models point them at an [Ollama](https://ollama.com) server
  (`OLLAMA_URL`) that holds the models you name — that is the only endpoint they know, so
  private text never leaves the machine you choose.
- The transcription notebooks need a GPU, `ffmpeg`, and a HuggingFace token for the
  pyannote models (see [`speech_to_text/README.md`](speech_to_text/README.md)).

## Privacy rules the tools enforce

Aggregation prints counts, rates and ranks — never a phrase or a passage. Reviewing is
one public page, [`demo/review.html`](demo/review.html): a reviewer opens the small
`.json` list they were e-mailed and the page shows it in their language (English, Danish,
Dutch) — the list is read in the browser, nothing is uploaded, and the exported labels hold
candidate ids and verdicts only. A list embeds text and is as private as the corpus it was
built from: send it to named reviewers, keep it on project machines. Published Menu entries are planted into every corpus
as check items, so a ranking that does not surface them near the top is not to be trusted.
