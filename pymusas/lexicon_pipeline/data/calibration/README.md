# Saved committee answers on the human gold

One JSON per annotator and language: `{sentence: {token_index: USAS_code}}` for every
token of `benedict_fin.txt` / `benedict_eng.txt`, produced through the three vendors'
APIs on 2026-08-14 (Claude Fable 5, GPT-5.6, Gemini 3.1 Pro; same prompt and tagset as
`usas_llm.py`). `python score_calibration_classes.py` scores them offline — no API call —
and prints the calibration card used in the notebooks and in the paper.
