"""Layer 2 — Document-level scoring.

JD metrics: "resolution rate", "critical error rate".
Reads config/field_weights.yaml to weight critical fields (clientName,
items) higher than non-critical ones (email, address).

Input shape: a list of per-document score dicts, i.e. exactly what
evals/layer1_field.py's score_fields() returns for each record -- one dict
per document, keyed by Layer 1 field type ("email", "clientName", "address",
"items.name", "items.quantity", "items.unitPrice", "items.count"). This
module does not call score_fields() or any judge itself -- pure
re-aggregation of Layer 1 output, per CLAUDE.md's module boundaries.

Three entry points:
  document_field_scores()  -- collapses one document's Layer 1 field-type
                               scores into the 4 fields field_weights.yaml
                               assigns weights to (items.* -> one "items").
  weighted_document_score() -- one document's weighted score (0-1).
  resolution_rate() / critical_error_rate() -- dataset-level rates over
                               CRITICAL_FIELDS, complementary by definition
                               (resolution_rate = 1 - critical_error_rate),
                               reported separately because they're both
                               named JD metrics for different audiences.

Honesty rule (matches Layer 1): a document where a critical field wasn't
scored at all (e.g. the semantic judge was skipped, see
evals/layer1_field.py use_semantic_judge=False) is excluded from
resolution_rate/critical_error_rate, not guessed as pass or fail.
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
FIELD_WEIGHTS_PATH = REPO_ROOT / "config" / "field_weights.yaml"

# The subset of document_field_scores() keys that must ALL be correct for a
# document to "resolve" (JD: resolution rate) -- see config/field_weights.yaml
# for the rationale. Kept as the two highest-weighted fields there.
CRITICAL_FIELDS = ("clientName", "items")

ITEMS_SUBFIELDS = ("items.name", "items.quantity", "items.unitPrice", "items.count")


def load_field_weights(path: Path = FIELD_WEIGHTS_PATH) -> dict[str, float]:
    with open(path, encoding="utf-8") as f:
        weights = yaml.safe_load(f)
    return dict(weights)


def _items_subscores(record_scores: dict[str, float]) -> list[float]:
    return [record_scores[k] for k in ITEMS_SUBFIELDS if k in record_scores]


def document_field_scores(record_scores: dict[str, float]) -> dict[str, float]:
    """Collapse one document's Layer 1 per-field-type scores into the 4
    document-level fields field_weights.yaml has weights for. items.* are
    averaged into a single "items" score; a document with no items.* keys at
    all (no line items on either side) has no "items" entry, same as Layer 1
    omits inapplicable fields rather than forcing a score."""
    out: dict[str, float] = {}
    for field in ("email", "clientName", "address"):
        if field in record_scores:
            out[field] = record_scores[field]

    items = _items_subscores(record_scores)
    if items:
        out["items"] = sum(items) / len(items)

    return out


def weighted_document_score(record_scores: dict[str, float], weights: dict[str, float] | None = None) -> float | None:
    """One document's field score weighted by config/field_weights.yaml.
    Returns None if none of the weighted fields were scored for this
    document (nothing to weight)."""
    weights = weights if weights is not None else load_field_weights()
    doc_fields = document_field_scores(record_scores)
    applicable = {f: v for f, v in doc_fields.items() if weights.get(f, 0) > 0}
    total_weight = sum(weights[f] for f in applicable)
    if not applicable or total_weight == 0:
        return None
    return sum(applicable[f] * weights[f] for f in applicable) / total_weight


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
