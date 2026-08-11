"""Production Simulation (formerly "Layer 4") metrics.

JD metrics: latency, CSAT/thumbs-up-down proxy, trend/drift across batches.
Unlike the accuracy sections (field/document accuracy), this section
simulates what you'd watch AFTER deployment -- ops/monitoring signals, not
correctness. See conversation record ("О чем вообще этот слой?") for the
full framing.

Current state (see conversation record "давай так"):
  - latency: no run has ever captured real per-call timing (checked
    data/synthetic/generator_predictions.jsonl -- no timestamp field).
    latency_stats() is the real implementation, ready for when timed data
    exists; LATENCY_ESTIMATE_MS is an explicit, labeled guess (Gemini
    2.5 Flash typical response time for a short extraction prompt) used as
    a stand-in until then.
  - CSAT/thumbs-up-down proxy: the real version needs
    evals/judges/reviewer_judge.py (an LLM call, needs ANTHROPIC_API_KEY,
    not implemented). csat_proxy_stub() is an explicit placeholder:
    extrapolates a plausible thumbs-down rate from Document Accuracy's
    critical_error_rate plus an assumed "a second reviewer catches a bit
    more" delta -- NOT a judge call, NOT real user data.
  - trend/drift: deliberately not implemented -- there's only ever been one
    full run (one point in time). Slicing that single run into fake
    "batches" wouldn't show a real trend, just noise dressed up as one.
    Revisit once there's an actual second run to compare (e.g. after a
    prompt change).
"""

LATENCY_ESTIMATE_MS = {
    "p50": 1800.0,
    "p95": 3500.0,
    "mean": 2000.0,
}

CSAT_PROXY_PESSIMISM_DELTA = 0.05


def latency_stats(latencies_ms: list[float]) -> dict[str, float]:
    """Real implementation, for whenever a run captures actual per-call
    timing. Not called anywhere yet -- see module docstring."""
    if not latencies_ms:
        raise ValueError("no latencies to summarize")
    ordered = sorted(latencies_ms)
    n = len(ordered)
    p50 = ordered[int(0.50 * (n - 1))]
    p95 = ordered[int(0.95 * (n - 1))]
    return {"p50": p50, "p95": p95, "mean": sum(ordered) / n, "n": n}


def latency_estimate() -> dict[str, float]:
    """ASSUMPTION, not measured -- see LATENCY_ESTIMATE_MS in the module
    docstring for the reasoning."""
    return {**LATENCY_ESTIMATE_MS, "is_estimate": True}


def csat_proxy_stub(critical_error_rate: float, delta: float = CSAT_PROXY_PESSIMISM_DELTA) -> dict:
    """STUB, not a real judge call -- see evals/judges/reviewer_judge.py
    (unimplemented, needs ANTHROPIC_API_KEY). Extrapolates a plausible
    thumbs-down rate from Document Accuracy's critical_error_rate plus a small
    assumed pessimism delta: a second, independent reviewer likely also
    flags non-critical issues (phrasing, formatting) the critical-field
    check alone doesn't catch."""
    thumbs_down_rate = min(1.0, critical_error_rate + delta)
    return {
        "thumbs_down_rate": thumbs_down_rate,
        "thumbs_up_rate": 1.0 - thumbs_down_rate,
        "is_stub": True,
        "stub_basis": "critical_error_rate",
        "pessimism_delta": delta,
    }


def batch_trend(batches: list[dict]) -> dict:
    raise NotImplementedError(
        "Deliberately unimplemented -- see module docstring: no second real "
        "run exists yet to compare against, so there's nothing true to trend."
    )
