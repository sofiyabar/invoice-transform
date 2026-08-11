"""Ad hoc diagnostic run of generator.base_generator over a stratified sample of
data/synthetic/eval_dataset.jsonl — NOT part of the eval suite (real, paid,
non-deterministic Gemini calls). Goal: measure real parse failure rate and spot
format-only mismatches (e.g. "" vs null, int vs float) before they get treated
as real extraction errors in evals/field_accuracy.py.

eval_dataset.jsonl mixes two record shapes:
  - invoice rows: segment in {clean, noisy, edge}, ground_truth populated.
  - non-invoice / out-of-scope rows: ground_truth is null, is_invoice_request
    is false, segment is null or absent. There's no refusal path in the
    generator today, so we just record what it does with these.

Usage: python scripts/generator_probe.py [--n-per-segment 8] [--n-oos 6] [--seed 42]
"""

import argparse
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from generator.base_generator import parse_invoice_from_text

ROOT = Path(__file__).resolve().parent.parent
DATASET_PATH = ROOT / "data" / "synthetic" / "eval_dataset.jsonl"
EVAL_RUNS_DIR = ROOT / "eval_runs"

INVOICE_SEGMENTS = ("clean", "noisy", "edge")

# Billing is enabled on this key now (paid tier: 1000 req/min) — a light pace
# is still polite/defensive, but we don't need the free-tier 13s spacing
# anymore. Retry-on-429 stays as a safety net in case limits change again.
MIN_CALL_INTERVAL = 0.5
MAX_RETRIES = 2
_last_call_at = 0.0


def call_generator(text: str) -> dict:
    global _last_call_at
    for attempt in range(MAX_RETRIES + 1):
        elapsed = time.monotonic() - _last_call_at
        if elapsed < MIN_CALL_INTERVAL:
            time.sleep(MIN_CALL_INTERVAL - elapsed)
        _last_call_at = time.monotonic()
        try:
            return parse_invoice_from_text(text)
        except Exception as e:
            is_rate_limit = "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e)
            if is_rate_limit and attempt < MAX_RETRIES:
                backoff = MIN_CALL_INTERVAL * (attempt + 2)
                print(f"    rate limited, backing off {backoff:.0f}s...", file=sys.stderr)
                time.sleep(backoff)
                continue
            raise

# fields we diff at top level; "items" gets special handling below
SCALAR_FIELDS = ("clientName", "email", "address")


