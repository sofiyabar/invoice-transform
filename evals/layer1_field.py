"""Layer 1 — Field-level scoring.

JD metric: "error rate per field type".
Strict fields (invoice_number, currency) -> exact match.
Numeric/date fields (total, date) -> tolerance match.
Free-text fields (company, address, line_items) -> LLM-as-judge semantic
match, see evals/judges/field_judge.py.

TODO: implement per-field scoring and aggregation into error-rate-per-field-type.
"""

from data.schema import InvoiceFields


def score_fields(ground_truth: InvoiceFields, prediction: InvoiceFields) -> dict[str, float]:
    raise NotImplementedError("TODO: exact / tolerance / semantic-judge scoring per field")
