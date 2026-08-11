"""Full Intake Gate, Step 1 run: classify every row of eval_dataset.jsonl
with generator.intent_gate.is_invoice_request, score each against ground
truth (evals.intake_intent_gate), and save both per-record results and the
aggregate accuracy/FP-rate/FN-rate.

Usage: python scripts/run_intake_intent_full.py [--out PATH] [--workers 10]
"""

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.loaders import load_intent_gate_dataset
from evals.intake_intent_gate import aggregate_intent_scores, score_intent
from generator.intent_gate import is_invoice_request

ROOT = Path(__file__).resolve().parent.parent
EVAL_RUNS_DIR = ROOT / "eval_runs"


def classify_one(record) -> dict:
    entry = {"id": record.id, "ground_truth": record.is_invoice_request}
    try:
        prediction = is_invoice_request(record.raw_text)
        entry.update(score_intent(record.is_invoice_request, prediction))
        entry["ok"] = True
    except Exception as e:
        entry["ok"] = False
        entry["error"] = f"{type(e).__name__}: {e}"
    return entry


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args()

    records = load_intent_gate_dataset()
    total = len(records)

    per_record: list[dict] = []
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(classify_one, r): r.id for r in records}
        for future in as_completed(futures):
            per_record.append(future.result())
            done += 1
            if done % 50 == 0 or done == total:
                print(f"{done}/{total} done", file=sys.stderr)

    n_failed = sum(1 for r in per_record if not r["ok"])
    scored = [r for r in per_record if r["ok"]]
    aggregate = aggregate_intent_scores(scored)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = args.out or (EVAL_RUNS_DIR / f"{run_id}_intake_intent_gate.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    result = {
        "run_id": run_id,
        "n_records": total,
        "n_classification_failures": n_failed,
        "aggregate": aggregate,
        "per_record": per_record,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\nclassification failures: {n_failed}/{total}")
    print("aggregate:", json.dumps(aggregate, indent=2))
    print(f"\nfull results written to {out_path}")


if __name__ == "__main__":
    main()
