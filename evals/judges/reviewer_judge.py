"""DeepEval GEval judge simulating a human reviewer for Layer 4's
CSAT/thumbs-up-down proxy.

IMPORTANT: this is a simulated proxy, not real user feedback — must be
labeled as such everywhere it's surfaced (README, dashboard).

TODO: implement using deepeval.metrics.GEval, returning thumbs_up: bool
and confidence: float.
"""

from data.schema import InvoiceFields


def review_prediction(ground_truth: InvoiceFields, prediction: InvoiceFields) -> dict:
    raise NotImplementedError("TODO: DeepEval GEval reviewer -> {thumbs_up, confidence}")
