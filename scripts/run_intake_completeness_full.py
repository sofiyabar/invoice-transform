"""Full Intake Gate, Step 2 run: score generator.completeness_gate's
sufficiency decision against ground truth, using the generator predictions
already collected by scripts/generate_all.py (no new LLM calls --
completeness_gate.py is pure code, and reuses the same extraction field
accuracy would use, per the design in CHANGELOG.md 2026-08-10).

Rows are filtered by the MODEL's own Step 1 decision (from a
run_intake_intent_full.py results file), not by ground-truth
is_invoice_request -- in production, Step 2 only ever runs on what Step 1
actually let through. Scoring against ground-truth-positive rows would
silently include the ones Step 1 correctly/incorrectly said "no" to and
would never reach Step 2 for real. See CHANGELOG.md 2026-08-10.

Usage: python scripts/run_intake_completeness_full.py [--predictions PATH] [--intent-results PATH] [--out PATH]
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.loaders import load_sufficiency_gate_dataset
from data.schema import InvoiceFields
from evals.intake_completeness_gate import (
    aggregate_missing_fields_scores,
    aggregate_sufficiency_scores,
    score_missing_fields,
    score_sufficiency,
)
from generator.base_generator import normalize_prediction
from generator.completeness_gate import check_sufficiency, missing_critical_fields

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PREDICTIONS = ROOT / "data" / "synthetic" / "generator_predictions.jsonl"
EVAL_RUNS_DIR = ROOT / "eval_runs"


def load_predictions(path: Path) -> dict[str, dict]:
    preds = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            preds[row["id"]] = row
    return preds


def latest_intent_results() -> Path:
    matches = sorted(EVAL_RUNS_DIR.glob("*_intake_intent_gate.json"))
    if not matches:
        raise FileNotFoundError("no *_intake_intent_gate.json found in eval_runs/ -- run scripts/run_intake_intent_full.py first")
    return matches[-1]


def model_predicted_invoice_ids(path: Path) -> set[str]:
    """IDs the MODEL (not ground truth) classified as an invoice request in a
    run_intake_intent_full.py run -- these are the only ids Step 2 would
    ever see in production."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {r["id"] for r in data["per_record"] if r.get("ok") and r["prediction"] is True}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--intent-results", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    intent_results_path = args.intent_results or latest_intent_results()
    model_invoice_ids = model_predicted_invoice_ids(intent_results_path)

    all_records = load_sufficiency_gate_dataset()
    records = [r for r in all_records if r.id in model_invoice_ids]
    n_excluded_by_step1 = len(all_records) - len(records)

    predictions = load_predictions(args.predictions)

    per_record = []
    n_no_prediction = 0
    for record in records:
        pred_entry = predictions.get(record.id)
        if pred_entry is None or not pred_entry.get("ok"):
            n_no_prediction += 1
            continue

        try:
            pred_fields = InvoiceFields(**normalize_prediction(pred_entry["prediction"]))
        except Exception as e:
            per_record.append({"id": record.id, "ok": False, "error": f"{type(e).__name__}: {e}"})
            n_no_prediction += 1
            continue

        predicted_label = check_sufficiency(pred_fields)
        predicted_missing = missing_critical_fields(pred_fields)
        ground_truth_missing = set(record.missing_critical_fields)

        entry = {
            "id": record.id,
            "ok": True,
            **score_sufficiency(record.sufficiency_label, predicted_label),
            "missing_fields": score_missing_fields(ground_truth_missing, predicted_missing),
        }
        per_record.append(entry)

    scored = [r for r in per_record if r["ok"]]
    aggregate_sufficiency = aggregate_sufficiency_scores(scored)
    aggregate_missing_fields = aggregate_missing_fields_scores([r["missing_fields"] for r in scored])

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = args.out or (EVAL_RUNS_DIR / f"{run_id}_intake_completeness_gate.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    result = {
        "run_id": run_id,
        "intent_results_source": intent_results_path.name,
        "n_records_total": len(all_records),
        "n_excluded_by_step1": n_excluded_by_step1,
        "n_records": len(records),
        "n_no_prediction": n_no_prediction,
        "n_scored": len(scored),
        "aggregate_sufficiency": aggregate_sufficiency,
        "aggregate_missing_fields": aggregate_missing_fields,
        "per_record": per_record,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"excluded {n_excluded_by_step1}/{len(all_records)} -- Step 1 model said 'not an invoice'")
    print(f"scored {len(scored)}/{len(records)} ({n_no_prediction} skipped -- no usable prediction)")
    print("\naggregate_sufficiency:", json.dumps(aggregate_sufficiency, indent=2))
    print("\naggregate_missing_fields:", json.dumps(aggregate_missing_fields, indent=2))
    print(f"\nfull results written to {out_path}")


if __name__ == "__main__":
    main()
