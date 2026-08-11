"""Streamlit dashboard — one panel per eval section.

Each panel has a plain-language subtitle saying what it measures (the JD
metric it maps to lives in code comments / README, not the UI). Reads the
latest eval_runs/*_metrics.json only — never recomputes a metric; that's
evals/runner.py's job. Intake through Production Simulation have data so
far; the rest render as "not implemented yet" so the section hierarchy is
visible even before it's filled in.

UI: native Streamlit only -- no injected CSS/HTML. Page layout is
"centered" (Streamlit's own narrow-column mode, ~730px) so the KPI row and
the table share one width and sit flush under each other, rather than the
"wide" layout's full-monitor-width columns. Theming (colors) comes from
.streamlit/config.toml, Streamlit's own supported theming mechanism.

Field Accuracy layout: 3 KPI cards (st.metric) then one summary table
(field / n / error rate / mean score), sorted worst-field-first. The table
uses st.table (static -- no hover toolbar to cover the numbers) rendered
from a pandas.Styler for alignment and coloring; Streamlit explicitly
supports Styler-driven colors/font-weight, this isn't hand-written CSS.
Zero-error rows are left blank rather than "0.0%"; non-zero error rates
render in red. Provenance (which run, how many records) lives in one small
caption at the bottom.

Run: streamlit run dashboard/app.py
"""

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))  # so `import evals.business_impact` resolves when run via `streamlit run dashboard/app.py`

import evals.business_impact as business_impact  # noqa: E402 -- must follow the sys.path fix above

EVAL_RUNS_DIR = REPO_ROOT / "eval_runs"

SECTION_LABELS = {
    "intake": "Intake Gate — Intent check: catches non-invoice requests and incomplete data before extraction starts.",
    "field_accuracy": "Field Accuracy — how often each extracted field matches the correct value.",
    "document_accuracy": "Document Accuracy — how many invoices come out fully correct, ready to use without review — including a breakdown by segment and document type.",
    "production_simulation": "Production Simulation — simulated production monitoring: response time and a proxy for user approval.",
    "business_impact": "Business Impact — translating the metrics above into estimated cost and savings.",
}


def load_latest_run() -> dict | None:
    files = sorted(EVAL_RUNS_DIR.glob("*_metrics.json"))
    if not files:
        return None
    with open(files[-1], encoding="utf-8") as f:
        return json.load(f)


def _confusion_table(confusion: dict) -> "pd.io.formats.style.Styler":
    rows = []
    for key, count in confusion.items():
        gt, pred = key.split("->")
        rows.append({"Ground Truth": gt, "Predicted": pred, "Count": count})
    cdf = pd.DataFrame(rows).sort_values("Count", ascending=False).reset_index(drop=True)
    return (
        cdf.style.set_properties(subset=["Ground Truth", "Predicted"], **{"text-align": "left"})
        .set_properties(subset=["Count"], **{"text-align": "right"})
        .hide(axis="index")
    )


def render_intake(intake: dict) -> None:
    st.caption(SECTION_LABELS["intake"])

    if not intake:
        st.warning("No Intake scores in this run.")
        return

    intent = intake.get("intent_gate")
    if intent:
        st.markdown("**Intent gate** — does this text ask for an invoice at all?")
        agg = intent["aggregate"]
        col1, col2, col3 = st.columns([1, 1, 1])
        col1.metric(label="Accuracy", value=f"{agg['accuracy']:.1%}")
        col2.metric(label="False Positive Rate", value=f"{agg['fp_rate']:.1%}" if agg["fp_rate"] is not None else "n/a")
        col3.metric(label="False Negative Rate", value=f"{agg['fn_rate']:.1%}" if agg["fn_rate"] is not None else "n/a")
        st.caption(f"{intent['n_records']} records classified · {intent['n_classification_failures']} classification failures")

    completeness = intake.get("completeness_gate")
    if completeness:
        st.markdown("**Completeness gate** — once it's an invoice, is there enough data to build one?")
        agg_s = completeness["aggregate_sufficiency"]
        agg_m = completeness["aggregate_missing_fields"]
        col1, col2, col3 = st.columns([1, 1, 1])
        col1.metric(label="Accuracy", value=f"{agg_s['accuracy']:.1%}")
        col2.metric(label="Missed Shortage Rate", value=f"{agg_s['missed_shortage_rate']:.1%}")
        col3.metric(label="Missing-Field F1", value=f"{agg_m['f1']:.2f}" if agg_m["f1"] is not None else "n/a")
        st.caption(
            f"{completeness['n_scored']} of {completeness['n_records_total']} records scored "
            f"({completeness['n_excluded_by_step1']} excluded — intent gate said 'not an invoice')"
        )
        st.table(_confusion_table(agg_s["confusion_matrix"]))


