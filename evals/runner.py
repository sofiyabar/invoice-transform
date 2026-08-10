"""Orchestrates a full eval run: generator -> Layer 1-5 -> saved metrics_dict.

metrics_dict is the single place all layers' output lives — one timestamped
JSON file per run in eval_runs/, nested by layer key. business_layer.py and
dashboard/app.py must only ever read this file, never recompute a metric.
Only layer1 is implemented so far; layer2-6 keys are present but null until
their modules are un-stubbed (see CLAUDE.md "Known open decisions").

Three entry points:
  run()                          -- calls the live generator (real,
                                     rate-limited Gemini calls, see
                                     call_generator() below).
  run_from_probe_results()       -- builds metrics_dict from already-collected
                                     scripts/generator_probe.py output, no new
                                     generator calls.
  run_from_generated_predictions() -- builds metrics_dict from
                                     scripts/generate_all.py's full-dataset
                                     output (data/synthetic/generator_predictions.jsonl,
                                     all 600 rows incl. non-invoice ones).
                                     Prefer this once that file exists -- it's
                                     the full run, not a partial probe.
"""

import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from data.loaders import load_synthetic_extraction
from data.schema import InvoiceFields, InvoiceRecord
from evals.layer1_field import aggregate_scores, score_fields
from evals.layer2_document import (
    CRITICAL_FIELDS,
    critical_error_rate,
    critical_fields_all_correct,
    load_field_weights,
    resolution_rate,
    weighted_document_score,
)
from generator.base_generator import normalize_prediction, parse_invoice_from_text

REPO_ROOT = Path(__file__).resolve().parent.parent
EVAL_RUNS_DIR = REPO_ROOT / "eval_runs"
GENERATED_PREDICTIONS_PATH = REPO_ROOT / "data" / "synthetic" / "generator_predictions.jsonl"

# Gemini free tier: 5 requests/min for gemini-2.5-flash.
MIN_CALL_INTERVAL = 13.0
MAX_RETRIES = 2


def call_generator(text: str, min_call_interval: float = MIN_CALL_INTERVAL) -> dict | None:
    """Rate-limited, retrying wrapper around the generator under test.
    Returns None (not an exception) on real parse/API failure, so a single
    bad record doesn't kill the whole run -- the failure itself is a Layer 1
    signal (parse failure rate), not a bug in the harness."""
    last_call_at = getattr(call_generator, "_last_call_at", 0.0)
    for attempt in range(MAX_RETRIES + 1):
        elapsed = time.monotonic() - last_call_at
        if elapsed < min_call_interval:
            time.sleep(min_call_interval - elapsed)
        last_call_at = time.monotonic()
        call_generator._last_call_at = last_call_at
        try:
            return parse_invoice_from_text(text)
        except Exception as e:
            is_rate_limit = "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e)
            if is_rate_limit and attempt < MAX_RETRIES:
                backoff = min_call_interval * (attempt + 2)
                print(f"    rate limited, backing off {backoff:.0f}s...", file=sys.stderr)
                time.sleep(backoff)
                continue
            print(f"    generator failed on this record: {type(e).__name__}: {e}", file=sys.stderr)
            return None


def _sample_stratified(records: list[InvoiceRecord], n_per_segment: int, seed: int) -> list[InvoiceRecord]:
    rng = random.Random(seed)
    by_segment: dict[str, list[InvoiceRecord]] = {}
    for r in records:
        by_segment.setdefault(r.segment.value, []).append(r)
    sample = []
    for segment, pool in by_segment.items():
        sample += rng.sample(pool, min(n_per_segment, len(pool)))
    return sample


def _score_record(record: InvoiceRecord) -> dict[str, Any]:
    prediction_raw = call_generator(record.raw_text)
    entry: dict[str, Any] = {
        "id": record.id,
        "segment": record.segment.value,
        "doc_type": record.doc_type.value,
        "parse_ok": prediction_raw is not None,
    }
    if prediction_raw is None:
        entry["scores"] = {}
        return entry
    try:
        pred_fields = InvoiceFields(**normalize_prediction(prediction_raw))
    except Exception as e:
        # generator returned valid JSON but not our shape -- also a real
        # failure mode, tracked separately from parse_ok=False (bad JSON)
        entry["parse_ok"] = False
        entry["schema_error"] = f"{type(e).__name__}: {e}"
        entry["scores"] = {}
        return entry
    entry["scores"] = score_fields(record.ground_truth, pred_fields)
    return entry


