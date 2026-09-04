# Teaching a computer what Danish and Dutch words mean

## What this is

When researchers study large collections of text, they often want to know not just which
words occur but what those words are *about*: health, movement, emotion, money, family,
time. A **semantic tagger** does this automatically. It reads a text and attaches a meaning
category to every word, so that "surgeon", "tumour" and "recovery" all land under *health
and disease*, while "journey", "road" and "destination" land under *movement*. Once every
word carries such a label, you can ask questions of a whole corpus at once: how much of
this patient forum talks about illness in terms of travel, or fighting, or weather?

The best-known system of this kind is **USAS** ([UCREL Semantic Analysis System](https://ucrel.lancs.ac.uk/usas/)), developed at Lancaster University. Its
category scheme has 21 broad fields and about 230 finer ones, and its English dictionary,
built by hand over two decades, holds tens of thousands of words with their categories in
order of likelihood. The open-source software **PyMUSAS** ([documentation](https://ucrel.github.io/pymusas/), [code](https://github.com/UCREL/pymusas)) applies such a dictionary to text
in any language for which a dictionary exists; the dictionaries themselves are collected in the [Multilingual-USAS](https://github.com/UCREL/Multilingual-USAS) repository, where our 2024 Danish contribution lives as the official Danish entry.

That is the catch. A good dictionary existed for English and a few other languages. For
Danish there was none until this project contributed one in 2024, and that first version
depended partly on a commercial translation service. For Dutch the available dictionary
had only about 4,000 words, roughly one in ten of what the English one holds. The 4D
PICTURE project needed to tag Danish and Dutch cancer-patient texts, so we built new
dictionaries for both languages from open sources only, and we release them here.

## How the dictionaries were built

The recipe has four steps, and all of them run on ordinary hardware without paid services.

1. **Translate the English dictionary word by word** with an open-weights language model
   (Qwen), keeping each word's part of speech and its ordered list of categories.
   Translation is efficient because it carries the English categories across without
   labelling every word again.
2. **Add words the translation missed** from two free lexical resources: Wiktionary, and
   the language's own WordNet (DanNet for Danish, Open Dutch WordNet for Dutch), linked to
   the English dictionary through shared concept identifiers.
3. **Repair**: remove broken records, duplicates and multi-word strings that the tagger
   could never match. The repair rules reproduce the two review rounds Lancaster applied
   to our 2024 Danish submission, so they act as a release gate.
4. **Validate** the idiom list separately, since multi-word patterns have their own syntax.

The result is a plain text file anyone can open, inspect, correct and version. The Danish
file holds 43,169 words, the Dutch one 58,303. A separate Danish list of 30,516 idioms and
fixed expressions is included as an optional extra.

## How we checked them without a single human annotator

A dictionary is only useful if its categories are right, and checking that normally means
paying linguists to label thousands of words by hand. For Danish and Dutch no such
hand-labelled test set exists anywhere, and the project had no budget to create one.

We used a committee of three AI models from three different companies (Claude, GPT and
Gemini). Each model labels every word of a test text on its own, without seeing the
others' answers. Where all three agree, we take that label as the reference. The reason
this is more than wishful thinking is **calibration**: Finnish and English do have
human-labelled test texts, so we ran the same committee there first and measured how often
its answers matched the human experts. The result is the table further down. In short:
where all three models agree, they match the experts about 85 to 88 times in a hundred.
Where they disagree, the majority vote is right only about half the time. So we treat the
unanimous labels as the answer key and report scores on those.

Two guardrails keep this honest. The model that translated the dictionaries and the test
texts (Qwen) is a fourth, separate family, so no model ever grades its own homework. And
the same three families grade every language, so scores are comparable across languages
in construction, even though we still only compare dictionaries within a language.

## The test texts

Four texts were used to score the dictionaries. All of them are shipped in
[`lexicon_pipeline/data/`](lexicon_pipeline/data/) so every number below can be re-computed.

| Name used below | What it is | Size per language | Who labelled it | Where it comes from |
|---|---|---|---|---|
| **Coffee text** | A short history of coffee from a Finnish coffee website, the standard USAS test text since 2003. It exists in Finnish and English with labels by human experts, and we translated it into Danish and Dutch. | 73 sentences; 2,068 (fi), 3,468 (en), 3,399 (da), 3,675 (nl) words | Finnish and English: linguists (Löfberg et al. 2003). Danish and Dutch: the three-model committee | [USAS-WSD on Hugging Face](https://huggingface.co/datasets/ucrelnlp/USAS-WSD); our translations in [`data/references/`](lexicon_pipeline/data/references/) |
| **Talks sample** | 50 sentences of TED talk subtitles, the same 50 in English, Danish, Dutch and Finnish. Spoken, everyday language. | 50 sentences; 468–729 words | The committee | [TED2020 on OPUS](https://opus.nlpl.eu/TED2020/); shipped as `talks_*.txt` |
| **Health sample** | 50 sentences from the European Centre for Disease Prevention and Control, the same 50 in the four languages. Public-health communication, the register closest to the project's patient texts. | 50 sentences; 589–886 words | The committee | [ECDC translation memory on OPUS](https://opus.nlpl.eu/ECDC/); shipped as `health_*.txt` |
| **Finnish and English gold** | The human-labelled coffee text, used only to measure how good the committee is. | 2,068 and 3,468 words | Linguists | shipped in [`data/usas_wsd/`](lexicon_pipeline/data/usas_wsd/) |

The talks and health samples are small on purpose: they show whether the coffee-text
result carries over to two very different kinds of language, not to give precise scores.

## Results: how well do the dictionaries work

Each score is the share of words whose first category matched the reference exactly. The
number after `@` is coverage: the share of words for which the dictionary had any answer
at all. Both matter, because a dictionary can look more accurate simply by answering less.
For the coffee text we give two columns: scored only on the words where the committee was
unanimous (the labels close to human quality), and scored on all words.

| Dictionary | Coffee text, unanimous words | Coffee text, all words | Talks sample | Health sample |
|---|---|---|---|---|
| Danish, 2024 official release | 55.9 @ 78.7 | 50.3 @ 77.8 | 63.3 @ 84.4 | 52.9 @ 77.1 |
| **Danish `da_open` (this release)** | **65.4 @ 88.4** | **57.8 @ 86.8** | **68.7 @ 91.5** | **59.4 @ 85.6** |
| Dutch, current official (4,220 words) | 44.5 @ 70.4 | 38.2 @ 67.7 | 40.8 @ 71.6 | 34.3 @ 61.9 |
| **Dutch `nl_open` (this release)** | **70.1 @ 93.4** | **61.1 @ 91.2** | **68.2 @ 92.0** | **60.4 @ 89.3** |
| English hand-built dictionary, for scale, scored on human labels | — | 72.4 | 74.8 @ 97.9 | 71.2 @ 94.5 |

Reading the table: the new Danish dictionary answers more words and agrees with the
reference more often than the 2024 release. The Dutch gain is larger because the old
dictionary was so small. Neither reaches the hand-built English dictionary, which is the
ceiling to aim for. If you add a neural fallback for words the dictionary does not know
(dictionary first, a multilingual model for the rest), the talks and health scores rise to
71.4 and 64.5 for Danish and 70.8 and 64.3 for Dutch.

## How much to trust the committee

Measured on the human-labelled coffee text in Finnish and English, every word, through the
three vendors' APIs. Anyone can re-run this check without an API key:
`python lexicon_pipeline/score_calibration_classes.py`.

| What the committee did | Finnish: share of words → correct | English: share of words → correct |
|---|---|---|
| All three models agreed | 69.1% → **85.5%** | 79.0% → **88.2%** |
| Only two agreed (majority vote) | 26.5% → 48.4% | 19.0% → 56.2% |
| All three differed (strongest model decides) | 4.4% → 46.7% | 2.0% → 35.3% |
| The combined reference, all classes | 74.0% | 81.1% |
| The best single model on its own | 75.2% | 81.3% |

## What this cannot tell you

Every Danish and Dutch test word sits in translated text, not in text originally written
in those languages. The Dutch text was rewritten by a native speaker before labelling; the
Danish text was not. No native speaker checked the category labels themselves. The scores
therefore show which dictionary is better within a language. They are not a promise of
absolute accuracy, and any high-stakes use should add a human check on the texts at hand.

## Use it, or build your own

| What | Where |
|---|---|
| The dictionaries, ready for PyMUSAS with the matching spaCy model | [`lexicons/`](lexicons/) |
| Understand it: the whole story with every number drawn from result files, runs in seconds without a GPU | [`build_a_language.ipynb`](build_a_language.ipynb) |
| Run it: the recipe as cells, for any language with a spaCy model | [`build_your_language.ipynb`](build_your_language.ipynb) |
| The scripts behind each step | [`lexicon_pipeline/`](lexicon_pipeline/) |
| Every number shown in the notebook | [`results_index.json`](results_index.json) |

Cost to add a language, at August 2026 list prices: translating the 54,000-entry English
list with a local open-weights model is free and takes about two hours on one GPU, or
roughly $5 to $15 through an API; enrichment, repair and scoring are free and take minutes
on a laptop; the optional committee reference, which translates and labels a 3,300-word
test text with three commercial models, costs about $20 and under an hour.

## Official USAS and PyMUSAS resources

| Resource | Link |
|---|---|
| USAS semantic tagger and category scheme (UCREL, Lancaster University) | https://ucrel.lancs.ac.uk/usas/ |
| The USAS tagset, all categories with descriptions | https://ucrel.lancs.ac.uk/usas/semtags.txt |
| PyMUSAS documentation, including how to load a custom lexicon | https://ucrel.github.io/pymusas/ |
| PyMUSAS source code | https://github.com/UCREL/pymusas |
| Multilingual-USAS: the official dictionaries for all languages, including Danish | https://github.com/UCREL/Multilingual-USAS |
| USAS-WSD: the human-labelled test sets used for calibration | https://huggingface.co/datasets/ucrelnlp/USAS-WSD |
| The PyMUSAS paper (Moore, Rayson et al. 2026) | https://arxiv.org/abs/2601.09648 |
| The multilingual lexicon papers (Piao et al. 2015, 2016) | https://aclanthology.org/N15-1137/ , https://aclanthology.org/L16-1416/ |

## Licences and credits

USAS and its English dictionary are the work of [UCREL](https://ucrel.lancs.ac.uk/), Lancaster University, released as
CC BY-NC-SA 4.0 in [Multilingual-USAS](https://github.com/UCREL/Multilingual-USAS); the Danish and Dutch dictionaries derive from it and from Wiktionary,
DanNet and Open Dutch WordNet. The shipped Finnish and English human-labelled test files
are the USAS-WSD test sets (CC BY-NC-SA 4.0; Moore, Rayson et al. 2026). The work was done
in Work Package 3 of the EU-funded 4D PICTURE project.
