"""CLI entry point: run the full eval pipeline end-to-end.

Usage:
  python scripts/run_eval.py --from-probe                    # build metrics from already-collected
                                                               # generator_probe.py results, no new API calls
  python scripts/run_eval.py --from-probe --use-judge         # ...and score semantic fields too (needs ANTHROPIC_API_KEY)
  python scripts/run_eval.py --smoke                          # LIVE run: 3 records/segment, real Gemini calls
  python scripts/run_eval.py --n-per-segment 20                # LIVE run: stratified sample
  python scripts/run_eval.py                                   # LIVE run: full dataset (402 records)

--smoke/--n-per-segment/no-args all call the real generator (rate-limited,
paid, quota-constrained -- see evals/runner.run() docstring). --from-probe
makes zero network calls.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals.runner import run, run_from_probe_results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-probe", action="store_true", help="use existing eval_runs/*_generator_probe.json instead of calling the generator")
    parser.add_argument("--use-judge", action="store_true", help="with --from-probe: also call the Anthropic semantic judge (needs ANTHROPIC_API_KEY)")
    parser.add_argument("--smoke", action="store_true", help="live run: 3 records/segment, fast wiring check")
    parser.add_argument("--n-per-segment", type=int, default=None, help="live run: stratified sample size per segment")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if args.from_probe:
        metrics_dict = run_from_probe_results(use_semantic_judge=args.use_judge)
    else:
        metrics_dict = run(smoke=args.smoke, n_per_segment=args.n_per_segment, seed=args.seed)

    layer1 = metrics_dict["layer1"]
    print(f"\nrun_id: {metrics_dict['run_id']}")
    print(f"records run: {metrics_dict['config']['n_records_run']} / {metrics_dict['config']['n_records_total']}")
    print(f"parse failure rate: {layer1['parse_failure_rate']:.1%}")
    print("\nLayer 1 — error rate per field type:")
    for field, stats in layer1["field_scores"].items():
        print(f"  {field:20s} error_rate={stats['error_rate']:.1%}  mean_score={stats['mean_score']:.3f}  n={stats['n']}")


if __name__ == "__main__":
    main()
