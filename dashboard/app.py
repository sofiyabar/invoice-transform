"""Streamlit dashboard — one panel per eval layer.

Each panel has a plain-language subtitle saying what it measures (the JD
metric it maps to lives in code comments / README, not the UI). Reads the
latest eval_runs/*_metrics.json only — never recomputes a metric; that's
evals/runner.py's job. Only Layer 1-2 have data so far; the rest render as
"not implemented yet" so the layer hierarchy is visible even before it's
filled in.

UI: native Streamlit only -- no injected CSS/HTML. Page layout is
"centered" (Streamlit's own narrow-column mode, ~730px) so the KPI row and
the table share one width and sit flush under each other, rather than the
"wide" layout's full-monitor-width columns. Theming (colors) comes from
.streamlit/config.toml, Streamlit's own supported theming mechanism.

Layer 1 layout: 3 KPI cards (st.metric) then one summary table (field / n /
error rate / mean score), sorted worst-field-first. The table uses st.table
(static -- no hover toolbar to cover the numbers) rendered from a
pandas.Styler for alignment and coloring; Streamlit explicitly supports
Styler-driven colors/font-weight, this isn't hand-written CSS. Zero-error
rows are left blank rather than "0.0%"; non-zero error rates render in red.
Provenance (which run, how many records) lives in one small caption at the
bottom.

Run: streamlit run dashboard/app.py
"""

import json
from pathlib import Path

import pandas as pd
import streamlit as st

REPO_ROOT = Path(__file__).resolve().parent.parent
EVAL_RUNS_DIR = REPO_ROOT / "eval_runs"

LAYER_LABELS = {
    "layer0": "Layer 0 — Intent check: catches non-invoice requests and incomplete data before extraction starts.",
    "layer1": "Layer 1 — Field accuracy: how often each extracted field matches the correct value.",
    "layer2": "Layer 2 — Document accuracy: how many invoices come out fully correct, ready to use without review.",
    "layer3": "Layer 3 — Breakdown by segment and document type: where accuracy holds up and where it doesn't.",
    "layer4": "Layer 4 — Simulated production monitoring: response time and a proxy for user approval.",
    "layer5": "Layer 5 — Statistical confidence: how reliable these numbers are, not just what they are.",
    "layer6": "Layer 6 — Business impact: translating the metrics above into estimated cost and savings.",
}


def load_latest_run() -> dict | None:
    files = sorted(EVAL_RUNS_DIR.glob("*_metrics.json"))
    if not files:
        return None
    with open(files[-1], encoding="utf-8") as f:
        return json.load(f)


def render_layer1(layer1: dict, config: dict) -> None:
    st.caption(LAYER_LABELS["layer1"])

    field_scores = layer1["field_scores"]
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
        st.dataframe(pd.json_normalize(layer1["records"], sep="."), use_container_width=True, hide_index=True)


def render_layer2(layer2: dict, config: dict) -> None:
    st.caption(LAYER_LABELS["layer2"])

    if not layer2:
        st.warning("No document-level scores in this run.")
        return

    def _pct(v: float | None) -> str:
        return f"{v:.1%}" if v is not None else "n/a"

    wds = layer2["weighted_document_score"]

    col1, col2, col3 = st.columns([1, 1, 1])
    col1.metric(label="Resolution Rate", value=_pct(layer2["resolution_rate"]))
    col2.metric(label="Critical Error Rate", value=_pct(layer2["critical_error_rate"]))
    col3.metric(label="Weighted Document Score", value=f"{wds['mean']:.2f}" if wds["mean"] is not None else "n/a")

    st.caption(
        f"Resolution rate is based on {layer2['n_resolution_scored']} of {config['n_records_run']} documents "
        f"with every critical field ({', '.join(layer2['critical_fields'])}) scored."
    )

    weights_df = (
        pd.DataFrame(
            {
                "Field": list(layer2["field_weights"].keys()),
                "Weight": list(layer2["field_weights"].values()),
                "Critical": [f in layer2["critical_fields"] for f in layer2["field_weights"]],
            }
        )
        .sort_values("Weight", ascending=False)
        .reset_index(drop=True)
    )
    weights_df["Critical"] = weights_df["Critical"].map({True: "yes", False: ""})

    styler = (
        weights_df.style.format({"Weight": "{:.2f}"})
        .set_properties(subset=["Field"], **{"text-align": "left"})
        .set_properties(subset=["Weight", "Critical"], **{"text-align": "right"})
        .hide(axis="index")
    )
    st.table(styler)


def render_not_implemented(layer_key: str) -> None:
    st.caption(LAYER_LABELS[layer_key])
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
    tab_labels = ["Layer 1", "Layer 2", "Layer 3", "Layer 4", "Layer 5", "Layer 6"]
    tabs = st.tabs(tab_labels)
    layer_keys = ["layer1", "layer2", "layer3", "layer4", "layer5", "layer6"]

    for tab, layer_key in zip(tabs, layer_keys):
        with tab:
            if layer_key == "layer1" and run.get("layer1"):
                render_layer1(run["layer1"], config)
            elif layer_key == "layer2" and run.get("layer2"):
                render_layer2(run["layer2"], config)
            else:
                render_not_implemented(layer_key)

    st.caption(f"{config['n_records_run']} of {config['n_records_total']} records scored · run `{run['run_id']}`")


if __name__ == "__main__":
    main()
