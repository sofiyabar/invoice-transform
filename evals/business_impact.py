"""Business Impact (formerly "Layer 6"): interactive Unit Economics / P&L.

Reads ONLY the metrics_dict produced by the other eval sections plus
config/*.yaml assumptions (or live sidebar overrides of those same
assumptions, passed in as `params`) -- must not compute any eval metric
from scratch (CLAUDE.md module boundary: nothing here calls
evals.field_accuracy/document_accuracy's scoring functions, only reads
their already-written output out of metrics_dict). Every $ figure comes
back with the inputs that produced it and exactly where each one came from
-- a metrics_dict path, a config key, or "sidebar" (a live override of that
same config key) -- so it's always traceable, never a hardcoded number
(see tests/test_business_impact.py).

P&L formula (see conversation record "переделай слой Layer 6 в
интерактивный P&L дашборд Unit Economics" -- full spec from the user):

  Net AI Profit = Gross LTV Value - AI Run Cost - Manual Review OPEX - Quality Risk Cost

  Gross LTV Value    = monthly_volume * (1 - overall_error_rate) * retention_value_per_invoice
  AI Run Cost         = monthly_volume * ai_inference_cost_per_invoice
  Manual Review OPEX  = (1 - resolution_rate) * monthly_volume * (avg_review_min / 60) * operator_hourly_rate
  Quality Risk Cost   = sum(field_error_rate_i * field_severity_usd_i) * monthly_volume

overall_error_rate is the same n-weighted mean across every field-accuracy
field type that dashboard/app.py's Field Accuracy panel already labels
"Overall Error Rate" -- computed here from metrics_dict.field_accuracy.
field_scores, not recomputed from raw records.

default_params() pulls monthly_volume/operator_hourly_rate/avg_review_min/
retention_value_per_invoice/ai_inference_cost_per_invoice from
config/business_assumptions.yaml (falling back to DEFAULT_PARAMS only for
keys genuinely missing from the file). The dashboard's sidebar sliders
start at these same defaults and can override any of them live; either way
the values flow into this same function -- there is no separate "live"
formula, just different inputs to one formula.

NOT implemented -- each needs business inputs not yet gathered:
  infra_sla_cost -- compute_cost_per_sec_usd / SLA figures still 0 in
                    config/business_assumptions.yaml.
  churn_risk_proxy / segment_risk_exposure -- no agreed formula/inputs yet.
"""

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
BUSINESS_ASSUMPTIONS_PATH = REPO_ROOT / "config" / "business_assumptions.yaml"
SEVERITY_WEIGHTS_PATH = REPO_ROOT / "config" / "severity_weights.yaml"

ITEMS_SUBFIELDS = ("items.name", "items.quantity", "items.unitPrice", "items.count")

# Used only for params config/business_assumptions.yaml doesn't (yet) define
# -- see conversation record for where each of these numbers was confirmed.
DEFAULT_PARAMS = {
    "retention_value_per_invoice": 0.50,
    "operator_hourly_rate": 25.0,
    "ai_inference_cost_per_invoice": 0.02,
    "monthly_volume": 10000,
    "avg_review_min": 3.0,
}

NOT_COMPUTED = {
    "infra_sla_cost": "compute_cost_per_sec_usd / SLA figures not gathered yet (config/business_assumptions.yaml still 0)",
    "churn_risk_proxy": "no agreed f(thumbs_down_rate) scale yet",
    "segment_risk_exposure": "avg_error_cost not gathered yet",
}


def load_yaml(path: Path) -> dict[str, float]:
    with open(path, encoding="utf-8") as f:
        return dict(yaml.safe_load(f))


