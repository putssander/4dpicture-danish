# USAS dictionaries for Danish and Dutch

PyMUSAS-format semantic lexicons. Every entry carries USAS tags ordered
most-prominent-first. Built by open-weights translation of the UCREL English lexicon,
enriched from Wiktionary and the language's WordNet (DanNet, Open Dutch WordNet); no
closed service was used, so the files can be redistributed.

| File | Entries | Use |
|---|---|---|
| `da/semantic_lexicon_da_open.tsv` | 43,169 | Danish single-word lexicon — **use this** |
| `da/mwe_da_ALL.tsv` | 30,516 | Danish multi-word expressions / idioms (optional, add for idiom recognition) |
| `nl/semantic_lexicon_nl_open.tsv` | 58,303 | Dutch single-word lexicon — **use this** |

Format: `lemma<TAB>pos<TAB>tag1 tag2 …` (single-word) and
`mwe_template<TAB>tags` (MWE), the same as UCREL's
[Multilingual-USAS](https://github.com/UCREL/Multilingual-USAS) files, so they drop into
a [PyMUSAS](https://ucrel.github.io/pymusas/) rule-based tagger via its lexicon-collection
loaders (`LexiconCollection.from_tsv` / `MWELexiconCollection.from_tsv`) with the matching
spaCy model (`da_core_news_sm`, `nl_core_news_sm`).

## How well do they work

Exact top-1 accuracy @ coverage (share of words that got any answer). Danish and Dutch
have no human-labelled USAS test set, so the reference is a three-model committee
(Claude, GPT, Gemini) calibrated on Finnish and English human gold: where all three
agree, the label matched the human one 85.5% (Finnish) and 88.2% (English) of the time;
where they disagree it is about a coin flip. The **unanimous** column is therefore the
primary comparison; the "all tokens" column includes the weaker labels. The talks and health
samples are the same 50 TED2020 and ECDC sentences in every language; the test texts are
described in [`../README.md`](../README.md). All numbers compare dictionaries
within one language; they are not absolute accuracy claims.

| Lexicon | Coffee text, unanimous words | Coffee text, all words | Talks sample | Health sample |
|---|---|---|---|---|
| Danish, 2024 official release | 55.9 @ 78.7 | 50.3 @ 77.8 | 63.3 @ 84.4 | 52.9 @ 77.1 |
| **Danish `da_open`** | **65.4 @ 88.4** | **57.8 @ 86.8** | **68.7 @ 91.5** | **59.4 @ 85.6** |
| Dutch, current official (4,220 entries) | 44.5 @ 70.4 | 38.2 @ 67.7 | 40.8 @ 71.6 | 34.3 @ 61.9 |
| **Dutch `nl_open`** | **70.1 @ 93.4** | **61.1 @ 91.2** | **68.2 @ 92.0** | **60.4 @ 89.3** |
| English hand-built (ceiling reference, human gold) | — | 72.4 | 74.8 @ 97.9 | 71.2 @ 94.5 |

Unanimous tokens: 2,182 of 2,958 (Danish), 2,522 of 3,307 (Dutch). Adding a neural
fallback for words the dictionary does not cover (lexicon + BEM) raises Danish to
71.4 / 64.5 and Dutch to 70.8 / 64.3 on the talks / health samples.

Known limits, stated once: every Danish and Dutch test token is translated text (the
Dutch text was rewritten by a native speaker, the Danish text was not), and no native
speaker checked the semantic labels. The calibration itself is reproducible offline with
`../lexicon_pipeline/score_calibration_classes.py`; how every other number was obtained
is in [`../build_a_language.ipynb`](../build_a_language.ipynb).
