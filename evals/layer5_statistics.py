"""Layer 5 — Statistical layer (cross-cutting, applies to Layers 1-4).

JD framing: "understanding what a noisy metric is".
- Bootstrap confidence intervals on resolution rate (small sample size).
- Judge stability: repeated judge runs on a fixed golden subset,
  variance / Cohen's kappa agreement.
- Statistical significance when comparing segments (e.g. clean vs noisy).

TODO: implement with scipy.stats.bootstrap and sklearn.metrics.cohen_kappa_score.
"""


def bootstrap_ci(values: list[float], n_resamples: int = 2000) -> tuple[float, float]:
    raise NotImplementedError("TODO: scipy.stats.bootstrap confidence interval")


def judge_stability(repeated_scores: list[list[float]]) -> dict[str, float]:
    raise NotImplementedError("TODO: variance + Cohen's kappa across repeated judge runs")


def segment_significance(segment_a_scores: list[float], segment_b_scores: list[float]) -> dict:
    raise NotImplementedError("TODO: significance test between two segments")