def default_params(business_assumptions: dict[str, float] | None = None) -> dict[str, float]:
    """Sidebar/formula defaults: config/business_assumptions.yaml where the
    key is present, DEFAULT_PARAMS otherwise. Also what the dashboard's
    sidebar widgets initialize to before the user touches a slider."""
    assumptions = business_assumptions if business_assumptions is not None else load_yaml(BUSINESS_ASSUMPTIONS_PATH)
    return {
        "retention_value_per_invoice": assumptions.get("retention_value_per_invoice", DEFAULT_PARAMS["retention_value_per_invoice"]),
        "operator_hourly_rate": assumptions.get("hourly_rate_usd", DEFAULT_PARAMS["operator_hourly_rate"]),
        "ai_inference_cost_per_invoice": assumptions.get("ai_inference_cost_per_invoice", DEFAULT_PARAMS["ai_inference_cost_per_invoice"]),
        "monthly_volume": assumptions.get("volume_docs_per_period", DEFAULT_PARAMS["monthly_volume"]),
        "avg_review_min": assumptions.get("avg_review_min", DEFAULT_PARAMS["avg_review_min"]),
    }


def _overall_error_rate(field_scores: dict[str, dict]) -> float | None:
    """n-weighted mean error rate across every field-accuracy field type --
    the same computation dashboard/app.py's Field Accuracy panel uses for
    its "Overall Error Rate" KPI."""
    if not field_scores:
        return None
    total_n = sum(s["n"] for s in field_scores.values())
    return sum(s["error_rate"] * s["n"] for s in field_scores.values()) / total_n if total_n else None


def _items_error_rate(field_scores: dict[str, dict]) -> float | None:
    """Collapse the 4 items.* field-accuracy field types into one n-weighted
    error rate, matching severity_weights.yaml's single "items" key."""
    present = [field_scores[f] for f in ITEMS_SUBFIELDS if f in field_scores]
    if not present:
        return None
    total_n = sum(s["n"] for s in present)
    return sum(s["error_rate"] * s["n"] for s in present) / total_n if total_n else None


def _gross_ltv_value(field_scores: dict, volume: float, retention_value: float) -> dict[str, Any]:
    overall_error_rate = _overall_error_rate(field_scores)
    if overall_error_rate is None or not volume:
        return {"value_usd": None, "reason": "missing metrics_dict.field_accuracy.field_scores"}
    return {
        "value_usd": round(volume * (1 - overall_error_rate) * retention_value, 2),
        "formula": "monthly_volume * (1 - overall_error_rate) * retention_value_per_invoice",
        "inputs": {
            "overall_error_rate": {"value": overall_error_rate, "source": "metrics_dict.field_accuracy.field_scores (n-weighted mean)"},
            "monthly_volume": {"value": volume, "source": "sidebar / config.business_assumptions.volume_docs_per_period"},
            "retention_value_per_invoice": {"value": retention_value, "source": "sidebar / config.business_assumptions.retention_value_per_invoice"},
        },
    }


def _ai_run_cost(volume: float, ai_cost_per_invoice: float) -> dict[str, Any]:
    if not volume:
        return {"value_usd": None, "reason": "missing monthly_volume"}
    return {
        "value_usd": round(volume * ai_cost_per_invoice, 2),
        "formula": "monthly_volume * ai_inference_cost_per_invoice",
        "inputs": {
            "monthly_volume": {"value": volume, "source": "sidebar / config.business_assumptions.volume_docs_per_period"},
            "ai_inference_cost_per_invoice": {"value": ai_cost_per_invoice, "source": "sidebar / config.business_assumptions.ai_inference_cost_per_invoice"},
        },
    }


