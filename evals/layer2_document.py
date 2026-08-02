"""Layer 2 — Document-level scoring.

JD metrics: "resolution rate", "critical error rate".
Reads config/field_weights.yaml to weight critical fields (total, company)
higher than non-critical ones.

TODO: implement weighted document score, resolution rate, critical error rate.
"""


def resolution_rate(field_scores: list[dict[str, float]]) -> float:
    raise NotImplementedError("TODO: % of documents where all critical fields are correct")


def critical_error_rate(field_scores: list[dict[str, float]]) -> float:
    raise NotImplementedError("TODO: % of documents with an error in a critical field")
