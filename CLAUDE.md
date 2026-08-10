# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project intent

This repository is for building an **evals system for AI-generated invoices** — i.e., evaluating how well an AI model can produce/transform invoice data (e.g., extracting or generating structured invoice fields such as client, address, and line items) against ground truth.

It is a portfolio project built for a specific job application (Finom, Product Data Scientist — AI Evaluation & Quality). The full brief — 6-layer metric hierarchy, business-impact formulas, dataset priorities, non-negotiable requirements — lives in `.claude/.skills/project_brief.md`. Read it before making architectural decisions; note it still describes Layer 3 as a standalone layer, which the implementation has since merged into Layer 2 (see below) — the brief hasn't been rewritten to match, only annotated.

## Current state

Layers 0-2 and the generator are implemented and tested (`pytest` — 60 passed, 3 skipped). Layer 4 is partially implemented with explicitly labeled stubs/assumptions. Layers 5 and 6 are not implemented yet.

**Before tracing how data flows between files, read `DATA_MAP.md` first** — it has the full pipeline diagram, the file-by-file "what lives where" table, and the complete `metrics_dict` schema (keys/types/producer for every layer's output). Don't re-derive that from `evals/runner.py` by hand; `DATA_MAP.md` is kept in sync with it.

```
generator/                  # the invoice generator under evaluation (raw text -> invoice JSON)
  base_generator.py          # Gemini-based extraction, prompt copied from Finvoice-AI aiController.js
  intent_gate.py              # Layer 0 Step 1: is-invoice-intent classifier
  completeness_gate.py        # Layer 0 Step 2: data sufficiency check (deterministic logic)
  pipeline.py                  # wires intent gate -> completeness gate -> base_generator into one call
evals/                      # eval hierarchy + LLM judges
  layer0_intent_gate.py        # scoring for generator/intent_gate.py (FP/FN rates kept separate)
  layer0_completeness_gate.py  # scoring for generator/completeness_gate.py
  layer1_field.py               # field-level: exact / numeric-tolerance / judge-free fuzzy text match
  layer2_document.py            # document-level (resolution rate, critical error rate) +
                                  # by_group() -- former Layer 3 segment-level breakdown, merged in here
  layer4_production_sim.py      # latency (estimate, not yet measured), CSAT proxy (stub), batch trend (TODO)
  layer5_statistics.py          # TODO -- bootstrap CI, judge stability/kappa, segment significance
  business_layer.py             # Layer 6, derived -- TODO, must only read Layer 0-5 outputs + config
  judges/                       # DeepEval GEval-based judges (field_judge.py implemented, optional
                                  # re-score path; reviewer_judge.py TODO, needed for real Layer 4 CSAT)
  runner.py                     # orchestrates a run, writes eval_runs/*.json
data/          # schema.py (shared contract), loaders.py (reads data/synthetic/eval_dataset.jsonl),
               # synth_generate.py / segment_labeler.py (TODO stubs -- dataset was generated via the
               # .claude/.skills/*.md process instead, not through these)
               # data/synthetic/ has the real dataset + dataset_manifest.md + generation_notes.md
dashboard/     # Streamlit app + SQL layer (Databricks Free Edition). app.py renders Layer 0-2 for
               # real from eval_runs/*.json; Layer 3-6 tabs are an explicit "Not implemented yet"
config/        # explicit "expert assumption" YAML files. business_assumptions.yaml and
               # severity_weights.yaml are still all-zero placeholders (needed for Layer 6).
               # field_weights.yaml is deprecated/unused (see its own header comment).
               # segments.yaml's comment still references the now-deleted layer3_segment.py.
tests/         # one file per module; test_business_layer.py and test_generator.py still skipped
               # (waiting on Layer 6 and on generator output-shape decisions, respectively).
               # No dedicated tests yet for runner.py, dashboard/app.py, loaders.py, field_judge.py,
               # or the scripts/ entry points.
notebooks/     # datasets_searching.ipynb -- exploratory history, not cleaned up
scripts/       # run_eval.py, generate_all.py, generator_probe.py, run_layer0_full.py,
               # run_layer0_step2_full.py, smoke_test_generator.py -- all real, runnable.
               # run_stability_check.py is still a stub, tracking layer5_statistics.py.
eval_runs/     # timestamped eval run outputs (gitignored) -- contains real runs already
```

## Known open decisions

- **Base generator**: decided and implemented — `generator/base_generator.py` wraps Gemini (`google-genai` SDK, `gemini-2.5-flash`) via `GEMINI_API_KEY`, prompt copied verbatim from Finvoice-AI's `aiController.js` (MIT license). Parsing is intentionally fragile (strips ```json fences, no try/except around `json.loads`) to measure the real parse-failure rate rather than mask it.
- **`notebooks/datasets_searching.ipynb`**: has an unresolved bug — assumes `priyank-m/SROIE_2019_text_recognition` has a `words` field, but it doesn't (`KeyError: 'words'`). Not fixed; kept as history. The actual dataset used everywhere else is the synthetic one in `data/synthetic/`, not SROIE.
- **LLM provider split**: generator uses Gemini (`GEMINI_API_KEY`); judges in `evals/judges/` use Anthropic/Claude (`ANTHROPIC_API_KEY`). Both keys live in `.env.example`.
- **Layer 3 merged into Layer 2**: `evals/layer2_document.py::by_group()` now covers the segment/doc-type breakdown the brief describes as a separate Layer 3. `evals/layer3_segment.py` was deleted. The brief itself (`.claude/.skills/project_brief.md`) has not been rewritten to match — treat Layer 2's docstring and `CHANGELOG.md` as the source of truth over the brief's Layer 3 section.
- **Uncommitted work / CHANGELOG lag**: significant changes get logged by hand in `CHANGELOG.md` rather than relying on git log — check it's current before assuming recent work is undocumented; if it lags behind the working tree, that's a known gap, not a signal the change didn't happen.

## Working in this repo

- Follow the module boundaries above: generator logic only in `generator/`, all metric/judge logic in `evals/`, nothing computed from scratch in `evals/business_layer.py` (Layer 6) — it must only read `metrics_dict` + `config/*.yaml`.
- `config/*.yaml` files are placeholders (`# ASSUMPTION — заполнить`) — fill with real values as part of implementing the layer that consumes them, not speculatively.
- When implementing a layer, replace its `NotImplementedError` and un-skip the corresponding test in `tests/`.
- When real project structure changes (new dependencies, new modules, architecture shifts), update this file to match.
