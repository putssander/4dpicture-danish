# How the metaphor finder works — in plain language

For everyone on the project, including people who never touch the code. It explains what
the system does, what it does *not* do, and how much to trust each number.

---

## The problem

We want a menu of metaphors that Danish cancer patients actually use, so that other
patients can be offered choices: *is your illness a fight, a journey, an uninvited guest, a
stone in your shoe?* The English Metaphor Menu did this by hand. We have far more material
than anyone can read by hand — thousands of interview turns and questionnaire answers.

So a computer proposes candidates and people decide. The whole design follows from that
split. **The machine's job is to hand a human a shortlist worth reading. It is not to
decide what belongs in a menu.**

---

## Step 1 — Cut the text into small pieces

Long texts are split into chunks of two or three sentences, so that every candidate
metaphor comes with enough surrounding words for a person to judge it.

Nothing clever happens here, but two choices matter:

- **Very short answers were nearly lost.** Interviews are cut at 25 words minimum, which
  is fine for spoken turns. Questionnaire answers average nine words, so that rule would
  have thrown away 78% of them. Questionnaires use an 8-word minimum instead. Same
  machinery, one number changed — and we say so, because it affects what gets found.
- **The order is fixed.** If we later process more text, the new material is *added*; the
  earlier pieces keep their identity. Results stay comparable across runs.

## Step 2 — Two different AI models read every piece

Each chunk goes to two AI models from **different families** (think of them as two
readers trained by different teams). Each is asked, in the local language:

> Find all metaphorical expressions in this text, including everyday ones.

Note what is *not* asked. The models are **not** told to look for illness metaphors
specifically. They look for any figurative language at all. Narrowing to illness happens
later, in step 4. This is a deliberate choice with a trade-off, discussed at the end.

Both models run on our own machine. **No patient or participant text ever leaves it** — not
to ChatGPT, not to any company's servers, not to any website.

## Step 3 — Keep only what both models found

If only one model spots something, we drop it. If both models independently point at the
same expression, we keep it.

This is the cheapest possible quality check and it needs no new judgement: two independent
readers agreeing is evidence that something really is figurative. It typically removes
half or more of what was proposed.

What it **cannot** tell us is what the metaphor is *about*. "This traffic is cancer" is a
genuine metaphor that both models would happily agree on — but it is about traffic, not
about illness. That blind spot is exactly why the next step exists.

## Step 4 — Three screens, each catching what the last one missed

Every surviving candidate is put to three questions. Each is a separate model call, so
each can be inspected, changed, or overruled on its own.

| Screen | The question it asks | What it catches |
|---|---|---|
| **Is it about illness?** | Is this expression really *about* the illness, treatment, body, or being a patient? | "This traffic is cancer" — figurative, but about traffic |
| **Is it about the lived experience?** | Is it about living with illness — coping, fear, hope, identity, daily life — rather than the disease as a medical object? | "The tumour is 3 cm" style talk; clinical description |
| **How menu-like is it?** | Score 0–10: how strongly does this resemble entries in the published Metaphor Menu — vivid, personal, something a patient might adopt? | Dead everyday idioms score low; personal images score high |

A fourth, smaller check labels each expression as **everyday** or **vivid**, used only to
break ties.

Two safeguards worth knowing. The model that *scores* candidates comes from a **third**
family, so no model both proposes an expression and rates its own suggestion. And
candidates that fail the first question are placed at the bottom regardless of anything
else — so the expensive screens only run on survivors, which is why this is affordable at
all.

## Step 5 — Sort the list

The final order is a cascade, exactly like sorting a spreadsheet by several columns at
once:

1. First, everything that passed **both** the illness question and the lived-experience question
2. Then, everything that passed the illness question only
3. Then, everything that failed
4. Within each group, by **menu-likeness score**, highest first
5. Ties broken in favour of the **vivid** expression over the everyday one

Near-identical duplicates are merged at this point: if one model found "a huge parenthesis
closing around you" and the other "parenthesis closing around you", that counts as one
candidate, not two. (This was a real bug, fixed on 19 August; it had inflated the lists by
about a third.)

---

## How do we know the order is any good?

This is the part that is easy to get wrong, so it is worth being careful.

**The temptation:** rank the list, read the top of it, and observe that it looks good. That
proves nothing. We built the system, so we would find our own output convincing.

**What we do instead:** we take metaphors that are *already known to be good* — entries
from the published English Metaphor Menu, and translations of them into Dutch and Danish —
and we **hide them inside the pile** of real mined candidates. Crucially, they are pushed
through the same extraction step as everything else, so they are indistinguishable in
format from ordinary candidates. Then we ask a simple question:

> Did the system push the known-good items to the top?

It did, in all three collections we tested:

| Collection | List length | Where the known-good items landed |
|---|---|---|
| English (public COVID forums) | 1,490 | top 8% |
| Dutch (kanker.nl) | 6,330 | top 4% |
| Danish (interviews + questionnaire) | 5,239 | top 9% |