def render_field_accuracy(field_accuracy: dict, config: dict) -> None:
    st.caption(SECTION_LABELS["field_accuracy"])

    field_scores = field_accuracy["field_scores"]
    if not field_scores:
        st.warning("No field scores in this run.")
        return

    df = (
        pd.DataFrame(
            [
                {"field": field, "error_rate": s["error_rate"], "mean_score": s["mean_score"], "n": s["n"]}
                for field, s in field_scores.items()
            ]
        )
        .sort_values("error_rate", ascending=False)  # worst field first
        .reset_index(drop=True)
    )

    # overall KPIs: weighted by n so a field scored on 1 record doesn't count
    # as much as one scored on all of them
    total_n = df["n"].sum()
    overall_error_rate = (df["error_rate"] * df["n"]).sum() / total_n
    overall_mean_score = (df["mean_score"] * df["n"]).sum() / total_n

    col1, col2, col3 = st.columns([1, 1, 1])
    col1.metric(label="Total Records Scored", value=config["n_records_run"])
    col2.metric(label="Overall Mean Score", value=f"{overall_mean_score:.2f}")
    col3.metric(label="Overall Error Rate", value=f"{overall_error_rate:.1%}")

    # data-level formatting, not HTML: "items.quantity" -> "items › quantity",
    # and error rate pre-formatted to a plain string ("" for zero) so a
    # field with no errors renders blank instead of a distracting "0.0%".
    display_df = pd.DataFrame(
        {
            "Field": df["field"].str.replace(".", " › ", regex=False),
            "Records Scored": df["n"],
            "Error Rate": df["error_rate"].apply(lambda v: f"{v:.1%}" if v > 0 else ""),
            "Mean Score": df["mean_score"],
        }
    )

    styler = (
        display_df.style.format({"Mean Score": "{:.2f}"})
        .set_properties(subset=["Field"], **{"text-align": "left"})
        .set_properties(subset=["Records Scored", "Error Rate", "Mean Score"], **{"text-align": "right"})
        .map(lambda v: "color: #dc2626; font-weight: 600;" if v else "", subset=["Error Rate"])
        .hide(axis="index")
    )
    st.table(styler)

    with st.expander("Per-record detail"):
        st.dataframe(pd.json_normalize(field_accuracy["records"], sep="."), use_container_width=True, hide_index=True)


def render_document_accuracy(document_accuracy: dict, config: dict) -> None:
    st.caption(SECTION_LABELS["document_accuracy"])

    if not document_accuracy or document_accuracy["resolution_rate"] is None:
        st.warning("No document-level scores in this run.")
        return

    n_scored = document_accuracy["n_resolution_scored"]
    n_correct = round(document_accuracy["resolution_rate"] * n_scored)
    n_error = n_scored - n_correct

    col1, col2, col3 = st.columns([1, 1, 1])
    col1.metric(label="Documents Scored", value=n_scored)
    col2.metric(label="Correct Documents", value=n_correct)
    col3.metric(label="Resolution Rate", value=f"{document_accuracy['resolution_rate']:.1%}")

    st.caption(
        f"{n_error} documents ({document_accuracy['critical_error_rate']:.1%}) have an error in a critical field "
        f"({', '.join(document_accuracy['critical_fields'])}) — out of {config['n_records_run']} total, "
        f"{config['n_records_run'] - n_scored} weren't scoreable (a critical field wasn't extracted at all)."
    )

    st.markdown("**By segment** (clean / noisy / edge case)")
    st.table(_group_table(document_accuracy["by_segment"]))

    st.markdown("**By document type**")
    st.table(_group_table(document_accuracy["by_doc_type"]))