def _manual_review_opex(document_accuracy: dict | None, volume: float, avg_review_min: float, hourly_rate: float) -> dict[str, Any]:
    resolution_rate = document_accuracy.get("resolution_rate") if document_accuracy else None
    if resolution_rate is None or not volume:
        return {"value_usd": None, "reason": "missing metrics_dict.document_accuracy.resolution_rate"}
    return {
        "value_usd": round((1 - resolution_rate) * volume * (avg_review_min / 60) * hourly_rate, 2),
        "formula": "(1 - resolution_rate) * monthly_volume * (avg_review_min / 60) * operator_hourly_rate",
        "inputs": {
            "resolution_rate": {"value": resolution_rate, "source": "metrics_dict.document_accuracy.resolution_rate"},
            "monthly_volume": {"value": volume, "source": "sidebar / config.business_assumptions.volume_docs_per_period"},
            "avg_review_min": {"value": avg_review_min, "source": "config.business_assumptions.avg_review_min"},
            "operator_hourly_rate": {"value": hourly_rate, "source": "sidebar / config.business_assumptions.hourly_rate_usd"},
        },
    }


def _quality_risk_cost(field_scores: dict, severity: dict[str, float], volume: float) -> dict[str, Any]:
    by_field: dict[str, Any] = {}
    total = 0.0
    for field, severity_usd in severity.items():
        error_rate = _items_error_rate(field_scores) if field == "items" else field_scores.get(field, {}).get("error_rate")
        if error_rate is None:
            continue
        contribution = error_rate * severity_usd * volume if volume else 0.0
        total += contribution
        by_field[field] = {
            "error_rate": error_rate,
            "error_rate_source": f"metrics_dict.field_accuracy.field_scores.{field}.error_rate"
            if field != "items"
            else "metrics_dict.field_accuracy.field_scores.items.* (n-weighted average)",
            "severity_usd": severity_usd,
            "severity_source": f"config.severity_weights.{field}",
            "financial_impact_usd": round(contribution, 2),
        }
    if not by_field:
        return {"value_usd": None, "reason": "no matching field_scores for any field in config.severity_weights"}
    return {
        "value_usd": round(total, 2),
        "formula": "sum(field_error_rate * field_severity_usd) * monthly_volume",
        "by_field": by_field,
    }


def compute_business_impact(
    metrics_dict: dict[str, Any],
    params: dict[str, float] | None = None,
    severity_weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """metrics_dict is read-only here. `params` defaults to config/
    business_assumptions.yaml via default_params() -- the dashboard passes
    its live sidebar values instead for the interactive what-if view, same
    formula either way."""
    params = params if params is not None else default_params()
    severity = severity_weights if severity_weights is not None else load_yaml(SEVERITY_WEIGHTS_PATH)

    field_scores = (metrics_dict.get("field_accuracy") or {}).get("field_scores") or {}
    document_accuracy = metrics_dict.get("document_accuracy")
    volume = params["monthly_volume"]

    gross_ltv_value = _gross_ltv_value(field_scores, volume, params["retention_value_per_invoice"])
    ai_run_cost = _ai_run_cost(volume, params["ai_inference_cost_per_invoice"])
    manual_review_opex = _manual_review_opex(document_accuracy, volume, params["avg_review_min"], params["operator_hourly_rate"])
    quality_risk_cost = _quality_risk_cost(field_scores, severity, volume)

    values = [gross_ltv_value["value_usd"], ai_run_cost["value_usd"], manual_review_opex["value_usd"], quality_risk_cost["value_usd"]]
    if all(v is not None for v in values):
        net_ai_profit = {
            "value_usd": round(values[0] - values[1] - values[2] - values[3], 2),
            "formula": "gross_ltv_value - ai_run_cost - manual_review_opex - quality_risk_cost",
        }
    else:
        net_ai_profit = {"value_usd": None, "reason": "missing one or more of gross_ltv_value/ai_run_cost/manual_review_opex/quality_risk_cost"}

    result: dict[str, Any] = {
        "params": params,
        "gross_ltv_value": gross_ltv_value,
        "ai_run_cost": ai_run_cost,
        "manual_review_opex": manual_review_opex,
        "quality_risk_cost": quality_risk_cost,
        "net_ai_profit": net_ai_profit,
    }
    for key, reason in NOT_COMPUTED.items():
        result[key] = {"value_usd": None, "reason": reason}
    return result
