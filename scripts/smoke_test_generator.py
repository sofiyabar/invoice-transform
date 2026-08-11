"""One-off smoke test for generator.base_generator — not part of the eval suite.

Runs a couple of examples from data/synthetic/eval_dataset.jsonl through the
real Gemini call and prints raw text / parsed dict / ground truth side by side,
so we can eyeball whether the API key + parsing actually work before wiring up
field-accuracy scoring.

Usage: python scripts/smoke_test_generator.py [n]
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from generator.base_generator import parse_invoice_from_text

DATASET_PATH = Path(__file__).resolve().parent.parent / "data" / "synthetic" / "eval_dataset.jsonl"


def main(n: int = 2) -> None:
    with open(DATASET_PATH, encoding="utf-8") as f:
        rows = [json.loads(line) for _, line in zip(range(n), f)]

    for row in rows:
        print("=" * 80)
        print(f"id: {row['id']}  segment: {row['segment']}  style: {row.get('style')}")
        print("-" * 80)
        print("RAW TEXT:")
        print(row["raw_text"])
        print("-" * 80)
        try:
            prediction = parse_invoice_from_text(row["raw_text"])
            print("PREDICTION (parsed):")
            print(json.dumps(prediction, indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"FAILED: {type(e).__name__}: {e}")
        print("-" * 80)
        print("GROUND TRUTH:")
        print(json.dumps(row["ground_truth"], indent=2, ensure_ascii=False))
        print()


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    main(n)