def _group_table(groups: dict) -> "pd.io.formats.style.Styler":
    df = (
        pd.DataFrame(
            [
                {
                    "Group": name,
                    "N": g["n_records"],
                    "Error Rate": g["overall_error_rate"],
                    "Resolution Rate": g["resolution_rate"],
                }
                for name, g in groups.items()
            ]
        )
        .sort_values("Resolution Rate", ascending=True)  # worst group first
        .reset_index(drop=True)
    )
    df["Error Rate"] = df["Error Rate"].apply(lambda v: f"{v:.1%}" if v else "")
    df["Resolution Rate"] = df["Resolution Rate"].apply(lambda v: f"{v:.1%}" if v is not None else "n/a")

    return (
        df.style.set_properties(subset=["Group"], **{"text-align": "left"})
        .set_properties(subset=["N", "Error Rate", "Resolution Rate"], **{"text-align": "right"})
        .map(lambda v: "color: #dc2626; font-weight: 600;" if v else "", subset=["Error Rate"])
        .hide(axis="index")
    )


def render_production_simulation(production_simulation: dict) -> None:
    st.caption(SECTION_LABELS["production_simulation"])

    if not production_simulation:
        st.warning("No production-simulation data in this run.")
        return

    st.markdown("**Technical error rate** — real, not estimated: how often the generator call itself failed.")
    col1, col2, col3 = st.columns([1, 1, 1])
    col1.metric(label="Technical Error Rate", value=f"{production_simulation['technical_error_rate']:.1%}")
    col2.metric(label="Failed Records", value=production_simulation["n_technical_failures"])
    col3.metric(label="Records Attempted", value=production_simulation["n_records_total"])
    if production_simulation["failure_types"]:
        types_str = ", ".join(f"{k} × {v}" for k, v in production_simulation["failure_types"].items())
        st.caption(f"Failure types: {types_str}")

    st.markdown("**Latency** — *estimated, not measured* (no run has captured real per-call timing yet).")
    lat = production_simulation["latency"]
    col1, col2, col3 = st.columns([1, 1, 1])
    col1.metric(label="p50 (est.)", value=f"{lat['p50'] / 1000:.1f}s")
    col2.metric(label="p95 (est.)", value=f"{lat['p95'] / 1000:.1f}s")
    col3.metric(label="Mean (est.)", value=f"{lat['mean'] / 1000:.1f}s")

    st.markdown("**CSAT proxy** — *stub, not a real judge or real users*: extrapolated from the critical error rate.")
    csat = production_simulation["csat_proxy"]
    if csat:
        col1, col2 = st.columns([1, 1])
        col1.metric(label="👍 Thumbs Up (stub)", value=f"{csat['thumbs_up_rate']:.1%}")
        col2.metric(label="👎 Thumbs Down (stub)", value=f"{csat['thumbs_down_rate']:.1%}")
    else:
        st.info("No critical_error_rate available to extrapolate from.")

    st.caption("Trend/drift across batches — not implemented: only one real run exists so far, nothing to trend against.")


def _impact_category(error_rate: float | None, severity_usd: float, high_threshold: float = 10) -> str:
    """"Zero Impact" wins regardless of severity tier if nothing is actually
    failing -- a high-severity field with 0% errors isn't a live risk."""
    if not error_rate:
        return "Zero Impact"
    return "Critical Churn Risk" if severity_usd >= high_threshold else "Support Overhead"


# bg/fg per category -- Tailwind red-100/red-700, amber-100/amber-700, gray-100/gray-500
_BADGE_COLORS = {
    "Critical Churn Risk": ("#fee2e2", "#b91c1c"),
    "Support Overhead": ("#fef3c7", "#b45309"),
    "Zero Impact": ("#f3f4f6", "#6b7280"),
}


