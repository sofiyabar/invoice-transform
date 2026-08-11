# About this project

This project is a demonstration of an evaluation system built around an AI model that extracts
structured invoice data from unstructured text.

## Goal

The goal is to demonstrate a complete evaluation loop around an AI model: measure its accuracy
layer by layer, identify and explain where and why it fails, translate those failures into
business cost, and use the results to drive concrete improvements to the model.

## Steps

1. An existing invoice-extraction model was taken from an existing open-source project on
   GitHub as the starting point.
2. A model of our own was added on top of it: a gate that determines whether a request is
   actually asking for an invoice, and whether the text contains enough information to build
   one, before extraction is attempted.
3. A test dataset was generated: 600 synthetic examples covering clean invoice requests, noisy
   and edge-case variants, requests unrelated to invoices, requests with missing data, and
   deliberately malformed or garbage text — each with a matching correct answer to measure
   against.
4. An evaluation system was built around the combined model, layer by layer: accuracy per
   field, readiness of the document as a whole, simulated behavior in production, and
   translation of accuracy into cost.
5. The first evaluation pass produced a full set of results. A dashboard was built after that
   to make those results readable at a glance, layer by layer, instead of read out of raw
   output files.

## Dashboard

The dashboard has one tab per evaluation layer: intent and data-sufficiency checks, field
accuracy, document readiness (with a breakdown by input complexity and document type),
production simulation, and business impact. It reads a single evaluation run and renders it
directly, with no numbers computed in the interface itself.

Run it locally:

```
streamlit run dashboard/app.py
```

## Results

Measured on the full dataset, latest run:

- Intent detection: 98.2% accuracy, 0% false positives — no irrelevant request ever produced a
  fabricated invoice — and a 2.4% false-negative rate.
- Data-sufficiency check: 97.7% accuracy.
- Document readiness: 87.7% of invoices are extracted fully correctly and ready to use without
  human review.
- Technical failure rate of the model call itself: about 1%.

## Principles

Every dollar figure traces back to a measured metric or a stated assumption. Where a real
measurement isn't yet available — for example, response latency — the number shown is labeled
as an estimate.

## Closing the loop

The evaluation results are the input for the next step: using them to propose changes to the
algorithm, adjust it, and measure how the metrics respond to the change. This is where the
evaluation loop closes — a measured weakness turns into a tested improvement, and the dashboard
shows the before-and-after directly.

## Where to go next

Evaluation layers are built and tested against the full dataset in the order described above.
Closing the loop through algorithm changes is the current focus. For the exact status of each
layer, the data schema, and the history of decisions, see:

- [`README.md`](README.md) — current status and project structure
- [`DATA_MAP.md`](DATA_MAP.md) — data files, fields, and how the dashboard reads them
- [`CHANGELOG.md`](CHANGELOG.md) — history of decisions and changes
- [`.claude/.skills/project_brief.md`](.claude/.skills/project_brief.md) — the original project brief
