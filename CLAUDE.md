# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project intent

This repository is for building an **evals system for AI-generated invoices** — i.e., evaluating how well an AI model can produce/transform invoice data (e.g., extracting or generating structured invoice fields such as client, address, and line items) against ground truth.

It is a portfolio project built for a specific job application (Finom, Product Data Scientist — AI Evaluation & Quality). The full brief — 6-layer metric hierarchy, business-impact formulas, dataset priorities, non-negotiable requirements — lives in `.claude/.skills/project_brief.md`. Read it before making architectural decisions; the brief still numbers the hierarchy "Layer 0" through "Layer 6" and describes Layer 3 as a standalone layer. The implementation has since (a) merged Layer 3 into Layer 2 and (b) renamed every layer from a number to what it does (see the mapping below) — the brief hasn't been rewritten to match either change, only annotated. When reading the brief, translate its "Layer N" language using this table:

| Brief's name | Current name | Current `metrics_dict` key |
|---|---|---|
| Layer 0 | Intake Gate | `intake` |
| Layer 1 | Field Accuracy | `field_accuracy` |
| Layer 2 (+ Layer 3, merged in) | Document Accuracy | `document_accuracy` |
| Layer 4 | Production Simulation | `production_simulation` |
| Layer 5 | *(deleted — see "Known open decisions")* | — |
| Layer 6 | Business Impact | `business_impact` |

## Current state

Intake, Field Accuracy, Document Accuracy and the generator are implemented and tested. Production Simulation is partially implemented with explicitly labeled stubs/assumptions. Business Impact is implemented (interactive P&L dashboard). The former Layer 5 (statistics) was implemented and then deleted (see "Known open decisions"). `pytest` — 68 passed, 1 skipped (`tests/test_generator.py`, waiting on a generator output-shape decision).