def load_rows() -> list[dict]:
    rows = []
    with open(DATASET_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def bucket_rows(rows: list[dict]) -> tuple[dict[str, list[dict]], list[dict]]:
    """Split into {segment: [invoice rows]} and [oos rows]."""
    by_segment: dict[str, list[dict]] = {s: [] for s in INVOICE_SEGMENTS}
    oos = []
    for row in rows:
        if row.get("ground_truth") is None:
            oos.append(row)
        elif row.get("segment") in by_segment:
            by_segment[row["segment"]].append(row)
        # rows with ground_truth set but unrecognized segment: skip silently,
        # shouldn't happen given the dataset audit, but don't want to crash the probe
    return by_segment, oos


def normalize_scalar(v):
    """Collapse "missing" representations so "" and null compare equal."""
    if v is None:
        return None
    if isinstance(v, str) and v.strip() == "":
        return None
    return v


def classify_scalar(truth, pred) -> str:
    t_norm, p_norm = normalize_scalar(truth), normalize_scalar(pred)
    if isinstance(t_norm, (int, float)) and isinstance(p_norm, (int, float)):
        t_norm, p_norm = float(t_norm), float(p_norm)
    if t_norm == p_norm:
        return "match" if truth == pred else "format_only_diff"
    return "real_mismatch"


def compare_fields(ground_truth: dict, prediction: dict) -> dict[str, str]:
    result = {}
    for field in SCALAR_FIELDS:
        result[field] = classify_scalar(ground_truth.get(field), prediction.get(field))

    truth_items = ground_truth.get("items") or []
    pred_items = prediction.get("items") if isinstance(prediction.get("items"), list) else []
    if len(truth_items) != len(pred_items):
        result["items.length"] = "real_mismatch"
    else:
        result["items.length"] = "match"
    for sub_field in ("name", "quantity", "unitPrice"):
        classes = [
            classify_scalar(t.get(sub_field), p.get(sub_field))
            for t, p in zip(truth_items, pred_items)
        ]
        if not classes:
            result[f"items.{sub_field}"] = "n/a"
        elif "real_mismatch" in classes:
            result[f"items.{sub_field}"] = "real_mismatch"
        elif "format_only_diff" in classes:
            result[f"items.{sub_field}"] = "format_only_diff"
        else:
            result[f"items.{sub_field}"] = "match"
    return result


def run_invoice_row(row: dict) -> dict:
    entry = {"id": row["id"], "segment": row["segment"], "kind": "invoice"}
    try:
        prediction = call_generator(row["raw_text"])
        entry["ok"] = True
        entry["prediction"] = prediction
        entry["ground_truth"] = row["ground_truth"]
        entry["field_comparison"] = compare_fields(row["ground_truth"], prediction)
    except Exception as e:
        entry["ok"] = False
        entry["error"] = f"{type(e).__name__}: {e}"
    return entry


def run_oos_row(row: dict) -> dict:
    entry = {"id": row["id"], "segment": row.get("segment"), "kind": "oos"}
    try:
        prediction = call_generator(row["raw_text"])
        entry["ok"] = True
        entry["prediction"] = prediction
    except Exception as e:
        entry["ok"] = False
        entry["error"] = f"{type(e).__name__}: {e}"
    return entry


def print_summary(results: list[dict]) -> None:
    invoice_results = [r for r in results if r["kind"] == "invoice"]
    oos_results = [r for r in results if r["kind"] == "oos"]

    print("=" * 80)
    print("PARSE FAILURE RATE — invoice rows")
    print("=" * 80)
    total = len(invoice_results)
    failed = [r for r in invoice_results if not r["ok"]]
    print(f"overall: {len(failed)}/{total} failed ({len(failed) / total:.0%})" if total else "no invoice rows sampled")
    for segment in INVOICE_SEGMENTS:
        seg_rows = [r for r in invoice_results if r["segment"] == segment]
        seg_failed = [r for r in seg_rows if not r["ok"]]
        if seg_rows:
            print(f"  {segment}: {len(seg_failed)}/{len(seg_rows)} failed ({len(seg_failed) / len(seg_rows):.0%})")
    if failed:
        print("failed ids:", ", ".join(r["id"] for r in failed))

    print()
    print("=" * 80)
    print("FIELD-LEVEL COMPARISON — invoice rows that parsed successfully")
    print("=" * 80)
    ok_rows = [r for r in invoice_results if r["ok"]]
    field_names = ["clientName", "email", "address", "items.length", "items.name", "items.quantity", "items.unitPrice"]
    for field in field_names:
        classes = [r["field_comparison"][field] for r in ok_rows if field in r["field_comparison"]]
        classes = [c for c in classes if c != "n/a"]
        if not classes:
            continue
        counts = {c: classes.count(c) for c in ("match", "format_only_diff", "real_mismatch")}
        print(f"  {field:20s} match={counts['match']:3d}  format_only_diff={counts['format_only_diff']:3d}  real_mismatch={counts['real_mismatch']:3d}")

    print()
    print("=" * 80)
    print("OUT-OF-SCOPE / NON-INVOICE ROWS — current generator has no refusal path")
    print("=" * 80)
    for r in oos_results:
        if r["ok"]:
            print(f"  {r['id']}: returned {json.dumps(r['prediction'], ensure_ascii=False)}")
        else:
            print(f"  {r['id']}: FAILED — {r['error']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-per-segment", type=int, default=8)
    parser.add_argument("--n-oos", type=int, default=6)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    by_segment, oos = bucket_rows(load_rows())

    sample_rows = []
    for segment in INVOICE_SEGMENTS:
        pool = by_segment[segment]
        sample_rows += rng.sample(pool, min(args.n_per_segment, len(pool)))
    oos_sample = rng.sample(oos, min(args.n_oos, len(oos)))

    results = []
    for row in sample_rows:
        print(f"... running {row['id']} ({row['segment']})", file=sys.stderr)
        results.append(run_invoice_row(row))
    for row in oos_sample:
        print(f"... running {row['id']} (oos)", file=sys.stderr)
        results.append(run_oos_row(row))

    print_summary(results)

    EVAL_RUNS_DIR.mkdir(exist_ok=True)
    out_path = EVAL_RUNS_DIR / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_generator_probe.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nraw results saved to {out_path}")


if __name__ == "__main__":
    main()
