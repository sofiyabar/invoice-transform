"""Layer 3 — Segment-level breakdown.

JD framing: "mine failure patterns from real traffic" (simulated via
synthetic segments). Pure re-aggregation of Layer 1/2 outputs sliced by
segment x doc_type — must not call judges again.

TODO: implement groupby(segment, doc_type) over Layer 1/2 outputs.
"""


def by_segment(doc_scores: list[dict], segment_field: str = "segment") -> dict:
    raise NotImplementedError("TODO: slice resolution_rate / error_rate by segment and doc_type")