def _pnl_breakdown_table(by_field: dict) -> "pd.io.formats.style.Styler":
    df = (
        pd.DataFrame(
            [
                {
                    "Field": field,
                    "Impact Category": _impact_category(v["error_rate"], v["severity_usd"]),
                    "Error Rate (%)": v["error_rate"],
                    "Severity ($)": v["severity_usd"],
                    "Financial Impact ($/mo)": v["financial_impact_usd"],
                }
                for field, v in by_field.items()
            ]
        )
        .sort_values("Financial Impact ($/mo)", ascending=False)  # worst first
        .reset_index(drop=True)
    )
    df["Error Rate (%)"] = df["Error Rate (%)"].apply(lambda v: f"{v:.1%}")

    def _badge_css(category: str) -> str:
        bg, fg = _BADGE_COLORS[category]
        return f"background-color: {bg}; color: {fg}; border-radius: 999px; padding: 2px 10px; font-weight: 600;"

    return (
        df.style.format({"Severity ($)": "${:.0f}", "Financial Impact ($/mo)": lambda v: f"-${v:,.2f}"})
        .set_properties(subset=["Field"], **{"text-align": "left"})
        .set_properties(subset=["Impact Category"], **{"text-align": "center"})
        .set_properties(subset=["Error Rate (%)", "Severity ($)", "Financial Impact ($/mo)"], **{"text-align": "right"})
        .map(_badge_css, subset=["Impact Category"])
        .map(lambda v: "color: #991b1b; font-weight: 700;", subset=["Financial Impact ($/mo)"])
        .hide(axis="index")
    )


def render_business_impact(run: dict) -> None:
    st.caption(SECTION_LABELS["business_impact"])

    defaults = business_impact.default_params()

    st.sidebar.header("Unit Economics — What-If")
    st.sidebar.caption("Business Impact P&L simulation. Defaults come from config/business_assumptions.yaml.")
    retention_value = st.sidebar.slider(
        "LTV Value per Clean Invoice ($)", min_value=0.10, max_value=5.00,
        value=float(defaults["retention_value_per_invoice"]), step=0.05,
    )
    operator_hourly_rate = st.sidebar.number_input(
        "Operator Hourly Rate ($/hr)", min_value=0.0, value=float(defaults["operator_hourly_rate"]), step=1.0,
    )
    ai_inference_cost = st.sidebar.number_input(
        "AI API Cost per Invoice ($)", min_value=0.0, value=float(defaults["ai_inference_cost_per_invoice"]), step=0.01, format="%.4f",
    )
    monthly_volume = st.sidebar.number_input(
        "Simulated Monthly Invoices Volume", min_value=1, value=int(defaults["monthly_volume"]), step=100,
    )

    params = {
        "retention_value_per_invoice": retention_value,
        "operator_hourly_rate": operator_hourly_rate,
        "ai_inference_cost_per_invoice": ai_inference_cost,
        "monthly_volume": monthly_volume,
        "avg_review_min": defaults["avg_review_min"],
    }
    # Live recompute via evals/business_impact.py (the single formula
    # implementation runner.py also uses for the static snapshot) -- the
    # dashboard never reimplements the math itself, only supplies different
    # inputs (sidebar values instead of config), see evals/business_impact.py
    # module docstring.
    pnl = business_impact.compute_business_impact(run, params=params)

    net = pnl["net_ai_profit"]["value_usd"]
    # Streamlit's st.metric can't color its own value text green/red without
    # CSS -- a deliberate, narrowly-scoped exception to "no custom CSS" for
    # just this one number, explicitly requested (profit=green/loss=red).
    color = "#16a34a" if net is not None and net >= 0 else "#dc2626"
    st.markdown(
        f'<div style="font-size:0.8rem;color:#6b7280;">Net AI Profit / mo</div>'
        f'<div style="font-size:2.25rem;font-weight:700;line-height:1.2;'
        f'color:{color};">{f"${net:,.0f}" if net is not None else "n/a"}</div>',
        unsafe_allow_html=True,
    )

    def _term(label: str, d: dict, sign: str, color: str) -> str:
        # Same narrowly-scoped markdown-color exception as Net AI Profit
        # above -- the +/- sign alone read as too subtle (conversation
        # record "чтобы была видна математика вычитания"), so subtracted
        # terms get the same dark red as the table's Financial Impact
        # column; the one additive term (Gross LTV Value) stays neutral ink.
        value = f"{sign}${d['value_usd']:,.0f}" if d["value_usd"] is not None else "n/a"
        return (
            f'<div style="font-size:0.8rem;color:#6b7280;">{label}</div>'
            f'<div style="font-size:1.5rem;font-weight:700;color:{color};">{value}</div>'
        )

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(_term("Gross LTV Value", pnl["gross_ltv_value"], "+", "#111827"), unsafe_allow_html=True)
    with col2:
        st.markdown(_term("AI Run Cost", pnl["ai_run_cost"], "-", "#991b1b"), unsafe_allow_html=True)
    with col3:
        st.markdown(_term("Manual Review OPEX", pnl["manual_review_opex"], "-", "#991b1b"), unsafe_allow_html=True)
    with col4:
        st.markdown(_term("Quality Risk Cost", pnl["quality_risk_cost"], "-", "#991b1b"), unsafe_allow_html=True)

    by_field = pnl["quality_risk_cost"].get("by_field")
    if by_field:
        st.table(_pnl_breakdown_table(by_field))

    st.info(
        "💡 Tip: Adjust retention value, operator costs, and monthly volume in the "
        "sidebar to simulate P&L under different business scenarios."
    )

    not_computed = [
        (label, pnl[key]["reason"])
        for key, label in [
            ("infra_sla_cost", "Infra/SLA cost"),
            ("churn_risk_proxy", "Churn risk proxy"),
            ("segment_risk_exposure", "Segment risk exposure"),
        ]
        if pnl.get(key, {}).get("value_usd") is None
    ]
    if not_computed:
        with st.expander("Not computed yet"):
            for label, reason in not_computed:
                st.caption(f"• {label}: {reason}")


