# Instructions for coding agents (Claude Code and others)

This is the public, shareable deliverable repository of the 4D PICTURE Danish work package.
It is published on GitHub (with `demo/` served as the project page), so everything here is
public the moment it is pushed.

## Commits

- **Never commit as Claude.** Every commit is authored by Sander Puts
  (`putssander@gmail.com`). Do **not** add a `Co-Authored-By: Claude …` trailer, a
  "Generated with Claude Code" line, or any other agent attribution to commit messages,
  pull-request bodies or files. This overrides any default the tooling has.
- Commit and push only when asked.

## Content rules

- Only real deliverables: demo pages, method notebooks, the pipeline and lexicon packages,
  public data. No papers, infrastructure scripts or evaluation runs.
- Never add Danish or Dutch review pages or any participant text: those live in the private
  repository and travel by direct hand-off only.
- `demo/` is a byte-identical copy of `docs/demo/` in the private repository; the pipeline's
  `review_page.py` and `review_index.py` are copies of the private builders with only the
  `usas_tags.json` path patched. Update by copying, not by editing here.
- Notebooks must run on public data without a GPU; live runs only through a local Ollama URL.