def _build_layer2(scored: list[dict[str, float]]) -> dict[str, Any]:
    """Layer 2 is pure re-aggregation of Layer 1's per-record scores -- no
    judge calls, nothing computed from scratch (CLAUDE.md module boundary)."""
    weights = load_field_weights()
    weighted_scores = [s for s in (weighted_document_score(r, weights) for r in scored) if s is not None]

    n_resolution_scored = sum(1 for r in scored if critical_fields_all_correct(r) is not None)
    try:
        res_rate = resolution_rate(scored)
        crit_err_rate = critical_error_rate(scored)
    except ValueError:
        res_rate = None
        crit_err_rate = None

    return {
        "resolution_rate": res_rate,
        "critical_error_rate": crit_err_rate,
        "n_resolution_scored": n_resolution_scored,
        "weighted_document_score": {
            "mean": sum(weighted_scores) / len(weighted_scores) if weighted_scores else None,
            "n": len(weighted_scores),
        },
        "field_weights": weights,
        "critical_fields": list(CRITICAL_FIELDS),
    }


def _write_metrics_dict(config: dict[str, Any], per_record: list[dict[str, Any]]) -> dict[str, Any]:
    """Shared assembly + write step for run() and run_from_probe_results() --
    metrics_dict is the one place all layers' output lives, so both entry
    points must produce the exact same shape."""
    scored = [r["scores"] for r in per_record if r["parse_ok"]]
    n_failed = sum(1 for r in per_record if not r["parse_ok"])

    metrics_dict: dict[str, Any] = {
        "run_id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "config": config,
        "layer0": None,
        "layer1": {
            "field_scores": aggregate_scores(scored),
            "parse_failure_rate": n_failed / len(per_record) if per_record else None,
            "n_parse_failures": n_failed,
            "records": per_record,
        },
        "layer2": _build_layer2(scored) if scored else None,
        "layer3": None,
        "layer4": None,
        "layer5": None,
        "layer6": None,
    }

    EVAL_RUNS_DIR.mkdir(exist_ok=True)
    out_path = EVAL_RUNS_DIR / f"{metrics_dict['run_id']}_metrics.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(metrics_dict, f, indent=2, ensure_ascii=False)
    print(f"metrics written to {out_path}", file=sys.stderr)

    return metrics_dict


def run(
    smoke: bool = False,
    n_per_segment: int | None = None,
    seed: int = 42,
) -> dict:
    """smoke=True is shorthand for n_per_segment=3 (fast wiring check).
    n_per_segment=None runs the full synthetic extraction dataset.

    Makes real, rate-limited Gemini calls -- one per record run. Do not call
    this against more than a handful of records without checking the day's
    remaining Gemini free-tier quota first (~20 requests/day, see
    CHANGELOG.md 2026-08-09 -- the quota is daily, not per-minute, and is
    easy to exhaust with a single unthrottled or even throttled bulk run)."""
    if smoke and n_per_segment is None:
        n_per_segment = 3

    all_records = load_synthetic_extraction()
    records = _sample_stratified(all_records, n_per_segment, seed) if n_per_segment else all_records

    per_record = []
    for i, record in enumerate(records, 1):
        print(f"... [{i}/{len(records)}] scoring {record.id} ({record.segment.value})", file=sys.stderr)
        per_record.append(_score_record(record))

    config = {
        "source": "live_generator_run",
        "n_records_total": len(all_records),
        "n_records_run": len(records),
        "sampled": n_per_segment is not None,
        "n_per_segment": n_per_segment,
        "seed": seed,
        "generator_model": "gemini-2.5-flash",
        "use_semantic_judge": True,
    }
    return _write_metrics_dict(config, per_record)


