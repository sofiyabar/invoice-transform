"""Document Accuracy (formerly "Layer 2") — document-level scoring.

JD metrics: "resolution rate", "critical error rate". Both are plain counts
of documents, not a weighted score -- see conversation record ("тогда нужно
это называть не весами, а стоимость убытков... иначе метрика бесполезна"):
an earlier version of this module also computed a "weighted document score"
from invented 0-1 field weights (config/field_weights.yaml, now removed).
That number wasn't tied to anything real and didn't belong here -- a $-cost
weighting only makes sense once real business figures exist for Business
Impact (config/severity_weights.yaml), not as an arbitrary blend here.

Input shape: a list of per-document score dicts, i.e. exactly what
evals/field_accuracy.py's score_fields() returns for each record -- one dict
per document, keyed by field-accuracy field type ("email", "clientName",
"address", "items.name", "items.quantity", "items.unitPrice", "items.count").
This module does not call score_fields() or any judge itself -- pure
re-aggregation of field-accuracy output, per CLAUDE.md's module boundaries.

Entry points:
  document_field_scores()  -- collapses one document's field-accuracy
                               field-type scores into 4 document-level
                               fields (items.* -> one "items").
  resolution_rate() / critical_error_rate() -- dataset-level rates over
                               CRITICAL_FIELDS, complementary by definition
                               (resolution_rate = 1 - critical_error_rate),
                               reported separately because they're both
                               named JD metrics for different audiences.
  by_group()                -- field-accuracy field-level scores +
                               resolution rate sliced by segment or doc_type
                               (originally a separate Layer 3, merged in per
                               conversation record "3 слой нужно перенести
                               во 2").
  document_level_summary() -- the dict Document Accuracy's dashboard panel
                               reads.

CRITICAL_FIELDS (clientName, items) is a plain, qualitative call, not
derived from any weight: a wrong client name means billing the wrong
person; wrong items means billing the wrong thing/amount -- either makes
the invoice unusable without human review. email/address are contact
details a human can add or fix without re-running extraction.

Honesty rule (matches field accuracy): a document where a critical field
wasn't applicable/scored at all (e.g. no items on either side, see
evals/field_accuracy.py) is excluded from resolution_rate/critical_error_rate,
not guessed as pass or fail.

Statistical context (bootstrap CI on resolution_rate, significance vs a
baseline segment -- merged in from the former Layer 5) was added on top of
the segment/doc-type breakdown and then removed per conversation record
("нам это не надо... Удали эти данные из таблицы"): the significance test
specifically didn't answer a question this project actually has -- 97% of
"noisy" and 76% of "edge" records are already correctly caught as partial/
incomplete by Intake's completeness gate (97.7% accuracy there) and would
never reach full field extraction in a real pipeline. "Can we tell complete
from incomplete" is Intake's job, already measured.

The plain by_group() breakdown itself (rate per segment/doc_type, no
p-value) stayed -- see conversation record ("таблица должна была остаться
на уровне два... верни") -- only the significance/CI layer on top of it
was the part that didn't belong.
"""

from evals.field_accuracy import aggregate_scores

CRITICAL_FIELDS = ("clientName", "items")

ITEMS_SUBFIELDS = ("items.name", "items.quantity", "items.unitPrice", "items.count")


def _items_subscores(record_scores: dict[str, float]) -> list[float]:
    return [record_scores[k] for k in ITEMS_SUBFIELDS if k in record_scores]


def document_field_scores(record_scores: dict[str, float]) -> dict[str, float]:
    """Collapse one document's field-accuracy per-field-type scores into 4
    document-level fields (email, clientName, address, items). items.* are
    averaged into a single "items" score; a document with no items.* keys at
    all (no line items on either side) has no "items" entry, same as
    field-accuracy omits inapplicable fields rather than forcing a score."""
    out: dict[str, float] = {}
    for field in ("email", "clientName", "address"):
        if field in record_scores:
            out[field] = record_scores[field]

    items = _items_subscores(record_scores)
    if items:
        out["items"] = sum(items) / len(items)

    return out


def critical_fields_all_correct(record_scores: dict[str, float]) -> bool | None:
    """None if any critical field wasn't scored at all in this document
    (excluded from the rate, not counted as a failure). Exposed publicly so
    callers (e.g. evals/runner.py) can report how many documents the rate
    below is actually based on, without duplicating this logic."""
    doc_fields = document_field_scores(record_scores)
    for field in CRITICAL_FIELDS:
        if field not in doc_fields:
            return None
    return all(doc_fields[field] == 1.0 for field in CRITICAL_FIELDS)


def resolution_rate(field_scores: list[dict[str, float]]) -> float:
    """% of documents where every critical field (CRITICAL_FIELDS) is
    exactly correct, i.e. resolvable without human review."""
    outcomes = [critical_fields_all_correct(r) for r in field_scores]
    applicable = [o for o in outcomes if o is not None]
    if not applicable:
        raise ValueError("no documents had all critical fields scored -- cannot compute resolution rate")
    return sum(applicable) / len(applicable)


def critical_error_rate(field_scores: list[dict[str, float]]) -> float:
    """% of documents with an error in at least one critical field.
    Complementary to resolution_rate by definition -- both are reported
    because they're separately named JD metrics."""
    return 1.0 - resolution_rate(field_scores)


def _group_scored(per_record: list[dict], group_field: str) -> dict[str, list[dict[str, float]]]:
    groups: dict[str, list[dict[str, float]]] = {}
    for r in per_record:
        if not r.get("parse_ok") or r.get(group_field) is None:
            continue
        groups.setdefault(r[group_field], []).append(r["scores"])
    return groups


def by_group(per_record: list[dict], group_field: str) -> dict[str, dict]:
    """Slices field-accuracy field-level scores + this module's resolution rate by
    group_field ("segment" or "doc_type"). One entry per group value, same
    headline shape as document_level_summary() so the dashboard can reuse
    the same table renderer. No significance test -- see module docstring."""
    result: dict[str, dict] = {}
    for group_value, scored in _group_scored(per_record, group_field).items():
        field_scores = aggregate_scores(scored)
        total_n = sum(s["n"] for s in field_scores.values())
        overall_error_rate = (
            sum(s["error_rate"] * s["n"] for s in field_scores.values()) / total_n if total_n else None
        )

        n_resolution_scored = sum(1 for r in scored if critical_fields_all_correct(r) is not None)
        try:
            res_rate = resolution_rate(scored)
        except ValueError:
            res_rate = None

        result[group_value] = {
            "n_records": len(scored),
            "overall_error_rate": overall_error_rate,
            "resolution_rate": res_rate,
            "n_resolution_scored": n_resolution_scored,
        }
    return result


def document_level_summary(per_record: list[dict]) -> dict | None:
    """Everything Document Accuracy shows: resolution rate, critical error rate, how
    many documents each is based on, and the segment/doc-type breakdown."""
    scored = [r["scores"] for r in per_record if r["parse_ok"]]
    if not scored:
        return None

    n_resolution_scored = sum(1 for r in scored if critical_fields_all_correct(r) is not None)
    try:
        res_rate = resolution_rate(scored)
        crit_err_rate = critical_error_rate(scored)
    except ValueError:
        res_rate = None
        crit_err_rate = None

    return {
        "resolution_rate": res_rate,
        "critical_error_rate": crit_err_rate,
        "n_resolution_scored": n_resolution_scored,
        "critical_fields": list(CRITICAL_FIELDS),
        "by_segment": by_group(per_record, "segment"),
        "by_doc_type": by_group(per_record, "doc_type"),
    }
