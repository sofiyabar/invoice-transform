"""Bulk-generate predictions for every row in data/synthetic/eval_dataset.jsonl,
as the generator currently stands — no scoring/comparison here, that's a
separate branch's job. Just runs generator.base_generator.parse_invoice_from_text
over every row (invoice and non-invoice/OOS alike) and saves the raw result (or
the error, if it failed) so downstream eval work has predictions to consume.

Output: one JSON object per line — {id, segment, ok, prediction} or
{id, segment, ok: false, error}. Order is not guaranteed to match input order
(results are written as they complete).

Usage: python scripts/generate_all.py [--out PATH] [--workers 10]
"""

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from generator.base_generator import parse_invoice_from_text

ROOT = Path(__file__).resolve().parent.parent
DATASET_PATH = ROOT / "data" / "synthetic" / "eval_dataset.jsonl"
DEFAULT_OUT = ROOT / "data" / "synthetic" / "generator_predictions.jsonl"


def load_rows() -> list[dict]:
    rows = []
    with open(DATASET_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def generate_one(row: dict) -> dict:
    result = {"id": row["id"], "segment": row.get("segment")}
    try:
        result["prediction"] = parse_invoice_from_text(row["raw_text"])
        result["ok"] = True
    except Exception as e:
        result["ok"] = False
        result["error"] = f"{type(e).__name__}: {e}"
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args()

    rows = load_rows()
    total = len(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)

    done = 0
    failed = 0
    with open(args.out, "w", encoding="utf-8") as f, ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(generate_one, row): row["id"] for row in rows}
        for future in as_completed(futures):
            result = future.result()
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
            f.flush()
            done += 1
            if not result["ok"]:
                failed += 1
            if done % 25 == 0 or done == total:
                print(f"{done}/{total} done ({failed} failed so far)", file=sys.stderr)

    print(f"\nWrote {done} predictions ({failed} failed) to {args.out}")


if __name__ == "__main__":
    main()