(Median position of the planted items. A few planted entries were also quoted as examples
inside the scoring prompt; those are not counted — they would be scored partly against
themselves — and are removed before ranking.)

In the English collection we also hid **known-bad** items: figurative uses of disease words
that are not about illness at all ("this traffic is cancer"). Only **one of 88** reached the
top tenth, and three quarters fell into the bottom half. So the system pushes the right
things up *and* the wrong things down.

## The single most useful finding so far

Danish material comes from two sources, and they are not equally worth collecting:

| Source | Candidates about lived illness experience | Strong menu candidates (score ≥7) |
|---|---:|---:|
| **Questionnaire free text** | **48.8%** | **15.5%** |
| Interviews (colorectal) | 12.8% | 0.8% |
| Interviews (mamma) | 8.5% | 0.7% |

Asking people **in writing** to describe their experience produced roughly twenty times
more strong menu candidates, proportionally, than transcribing interviews. This is not
because questionnaires contain more words — these are percentages, not totals. It is
because a questionnaire asks directly about the experience, so answers are about the
experience. Interviews contain the same people, but also scheduling, clinical detail, and
the interviewer talking.

**For planning: the format of the question is a lever.** A short written prompt is cheaper
than an interview *and* returned better material.

---

## What this does not tell you

Please read this section before quoting any number above.

- **No patient has judged any of it.** "Good" here means good *by the system's own
  criteria*. Whether these metaphors actually help patients is a question only patients and
  PPI contributors can answer, and that has not happened yet.
- **The known-good test has a hidden dependency.** Hidden items land near the top partly
  because of what surrounds them. When we added the questionnaire to the Danish collection,
  the hidden items *appeared* to do worse — not because the system got worse, but because
  the questionnaire supplied hundreds of genuinely good candidates that now compete for the
  same top slots. Positions are relative to the company they keep.
- **The 0–10 scores are not calibrated.** They cluster low (average 3.4–4.0). Trust the
  *order*, not the number.
- **We tested with 14 hidden items per language.** That is a real signal but a small one.
- **The known-good items are translations**, which may read more formally than spontaneous
  speech. If a human can spot them by style rather than quality, the test is weaker than it
  looks. The blinded human session is designed to find out.
- **The questionnaire advantage may be partly an artefact.** Written answers to a direct
  question might simply be *easier for the models to classify* than conversational speech.
  Only human judgement separates "better metaphors" from "easier to score".

## Something we tried that did not work

We asked the models to label each metaphor with the *kind of thing* illness was being
compared to — travel, weather, warfare, machinery — using a standard semantic
classification (USAS). If that had worked, we could answer the project's central question
directly: what is illness most often framed as?

It did not work — because of how *we* asked, not because of the classification. The
instruction included two examples of what a code looks like, and the models simply reused
those two examples for 76–95% of everything they labelled. In the
Danish questionnaire data, one of them — the code for *weather* — was applied to 86% of
candidates, which is obviously not a fact about how Danes describe cancer.

Two things are worth taking from this. First, structured-looking output is not evidence:
these were valid codes in a valid format that meant nothing. Second, it did no damage,
because the ranking never used this field — the screens ask their questions in ordinary
language. We have removed the examples from the instruction, and answering the
source-domain question properly needs a separate labelling pass, which has not been run.

## One design choice worth understanding

The project's central idea is to fix illness as the topic and ask what it is being compared
to. There are two ways to do that, and we now have names for them:

- **Asking narrow** — tell the model up front to find metaphors *about illness*. The
  narrowing happens during the search. (Technically: *target-conditioned*.)
- **Asking wide, then filtering** — let the model find any metaphor, then ask of each one
  "is this about illness?" The narrowing happens afterwards. (Technically:
  *target-screened*.)

Both end at the same kind of result. They differ in practice:

- **Asking narrow** gives a shorter, tighter list, and the model does the narrowing.
- **Asking wide, then filtering** gives a longer list, but it catches expressions where the
  illness is implied rather than named, and it puts the narrowing in a step we can read,
  adjust and re-run without re-processing all the text.

We have both on Danish material, and comparing them was informative. Asking wide and
filtering re-found 61% of what asking narrow had found. That sounds like a loss until you
look at the *top* of the ranked list, which is the only part anyone reads for a menu: there,
61% of the top 100 is material both approaches found, against just 21% across the list as a
whole. The two approaches converge on the same best material, arrived at independently.
And 39% of that top 100 was found *only* by asking wide — a large share of a 15-30 entry
shortlist that would otherwise not exist.

The evidence in this report is for the second route. Which ranks better has not been
tested, and saying so is more useful than guessing.

---

*Technical detail: `RANKER_EVAL_REPORT.md`. Reproduction: `metaphor_extraction/evals/REPRODUCE.md`.
Corrections and how to re-verify them: `RANKER_CORRECTIONS_2026-08-19.md`.*
