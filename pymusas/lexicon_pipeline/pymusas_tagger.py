"""Build PyMUSAS taggers for the baseline evaluation.

Two ways to obtain a tagger:

  * ``from_released_model("en_dual_none_contextual")`` — a released UCREL PyMUSAS model
    (installed as a Python package), the standard configuration for English.
  * ``from_lexicons(single_tsv, mwe_tsv, spacy_model)`` — an arbitrary lexicon pair, which
    is how this project's own Danish lexicons are evaluated.

Both return a spaCy pipeline whose tokens carry ``token._.pymusas_tags``.
"""

import re

import spacy
from pymusas.lexicon_collection import LexiconCollection, MWELexiconCollection
from pymusas.rankers.lexicon_entry import ContextualRuleBasedRanker
from pymusas.taggers.rules.mwe import MWERule
from pymusas.taggers.rules.single_word import SingleWordRule
from pymusas.spacy_api.taggers import rule_based  # noqa: F401  (registers the component)

UNMATCHED = {"Z99", "Z9", "PUNCT", ""}
# Tags that carry no semantic-domain content and must not count as a "different domain"
CLOSED_CLASS = {"Z", "T", "N", "A"}   # Z proper/grammatical, plus very generic fields


UCREL_RAW = ("https://raw.githubusercontent.com/UCREL/Multilingual-USAS/master/"
             "{lang_dir}/{filename}")
ENGLISH_SINGLE = UCREL_RAW.format(lang_dir="English", filename="semantic_lexicon_en.tsv")
ENGLISH_MWE = UCREL_RAW.format(lang_dir="English", filename="mwe-en.tsv")


def from_released_model(model_name="en_dual_none_contextual",
                        spacy_model="en_core_web_sm"):
    """Load a released PyMUSAS model package and attach it to a spaCy pipeline.

    NOTE: the published model wheels were built against older spaCy versions and fail on
    spaCy >= 3.7 with ``load_model_from_init_py() got an unexpected keyword argument
    'enable'``. Prefer :func:`from_lexicons`, which builds the same rule-based tagger from
    the lexicon TSVs and works on current spaCy — and which is also the only option for
    this project's Danish lexicons, so both languages then use an identical code path.
    """
    nlp = spacy.load(spacy_model, exclude=["ner"])
    tagger_pipeline = spacy.load(model_name)
    nlp.add_pipe("pymusas_rule_based_tagger", source=tagger_pipeline)
    return nlp


def from_lexicons(single_tsv, mwe_tsv=None, spacy_model="en_core_web_sm",
                  pos_mapper=None):
    """Build a tagger from lexicon TSV files (local paths or URLs)."""
    nlp = spacy.load(spacy_model, exclude=["ner"])
    single = LexiconCollection.from_tsv(single_tsv)
    single_lemma = LexiconCollection.from_tsv(single_tsv, include_pos=False)
    rules = [SingleWordRule(single, single_lemma, pos_mapper=pos_mapper)]
    if mwe_tsv:
        rules.append(MWERule(MWELexiconCollection.from_tsv(mwe_tsv),
                             pos_mapper=pos_mapper))
    ranker = ContextualRuleBasedRanker(
        *ContextualRuleBasedRanker.get_construction_arguments(rules))
    tagger = nlp.add_pipe("pymusas_rule_based_tagger")
    tagger.rules = rules
    tagger.ranker = ranker
    return nlp


CODE_RE = re.compile(r"^([A-Z]\d*(?:\.\d+)*)")


def normalise_tag(tag):
    """Reduce ONE raw USAS tag to the list of bare codes it asserts.

    PyMUSAS tags carry polarity and other markers (``S5+c``, ``Z1mf``, ``N5++``,
    ``A5.1-``) and may be *multi-field*: ``L2/S9mfn`` asserts that the word belongs to
    BOTH ``L2`` and ``S9``. Returning only the first field would silently discard a
    correct assignment, so every field is returned. Grammatical/unmatched bins (``Z*``)
    are dropped.
    """
    if not tag:
        return []
    codes = []
    for field in str(tag).split("/"):
        m = CODE_RE.match(field.strip())
        code = m.group(1) if m else ""
        if code and code not in UNMATCHED and not code.startswith("Z"):
            codes.append(code)
    return codes


def token_tags(token, top_n=1):
    """Bare USAS codes for a token, from its ``top_n`` highest-ranked candidate tags.

    ``top_n`` exists so the lexicon can be given the same number of chances as whatever it
    is compared against (see the fairness protocol in run_pymusas_baseline.py).
    """
    tags = getattr(token._, "pymusas_tags", None) or []
    out = []
    for tag in tags[:top_n]:
        for code in normalise_tag(tag):
            if code not in out:
                out.append(code)
    return out


def token_tag(token):
    """Single top-ranked bare USAS code for a token, or '' when unmatched/grammatical."""
    codes = token_tags(token, top_n=1)
    return codes[0] if codes else ""


def _head_token(doc):
    """The semantically decisive token of a short span: its last content token.

    For English noun phrases the head is usually final ('the fairground ride' -> 'ride').
    """
    head = None
    for tok in doc:
        if tok.is_punct or tok.is_stop:
            continue
        if getattr(tok._, "pymusas_tags", None):
            head = tok
    return head


def span_tags(nlp, text, top_n=1, whole_span=False):
    """USAS codes for a span.

    ``top_n``      how many of the lexicon's ranked candidate tags to accept, so the
                   lexicon can be given exactly as many chances as the system it is
                   compared with.
    ``whole_span`` if True, pool codes from every content token rather than only the head
                   token. Off by default: the comparison target produces one code for the
                   span, so pooling would give the lexicon more chances than its rival.
    """
    doc = nlp(str(text))
    if whole_span:
        out = []
        for tok in doc:
            if tok.is_punct or tok.is_stop:
                continue
            for code in token_tags(tok, top_n):
                if code not in out:
                    out.append(code)
        return out
    head = _head_token(doc)
    return token_tags(head, top_n) if head is not None else []


def span_tag(nlp, text):
    """Single best USAS code for a span (head token, top-ranked tag), or ''."""
    codes = span_tags(nlp, text, top_n=1)
    return codes[0] if codes else ""
