# PyMUSAS dictionaries for Danish and Dutch, and the recipe for any language

| What | Where |
|---|---|
| The released dictionaries (use these) | [`lexicons/`](lexicons/) — `da/semantic_lexicon_da_open.tsv` (43,169 entries), `da/mwe_da_ALL.tsv` (30,516 idioms), `nl/semantic_lexicon_nl_open.tsv` (58,303) |
| Understand it: how they were built and evaluated, every number from result files, no GPU | [`build_a_language.ipynb`](build_a_language.ipynb) |
| Run it: the six stages as cells for a new language | [`build_your_language.ipynb`](build_your_language.ipynb) |
| The scripts behind each stage | [`lexicon_pipeline/`](lexicon_pipeline/) |
| Every number the notebook shows | [`results_index.json`](results_index.json) |

## Results

Exact top-1 accuracy @ coverage (share of words that got any answer). Danish and Dutch have
no human-labelled USAS test set, so "own reference" is a three-model committee reference
(Claude, GPT, Gemini). Its **unanimous** labels are the primary comparison; see the
calibration below for why. The two PAR columns are the same 50 public sentences in every
language (TED2020 talks, ECDC health text). Compare rows within one language only.

| Lexicon | Own reference, unanimous tokens | Own reference, all tokens | Talks (PAR) | Health (PAR) |
|---|---|---|---|---|
| Danish, 2024 official release | 55.9 @ 78.7 | 50.3 @ 77.8 | 63.3 @ 84.4 | 52.9 @ 77.1 |
| **Danish `da_open`** | **65.4 @ 88.4** | **57.8 @ 86.8** | **68.7 @ 91.5** | **59.4 @ 85.6** |
| Dutch, current official (4,220 entries) | 44.5 @ 70.4 | 38.2 @ 67.7 | 40.8 @ 71.6 | 34.3 @ 61.9 |
| **Dutch `nl_open`** | **70.1 @ 93.4** | **61.1 @ 91.2** | **68.2 @ 92.0** | **60.4 @ 89.3** |
| English hand-built (ceiling, human gold) | — | 72.4 | 74.8 @ 97.9 | 71.2 @ 94.5 |

With a neural fallback for uncovered words (dictionary first, BEM for the rest) the PAR
scores rise to 71.4 / 64.5 (Danish) and 70.8 / 64.3 (Dutch).

## How much to trust the committee reference

Measured on the two languages that have human labels, all tokens, through the vendors'
APIs. Reproduce offline: `python lexicon_pipeline/score_calibration_classes.py`.

| Label class | Finnish: share of tokens → correct | English: share of tokens → correct |
|---|---|---|
| All three models agree | 69.1% → **85.5%** | 79.0% → **88.2%** |
| Only two agree (majority vote) | 26.5% → 48.4% | 19.0% → 56.2% |
| All differ (strongest model decides) | 4.4% → 46.7% | 2.0% → 35.3% |
| Combined reference | 74.0% | 81.1% |
| Best single model alone | 75.2% | 81.3% |

Unanimous labels are close to human quality; disagreements are a coin flip. Score a new
dictionary on the unanimous tokens and report the share of tokens that reached unanimity.

## Known limits

Every Danish and Dutch test token is translated text (the Dutch text was rewritten by a
native speaker, the Danish text was not), and no native speaker checked the semantic
labels. The scores compare dictionaries within a language; they are not absolute accuracy.

## Cost to add a language (August 2026 list prices)

| Stage | Cost |
|---|---|
| Translate the 54k-entry English list with a local open-weights model (Qwen via Ollama) | free, about two hours on one GPU; roughly $5–15 via an API instead |
| Wiktionary and WordNet enrichment, repair, validation | free, CPU minutes |
| Committee reference: translate and post-edit a 3,300-word text, tag with three API families | about $20, under an hour |
| Scoring | free, CPU minutes |

## Licences

The dictionaries derive from UCREL's Multilingual-USAS (CC BY-NC-SA 4.0), Wiktionary,
DanNet and Open Dutch WordNet. The shipped Finnish and English gold files are the USAS-WSD
test sets (CC BY-NC-SA 4.0, Moore, Rayson et al. 2026).