def render_not_implemented(section_key: str) -> None:
    st.caption(SECTION_LABELS[section_key])
    st.info("Not implemented yet.")


def main() -> None:
    st.set_page_config(page_title="Invoice Eval Dashboard", layout="centered")
    # Streamlit's default top/bottom block-container padding is generous
    # (~6rem) -- there's no native page_config/theme knob for it, so this one
    # CSS trim is a deliberate, requested exception to "no custom CSS".
    st.markdown(
        """
        <style>
            .block-container {
                padding-top: 1.5rem !important;
                padding-bottom: 0rem !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.subheader("Invoice-transform — eval dashboard")

    run = load_latest_run()
    if run is None:
        st.warning(f"No eval runs found in {EVAL_RUNS_DIR}. Run `python scripts/run_eval.py --from-probe` or `python scripts/run_eval.py --smoke` first.")
        return

    config = run["config"]
    # The former Layer 3 and Layer 5 have no tab of their own: their content
    # was merged into Document Accuracy and then removed outright (see
    # evals/document_accuracy.py module docstring, conversation record
    # "удаляем этот слой... удали слои 3 и 5 из дашборда").
    tab_labels = ["Intake Gate", "Field Accuracy", "Document Accuracy", "Production Simulation", "Business Impact"]
    tabs = st.tabs(tab_labels)
    section_keys = ["intake", "field_accuracy", "document_accuracy", "production_simulation", "business_impact"]

    for tab, section_key in zip(tabs, section_keys):
        with tab:
            if section_key == "intake" and run.get("intake"):
                render_intake(run["intake"])
            elif section_key == "field_accuracy" and run.get("field_accuracy"):
                render_field_accuracy(run["field_accuracy"], config)
            elif section_key == "document_accuracy" and run.get("document_accuracy"):
                render_document_accuracy(run["document_accuracy"], config)
            elif section_key == "production_simulation" and run.get("production_simulation"):
                render_production_simulation(run["production_simulation"])
            elif section_key == "business_impact" and run.get("business_impact"):
                render_business_impact(run)
            else:
                render_not_implemented(section_key)

    st.caption(f"{config['n_records_run']} of {config['n_records_total']} records scored · run `{run['run_id']}`")


if __name__ == "__main__":
    main()
