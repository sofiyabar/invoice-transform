"""CLI entry point: run the full eval pipeline end-to-end.

Usage:
  python scripts/run_eval.py --from-generated      # build metrics from data/synthetic/generator_predictions.jsonl
                                                     # (scripts/generate_all.py's full-dataset output), no new API calls
  python scripts/run_eval.py --from-probe          # build metrics from eval_runs/*_generator_probe.json, no new API calls
  python scripts/run_eval.py --smoke               # LIVE run: 3 records/segment, real Gemini calls
  python scripts/run_eval.py --n-per-segment 20     # LIVE run: stratified sample
  python scripts/run_eval.py                        # LIVE run: full dataset (402 records)

--smoke/--n-per-segment/no-args all call the real generator (rate-limited,
paid, quota-constrained -- see evals/runner.run() docstring). --from-probe
and --from-generated make zero network calls.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals.runner import run, run_from_generated_predictions, run_from_probe_results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-generated", action="store_true", help="use data/synthetic/generator_predictions.jsonl (scripts/generate_all.py output)")
    parser.add_argument("--from-probe", action="store_true", help="use existing eval_runs/*_generator_probe.json instead of calling the generator")
    parser.add_argument("--smoke", action="store_true", help="live run: 3 records/segment, fast wiring check")
    parser.add_argument("--n-per-segment", type=int, default=None, help="live run: stratified sample size per segment")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if args.from_generated:
        metrics_dict = run_from_generated_predictions()
    elif args.from_probe:
        metrics_dict = run_from_probe_results()
    else:
        metrics_dict = run(smoke=args.smoke, n_per_segment=args.n_per_segment, seed=args.seed)

    field_accuracy = metrics_dict["field_accuracy"]
    print(f"\nrun_id: {metrics_dict['run_id']}")
    print(f"records run: {metrics_dict['config']['n_records_run']} / {metrics_dict['config']['n_records_total']}")
    print(f"parse failure rate: {field_accuracy['parse_failure_rate']:.1%}")
    print("\nField Accuracy — error rate per field type:")
    for field, stats in field_accuracy["field_scores"].items():
        print(f"  {field:20s} error_rate={stats['error_rate']:.1%}  mean_score={stats['mean_score']:.3f}  n={stats['n']}")


if __name__ == "__main__":
    main()
