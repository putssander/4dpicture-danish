# USAS-WSD human gold (Finnish, English)

`benedict_fin.txt` (2,068 labelled tokens) and `benedict_eng.txt` (3,468) are the Finnish
and English test files of the USAS-WSD dataset, redistributed unchanged under
CC BY-NC-SA 4.0. Source: https://huggingface.co/datasets/ucrelnlp/USAS-WSD
(Moore, Rayson et al. 2026, https://arxiv.org/abs/2601.09648). They are the only human
labels the recipe uses: the committee is calibrated on them before it grades any new
language. Format: `token_TAG` per token, one sentence per line.