def run_from_probe_results(
    probe_paths: list[Path] | None = None,
    use_semantic_judge: bool = False,
) -> dict:
    """Build a Layer 1 metrics_dict from already-collected scripts/generator_probe.py
    output (eval_runs/*_generator_probe.json) instead of calling the generator
    again. Use this when the day's Gemini quota is spent, or to avoid burning
    more of it -- see CHANGELOG.md 2026-08-09.

    use_semantic_judge=False (default) skips Anthropic calls entirely: only
    email/numeric fields get scored, plus the trivial (both-missing /
    one-missing) cases for clientName/address/items.name. Non-trivial
    semantic comparisons are left out of field_scores rather than guessed --
    field_scores["clientName"]["n"] will be smaller than n_records_run, which
    is the honest signal that judge coverage is partial, not a bug.

    probe_paths defaults to every eval_runs/*_generator_probe.json found.
    """
    if probe_paths is None:
        probe_paths = sorted(EVAL_RUNS_DIR.glob("*_generator_probe.json"))
    if not probe_paths:
        raise FileNotFoundError(f"no *_generator_probe.json files found in {EVAL_RUNS_DIR}")

    doc_type_by_id = {r.id: r.doc_type.value for r in load_synthetic_extraction()}

    seen_ids: set[str] = set()
    per_record: list[dict[str, Any]] = []
    n_attempted = 0
    for path in probe_paths:
        with open(path, encoding="utf-8") as f:
            entries = json.load(f)
        for e in entries:
            if e.get("kind") != "invoice":
                continue
            n_attempted += 1
            if not e.get("ok"):
                continue
            if e["id"] in seen_ids:
                continue  # a record re-attempted across probe runs; keep the first success
            seen_ids.add(e["id"])

            try:
                gt_fields = InvoiceFields(**e["ground_truth"])
                pred_fields = InvoiceFields(**normalize_prediction(e["prediction"]))
            except Exception as ex:
                per_record.append(
                    {
                        "id": e["id"],
                        "segment": e.get("segment"),
                        "doc_type": doc_type_by_id.get(e["id"]),
                        "parse_ok": False,
                        "schema_error": f"{type(ex).__name__}: {ex}",
                        "scores": {},
                    }
                )
                continue

            per_record.append(
                {
                    "id": e["id"],
                    "segment": e.get("segment"),
                    "doc_type": doc_type_by_id.get(e["id"]),
                    "parse_ok": True,
                    "scores": score_fields(gt_fields, pred_fields, use_semantic_judge=use_semantic_judge),
                }
            )

    config = {
        "source": "generator_probe_results",
        "probe_files": [p.name for p in probe_paths],
        "probe_attempted": n_attempted,
        "probe_succeeded": len(per_record),
        "n_records_total": len(load_synthetic_extraction()),
        "n_records_run": len(per_record),
        "use_semantic_judge": use_semantic_judge,
        "generator_model": "gemini-2.5-flash",
        "note": (
            "Partial data from scripts/generator_probe.py, not a full eval run: "
            f"{n_attempted} generator calls attempted, {len(per_record)} succeeded "
            "before the Gemini free-tier daily quota (~20 req/day) was exhausted."
            + ("" if use_semantic_judge else " Semantic-match fields (clientName, "
               "address, items.name) scored only for trivial cases -- ANTHROPIC_API_KEY "
               "not configured, no judge calls were made.")
        ),
    }
    return _write_metrics_dict(config, per_record)


def run_from_generated_predictions(
    predictions_path: Path = GENERATED_PREDICTIONS_PATH,
    use_semantic_judge: bool = False,
) -> dict:
    """Build a Layer 1/2 metrics_dict from scripts/generate_all.py's
    full-dataset output (one line per row in data/synthetic/eval_dataset.jsonl,
    invoice and non-invoice alike -- {id, segment, ok, prediction} or
    {id, segment, ok: false, error}). Only the rows with ground_truth (the
    402-row extraction subset, see data/loaders.py::load_synthetic_extraction)
    are scoreable here; the rest belong to Layer 0.

    use_semantic_judge=False (default) skips Anthropic calls -- same partial-
    coverage honesty rule as run_from_probe_results(): non-trivial semantic
    comparisons are left out of field_scores rather than guessed.
    """
    if not predictions_path.exists():
        raise FileNotFoundError(
            f"{predictions_path} not found -- run scripts/generate_all.py first"
        )

    predictions_by_id: dict[str, dict] = {}
    with open(predictions_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                row = json.loads(line)
                predictions_by_id[row["id"]] = row

    extraction_records = load_synthetic_extraction()
    per_record: list[dict[str, Any]] = []
    n_missing = 0

    for record in extraction_records:
        pred_row = predictions_by_id.get(record.id)
        if pred_row is None:
            n_missing += 1
            per_record.append(
                {
                    "id": record.id,
                    "segment": record.segment.value,
                    "doc_type": record.doc_type.value,
                    "parse_ok": False,
                    "schema_error": "not present in generator_predictions.jsonl",
                    "scores": {},
                }
            )
            continue

        if not pred_row.get("ok"):
            per_record.append(
                {
                    "id": record.id,
                    "segment": record.segment.value,
                    "doc_type": record.doc_type.value,
                    "parse_ok": False,
                    "error": pred_row.get("error"),
                    "scores": {},
                }
            )
            continue

        try:
            pred_fields = InvoiceFields(**normalize_prediction(pred_row["prediction"]))
        except Exception as ex:
            per_record.append(
                {
                    "id": record.id,
                    "segment": record.segment.value,
                    "doc_type": record.doc_type.value,
                    "parse_ok": False,
                    "schema_error": f"{type(ex).__name__}: {ex}",
                    "scores": {},
                }
            )
            continue

        per_record.append(
            {
                "id": record.id,
                "segment": record.segment.value,
                "doc_type": record.doc_type.value,
                "parse_ok": True,
                "scores": score_fields(record.ground_truth, pred_fields, use_semantic_judge=use_semantic_judge),
            }
        )

    config = {
        "source": "generator_predictions_full",
        "predictions_file": predictions_path.name,
        "n_records_total": len(extraction_records),
        "n_records_run": len(per_record),
        "n_missing_from_predictions_file": n_missing,
        "use_semantic_judge": use_semantic_judge,
        "generator_model": "gemini-2.5-flash",
        "note": (
            None
            if use_semantic_judge
            else "Semantic-match fields (clientName, address, items.name) scored only for "
            "trivial cases -- ANTHROPIC_API_KEY not configured, no judge calls were made."
        ),
    }
    return _write_metrics_dict(config, per_record)
