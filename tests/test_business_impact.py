"""Traceability test: every $ figure in business_dict must trace back to a
metrics_dict key or a config/param value — never a hardcoded number. Keep
this test even under time pressure (see project brief, non-negotiable)."""

import evals.business_impact as business_impact
from evals.business_impact import compute_business_impact, default_params

PARAMS = {
    "retention_value_per_invoice": 0.50,
    "operator_hourly_rate": 25.0,
    "ai_inference_cost_per_invoice": 0.02,
    "monthly_volume": 10000,
    "avg_review_min": 3.0,
}
SEVERITY = {"clientName": 50, "email": 5, "address": 5, "items": 75}

METRICS_DICT = {
    "field_accuracy": {
        "field_scores": {
            "email": {"error_rate": 0.1, "mean_score": 0.9, "n": 100},
            "clientName": {"error_rate": 0.05, "mean_score": 0.95, "n": 100},
            "address": {"error_rate": 0.2, "mean_score": 0.8, "n": 80},
            "items.name": {"error_rate": 0.1, "mean_score": 0.9, "n": 90},
            "items.quantity": {"error_rate": 0.05, "mean_score": 0.95, "n": 90},
            "items.unitPrice": {"error_rate": 0.05, "mean_score": 0.95, "n": 90},
            "items.count": {"error_rate": 0.1, "mean_score": 0.9, "n": 90},
        },
    },
    "document_accuracy": {"resolution_rate": 0.877, "critical_error_rate": 0.123, "n_resolution_scored": 398},
}


def test_every_dollar_figure_traces_to_metrics_dict_or_config():
    result = compute_business_impact(METRICS_DICT, PARAMS, SEVERITY)

    for key in ("gross_ltv_value", "ai_run_cost", "manual_review_opex"):
        item = result[key]
        assert item["value_usd"] is not None, key
        for input_name, meta in item["inputs"].items():
            assert "source" in meta and ("metrics_dict." in meta["source"] or "config." in meta["source"] or "sidebar" in meta["source"])

    qrc = result["quality_risk_cost"]
    assert qrc["value_usd"] is not None
    for field, meta in qrc["by_field"].items():
        assert "metrics_dict." in meta["error_rate_source"]
        assert "config." in meta["severity_source"]

    assert result["net_ai_profit"]["value_usd"] is not None

    for key in ("infra_sla_cost", "churn_risk_proxy", "segment_risk_exposure"):
        assert result[key]["value_usd"] is None
        assert "reason" in result[key]


def test_net_ai_profit_formula():
    result = compute_business_impact(METRICS_DICT, PARAMS, SEVERITY)
    expected = (
        result["gross_ltv_value"]["value_usd"]
        - result["ai_run_cost"]["value_usd"]
        - result["manual_review_opex"]["value_usd"]
        - result["quality_risk_cost"]["value_usd"]
    )
    assert result["net_ai_profit"]["value_usd"] == round(expected, 2)


def test_ai_run_cost_is_pure_volume_times_unit_cost():
    result = compute_business_impact(METRICS_DICT, PARAMS, SEVERITY)
    assert result["ai_run_cost"]["value_usd"] == 10000 * 0.02


def test_quality_risk_cost_uses_items_weighted_average():
    result = compute_business_impact(METRICS_DICT, PARAMS, SEVERITY)
    assert result["quality_risk_cost"]["by_field"]["items"]["error_rate"] == 0.075


def test_missing_inputs_returns_none_not_a_guess():
    result = compute_business_impact({}, PARAMS, SEVERITY)
    assert result["gross_ltv_value"]["value_usd"] is None
    assert result["manual_review_opex"]["value_usd"] is None
    assert result["quality_risk_cost"]["value_usd"] is None
    assert result["net_ai_profit"]["value_usd"] is None
    # ai_run_cost only needs volume, not eval data -- still computable
    assert result["ai_run_cost"]["value_usd"] == 10000 * 0.02


def test_default_params_reads_config_falls_back_to_defaults():
    assumptions = {"hourly_rate_usd": 30, "volume_docs_per_period": 500}
    params = default_params(assumptions)
    assert params["operator_hourly_rate"] == 30
    assert params["monthly_volume"] == 500
    # not present in the fixture -> falls back to DEFAULT_PARAMS
    assert params["retention_value_per_invoice"] == business_impact.DEFAULT_PARAMS["retention_value_per_invoice"]
    assert params["ai_inference_cost_per_invoice"] == business_impact.DEFAULT_PARAMS["ai_inference_cost_per_invoice"]


def test_business_impact_does_not_recompute_eval_metrics():
    """Static check: this module must never IMPORT the scoring functions
    that actually compute eval metrics -- it only reads their already-
    written output out of metrics_dict[...] (CLAUDE.md module boundary)."""
    forbidden_modules = ("evals.intake_intent_gate", "evals.intake_completeness_gate", "evals.field_accuracy", "evals.document_accuracy")
    for name, obj in vars(business_impact).items():
        module = getattr(obj, "__module__", None)
        assert module not in forbidden_modules, f"business_impact.py imports {name} from {module} -- it recomputes, doesn't just read"
