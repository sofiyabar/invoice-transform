# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project intent

This repository is for building an **evals system for AI-generated invoices** — i.e., evaluating how well an AI model can produce/transform invoice data (e.g., extracting or generating structured invoice fields such as company, date, address, and total) against ground truth.

It is a portfolio project built for a specific job application (Finom, Product Data Scientist — AI Evaluation & Quality). The full brief — 6-layer metric hierarchy, business-impact formulas, dataset priorities, non-negotiable requirements — lives in `.claude/.skills/project_brief.md`. Read it before making architectural decisions; this file only summarizes current state.

## Current state

Scaffolding stage: the top-level directory/module structure exists, but almost all logic is stubbed with `NotImplementedError`/`TODO` — nothing has been implemented yet beyond `data/schema.py` (pydantic models) and the exploratory notebook.

```
generator/     # the invoice generator under evaluation (raw text -> invoice JSON).
               # base_generator.py — TODO: implementation/approach not yet decided.
evals/         # 6-layer eval hierarchy + LLM judges
  layer1_field.py .. layer5_statistics.py
  business_layer.py   # Layer 6, derived — reads only Layer 1-5 outputs + config
  judges/              # DeepEval GEval-based judges
  runner.py
data/          # schema.py (shared contract), loaders.py, synth_generate.py, segment_labeler.py
               # raw/, synthetic/, processed/ (gitignored data dirs)
dashboard/     # Streamlit app + SQL layer (Databricks Free Edition)
config/        # explicit "expert assumption" YAML files (severity weights, business
               # assumptions, segments, field weights) — all placeholders, need real values
tests/         # one test file per module, currently skipped pending implementation
notebooks/     # datasets_searching.ipynb — exploratory history, not cleaned up
scripts/       # run_eval.py, run_stability_check.py CLI entry points
eval_runs/     # timestamped eval run outputs (gitignored)
```

## Known open decisions

- **Base generator**: no implementation or approach chosen yet for `generator/base_generator.py`. Internet search for a suitable open-source "raw text → invoice JSON" repo was explicitly stopped by the user — do not resume that search unprompted. The adapter interface (`generate(raw_text: str) -> dict`) is fixed so this decision doesn't block other layers.
- **`notebooks/datasets_searching.ipynb`**: has an unresolved bug — assumes `priyank-m/SROIE_2019_text_recognition` has a `words` field, but it doesn't (`KeyError: 'words'`). Not fixed; kept as history. Don't invest further in SROIE without checking the brief's dataset priority list first (synthetic data is the primary MVP path, not SROIE).
- **LLM provider**: Anthropic (Claude), for both the generator and the judges. `.env.example` expects `ANTHROPIC_API_KEY`.

## Working in this repo

- Follow the module boundaries above: generator logic only in `generator/`, all metric/judge logic in `evals/`, nothing computed from scratch in `evals/business_layer.py` (Layer 6) — it must only read `metrics_dict` + `config/*.yaml`.
- `config/*.yaml` files are placeholders (`# ASSUMPTION — заполнить`) — fill with real values as part of implementing the layer that consumes them, not speculatively.
- When implementing a layer, replace its `NotImplementedError` and un-skip the corresponding test in `tests/`.
- When real project structure changes (new dependencies, new modules, architecture shifts), update this file to match.
