"""Layer 4 — Production-simulation metrics.

JD metrics: latency, CSAT/thumbs-up-down proxy (explicitly a simulation,
not real user data — must be labeled as such wherever displayed), trend/
drift across batches.

Latency must be captured during the generator run (see generator/ and
scripts/run_eval.py), not recomputed here.

TODO: implement latency aggregation, reviewer-judge call (see
evals/judges/reviewer_judge.py), batch trend view.
"""


def latency_stats(latencies_ms: list[float]) -> dict[str, float]:
    raise NotImplementedError("TODO: p50/p95/mean latency")


def batch_trend(batches: list[dict]) -> dict:
    raise NotImplementedError("TODO: metric trend across synthetic batches")
