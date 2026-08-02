# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project intent

This repository is for building an **evals system for AI-generated invoices** — i.e., evaluating how well an AI model can produce/transform invoice data (e.g., extracting or generating structured invoice fields such as company, date, address, and total) against ground truth.

## Current state

The project is in an early, exploratory stage. There is no build system, dependency manifest, test suite, or source code structure yet — only a single Jupyter notebook (`Untitled.ipynb`) used for prototyping.

The notebook currently:
- Installs the Hugging Face `datasets` library.
- Loads the `priyank-m/SROIE_2019_text_recognition` dataset (SROIE 2019 receipt OCR dataset) as a reference/eval data source.
- Extracts raw OCR text (concatenated words) as model input and a ground-truth dict (`company`, `date`, `address`, `total`) as the expected output — this shape (raw text in, structured JSON out) is likely the eval format the project will build around.

## Working in this repo

Since there is no established structure yet:
- Don't assume conventions, build tooling, or file layout — check what actually exists before relying on prior context.
- When real project structure (dependencies, source files, eval harness) is added, this file should be updated to document actual commands (install/run/test) and architecture.
