"""End-to-end production pipeline: raw text in, invoice fields (or a reason
we stopped short) out.

Chains the three generator/ components in the order a real product would
call them -- until now each had only ever been exercised independently, in
one-off scripts (scripts/run_intake_intent_full.py, generate_all.py,
run_intake_completeness_full.py each hit the API for their own narrow slice
and never actually called each other):

  1. intent_gate.is_invoice_request(text)   -- not an invoice? stop here.
  2. base_generator.parse_invoice_from_text(text) -- extract fields.
  3. completeness_gate.check_sufficiency(fields)  -- classify what we got.

Returns a dict recording the outcome at every stage reached, so a caller
(evals/runner.py, or a real product) can act on -- or score -- the whole
decision chain from one real run.
"""

from data.schema import InvoiceFields
from generator.base_generator import normalize_prediction, parse_invoice_from_text
from generator.completeness_gate import check_sufficiency, missing_critical_fields
from generator.intent_gate import is_invoice_request


def run_pipeline(raw_text: str) -> dict:
    """Runs the full decision chain on one piece of text. Stops early and
    leaves later stages at their default (None) once a stage says "no" or
    fails -- a non-invoice text never reaches extraction, and a parse
    failure never reaches the completeness check.
    """
    result: dict = {
        "is_invoice_request": None,
        "raw_prediction": None,
        "fields": None,
        "parse_error": None,
        "sufficiency": None,
        "missing_critical_fields": None,
    }

    result["is_invoice_request"] = is_invoice_request(raw_text)
    if not result["is_invoice_request"]:
        return result

    try:
        raw_prediction = parse_invoice_from_text(raw_text)
    except Exception as e:
        result["parse_error"] = f"{type(e).__name__}: {e}"
        return result
    result["raw_prediction"] = raw_prediction

    try:
        fields = InvoiceFields(**normalize_prediction(raw_prediction))
    except Exception as e:
        result["parse_error"] = f"{type(e).__name__}: {e}"
        return result
    result["fields"] = fields

    result["sufficiency"] = check_sufficiency(fields)
    result["missing_critical_fields"] = sorted(missing_critical_fields(fields))
    return result