**Before tracing how data flows between files, read `DATA_MAP.md` first** — it has the full pipeline diagram, the file-by-file "what lives where" table, and the complete `metrics_dict` schema (keys/types/producer for every section's output). Don't re-derive that from `evals/runner.py` by hand; `DATA_MAP.md` is kept in sync with it.

```
generator/                  # the invoice generator under evaluation (raw text -> invoice JSON)
  base_generator.py          # Gemini-based extraction, prompt copied from Finvoice-AI aiController.js
  intent_gate.py              # Intake Step 1: is-invoice-intent classifier
  completeness_gate.py        # Intake Step 2: data sufficiency check (deterministic logic)
  pipeline.py                  # wires intent gate -> completeness gate -> base_generator into one call
evals/                      # eval hierarchy + LLM judges
  intake_intent_gate.py         # scoring for generator/intent_gate.py (FP/FN rates kept separate)
  intake_completeness_gate.py   # scoring for generator/completeness_gate.py
  field_accuracy.py             # field-level: exact / numeric-tolerance / judge-free fuzzy text match
  document_accuracy.py          # document-level (resolution rate, critical error rate) +
                                  # by_group() -- former Layer 3 segment-level breakdown, merged in here
  production_simulation.py      # latency (estimate, not yet measured), CSAT proxy (stub), batch trend (TODO)
  business_impact.py            # interactive P&L / unit economics, reads metrics_dict + config/*.yaml only
  judges/                       # DeepEval GEval-based judges (field_judge.py implemented, optional
                                  # re-score path; reviewer_judge.py TODO, needed for real CSAT)
  runner.py                     # orchestrates a run, writes eval_runs/*.json
data/          # schema.py (shared contract), loaders.py (reads data/synthetic/eval_dataset.jsonl),
               # synth_generate.py / segment_labeler.py (TODO stubs -- dataset was generated via the
               # .claude/.skills/*.md process instead, not through these)
               # data/synthetic/ has the real dataset + dataset_manifest.md + generation_notes.md
dashboard/     # Streamlit app. app.py renders all 5 sections (Intake, Field Accuracy, Document
               # Accuracy, Production Simulation, Business Impact) for real from eval_runs/*.json;
               # Business Impact additionally recomputes live from sidebar what-if inputs.
config/        # explicit "expert assumption" YAML files. business_assumptions.yaml and
               # severity_weights.yaml are filled with confirmed portfolio-illustrative values
               # (needed for Business Impact); a few SLA/compute fields are still 0 (unimplemented
               # infra_sla_cost). field_weights.yaml is deprecated/unused (see its own header comment).
tests/         # one file per module; test_generator.py still skipped (waiting on generator
               # output-shape decisions). No dedicated tests yet for runner.py, dashboard/app.py,
               # loaders.py, field_judge.py, or the scripts/ entry points.
notebooks/     # datasets_searching.ipynb -- exploratory history, not cleaned up
scripts/       # run_eval.py, generate_all.py, generator_probe.py, run_intake_intent_full.py,
               # run_intake_completeness_full.py, smoke_test_generator.py -- all real, runnable.
eval_runs/     # timestamped eval run outputs (gitignored) -- contains real runs already
```

## Known open decisions

- **Base generator**: decided and implemented — `generator/base_generator.py` wraps Gemini (`google-genai` SDK, `gemini-2.5-flash`) via `GEMINI_API_KEY`, prompt copied verbatim from Finvoice-AI's `aiController.js` (MIT license). Parsing is intentionally fragile (strips ```json fences, no try/except around `json.loads`) to measure the real parse-failure rate rather than mask it.
- **`notebooks/datasets_searching.ipynb`**: has an unresolved bug — assumes `priyank-m/SROIE_2019_text_recognition` has a `words` field, but it doesn't (`KeyError: 'words'`). Not fixed; kept as history. The actual dataset used everywhere else is the synthetic one in `data/synthetic/`, not SROIE.
- **LLM provider split**: generator uses Gemini (`GEMINI_API_KEY`); judges in `evals/judges/` use Anthropic/Claude (`ANTHROPIC_API_KEY`). Both keys live in `.env.example`.
- **Layer 3 merged into Document Accuracy**: `evals/document_accuracy.py::by_group()` now covers the segment/doc-type breakdown the brief describes as a separate Layer 3. `evals/layer3_segment.py` was deleted. The brief itself (`.claude/.skills/project_brief.md`) has not been rewritten to match — treat Document Accuracy's docstring and `CHANGELOG.md` as the source of truth over the brief's Layer 3 section.
- **Layer 5 (statistics) deleted**: implemented (bootstrap CI on resolution_rate, segment significance vs. baseline) then removed outright — `evals/layer5_statistics.py`, `tests/test_layer5_statistics.py`, `scripts/run_stability_check.py` no longer exist. The significance test didn't answer a real question this project has (97%/76% of noisy/edge records are already caught by Intake's completeness gate before reaching full extraction) and there was never a real stochastic judge to test stability of. `metrics_dict` has no key for it at all now (not even `null`).
- **Layers renamed from numbers to names**: every "Layer N" reference — dashboard tabs, `metrics_dict` keys, module filenames, function/variable names, docs — was renamed to what it does (see the mapping table above). `CHANGELOG.md` and `.claude/.skills/*.md` were deliberately left unchanged (historical records using the terminology that existed when they were written); only current-state docs (this file, `DATA_MAP.md`, `README.md`) and the code itself were renamed.
- **Uncommitted work / CHANGELOG lag**: significant changes get logged by hand in `CHANGELOG.md` rather than relying on git log — check it's current before assuming recent work is undocumented; if it lags behind the working tree, that's a known gap, not a signal the change didn't happen.

## Working in this repo

- Follow the module boundaries above: generator logic only in `generator/`, all metric/judge logic in `evals/`, nothing computed from scratch in `evals/business_impact.py` — it must only read `metrics_dict` + `config/*.yaml`.
- `config/*.yaml` files hold confirmed portfolio-illustrative values where filled in, and `# ASSUMPTION — заполнить`-style placeholders where a section still needs real inputs — fill with real values as part of implementing the section that consumes them, not speculatively.
- When implementing a section, replace its `NotImplementedError` and un-skip the corresponding test in `tests/`.
- When real project structure changes (new dependencies, new modules, architecture shifts), update this file to match.
