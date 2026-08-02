"""Streamlit dashboard — one panel per eval layer.

Each panel must be explicitly labeled with the JD metric it maps to
(resolution rate, CSAT proxy, thumbs up/down, error rate, latency,
LLM-as-judge). Reads from eval_runs/, never recomputes metrics.

TODO: implement panels for Layer 1-6, reading the latest eval_runs/*.json.
"""


def main() -> None:
    raise NotImplementedError("TODO: streamlit run dashboard/app.py")


if __name__ == "__main__":
    main()
