# Metaphor search walkthrough

`ranker_walkthrough.ipynb` walks through the pipeline end to end on public data — cutting
text into passages, mining candidates with two local model families, keeping only what
both found, the screens, the composite ranking, and the check that hidden known-good and
known-bad items land where they should. Run it from this folder; it reads
`corona_benchmark_dehydrated.json` and needs no GPU, key or network.

The data file holds every screen verdict, score, rank, USAS code and span offset for
1,503 candidates from the public #ReframeCovid / Reddit COVID-19 set. Reddit post text is
not redistributed — post ids and character offsets are shipped instead; text is included
only for the open-licensed planted items (#ReframeCovid, CC; published Metaphor Menu).
