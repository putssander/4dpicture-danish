# Evaluation texts for Danish and Dutch (committee-labelled)

Every file has one sentence per line and one label per word, written `word_TAG`, the
format PyMUSAS and the USAS-WSD gold files use. The labels come from the three-model
committee (Claude Fable 5, GPT-5.6, Gemini 3.1 Pro), not from people; see
`../../score_calibration_classes.py` for how trustworthy each label class is.

| File | Sentences | Words | Text origin | Labels |
|---|---|---|---|---|
| `coffee_dan.txt`, `coffee_nld.txt` | 73 | 3,399 / 3,675 | The Finnish coffee-website text of Löfberg et al. (2003), the same text that carries the Finnish and English human labels in [USAS-WSD](https://huggingface.co/datasets/ucrelnlp/USAS-WSD). Translated from English by Qwen; the Dutch version was then rewritten by a native speaker, the Danish version was corrected only where two model families agreed a sentence was broken. | Full committee reference: unanimous label, else majority, else the strongest model's label |
| `coffee_dan_unanimous.txt`, `coffee_nld_unanimous.txt` | 73 | same | same | Only words where all three models agreed keep their label; the others are marked `_PUNC` and are skipped by the scorer |
| `talks_{eng,dan,nld,fin}.txt` | 50 | 468–729 | Subtitle sentences from [TED2020 on OPUS](https://opus.nlpl.eu/TED2020/) (Reimers and Gurevych 2020), the same 50 sentences in all four languages, aligned through their English original. Spoken, narrative register. | Committee reference, punctuation removed |
| `health_{eng,dan,nld,fin}.txt` | 50 | 589–886 | Sentences from the [ECDC translation memory on OPUS](https://opus.nlpl.eu/ECDC/) (European Centre for Disease Prevention and Control, 2016), the same 50 sentences in all four languages. Public-health communication register. | Committee reference, punctuation removed |

The Finnish and English legs of the talks and health samples exist so the same sentences
can be scored in a language that also has a hand-built dictionary; they were labelled by
the same committee. Human-labelled gold exists only for the coffee text in Finnish and
English, in `../usas_wsd/`.

Licences: the coffee text is CC BY-NC-SA 4.0 (USAS-WSD); TED2020 is CC BY-NC-ND 4.0 and
is quoted here as 50 unmodified sentences with their official translations; the ECDC
material is released by ECDC for reuse with attribution. The labels added here are
CC BY-NC-SA 4.0.
