"""Layer 6 — Business Impact (derived layer).

Reads ONLY the metrics_dict produced by Layers 1-5 plus config/*.yaml
assumptions — must not compute any eval metric from scratch. Every $
figure must be traceable to a specific metrics_dict key or config value
(see tests/test_business_layer.py for the traceability check).

Formulas (fixed, from project brief):
- cost_of_manual_review = (1 - resolution_rate) * volume * avg_review_min * hourly_rate
- expected_cost_of_critical_errors = sum(critical_error_rate_by_field * field_severity_$) * volume
- segment_risk_exposure = sum_segment(volume_share * critical_error_rate_segment * avg_error_cost)
- infra_sla_cost = latency_p95 * compute_cost_per_sec * volume + sla_penalty
- churn_risk_proxy = f(thumbs_down_rate)
- net_value = savings_from_automation - cost_of_manual_review - expected_cost_of_critical_errors - infra_sla_cost

TODO: implement each formula as a pure function of metrics_dict + config.
"""

from typing import Any


def compute_business_impact(metrics_dict: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    raise NotImplementedError("TODO: aggregate Layer 1-5 outputs into business_dict, no new computation")
