"""Layer 0, Step 2: given what generator/base_generator.py already extracted,
is there enough data to actually build an invoice?

Same reasoning as generator/intent_gate.py for placement: this is a production
decision (gates whether to send the invoice or ask the user for more), not a
judge grading an existing output, so it lives in generator/, not evals/.

Unlike Step 1, this needs no LLM call at all -- it's a deterministic rule over
fields the generator already extracted, reusing that same extraction call
rather than asking a second model to re-judge the raw text (see CHANGELOG.md
2026-08-10 for the discussion of why: an independent text-only judgment would
decouple this step's accuracy from generator/base_generator.py's own
extraction errors, but in production what matters is "can we build the
invoice from what we actually got", not "was the source text theoretically
complete").
"""

from data.schema import CRITICAL_FIELDS, InvoiceFields


def _is_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    if isinstance(value, list) and len(value) == 0:
        return True
    return False


def missing_critical_fields(fields: InvoiceFields) -> set[str]:
    """Which of CRITICAL_FIELDS are empty/missing on this (extracted or
    ground-truth) InvoiceFields."""
    return {name for name in CRITICAL_FIELDS if _is_empty(getattr(fields, name))}


def check_sufficiency(fields: InvoiceFields) -> str:
    """Returns "none" (all critical fields missing), "partial" (some
    missing), or "complete" (none missing) -- see CHANGELOG.md 2026-08-10 for
    how this three-way rule was chosen."""
    missing = missing_critical_fields(fields)
    if not missing:
        return "complete"
    if missing == set(CRITICAL_FIELDS):
        return "none"
    return "partial"
