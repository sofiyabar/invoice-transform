"""Layer 1 — Field-level scoring.

JD metric: "error rate per field type".
Strict fields (email) -> exact match.
Numeric fields (items[].quantity, items[].unitPrice) -> tolerance match.
items[].name -> simple normalized text match (see _score_item_name), NOT an
LLM judge -- empirically, 96% of real ground-truth/prediction item-name
pairs in this dataset resolve via exact-after-normalization or a
singular/plural or substring variant (1028/1069 pairs measured, see
conversation record "покажи что сейчас бывает в name"). A judge call isn't
worth the ANTHROPIC_API_KEY dependency for the ~4% left over.
Free-text fields (clientName, address) -> LLM-as-judge semantic match, see
evals/judges/field_judge.py -- these stay judge-based: person/company names
and addresses don't have items[].name's narrow "plural or substring" shape.

Two-step API:
  score_fields()      -- per-record, per-field-type scores (0-1) for one
                          (ground_truth, prediction) pair.
  aggregate_scores()  -- rolls per-record scores up across a dataset into
                          the actual Layer 1 output: mean score + error rate
                          per field type. This is what feeds Layer 2/6 and
                          the dashboard.

Item alignment assumption: ground_truth.items and prediction.items are
compared pairwise by index (no fuzzy re-ordering/matching of line items). A
length mismatch is itself scored as an error (see items.count below) rather
than silently truncating the shorter list — masking it would understate the
real error rate.
"""

from data.schema import InvoiceFields
from evals.judges.field_judge import judge_field_match

NUMERIC_TOLERANCE = 0.01  # absolute; quantity/unitPrice are already clean floats in ground truth
SEMANTIC_FIELDS = ("clientName", "address")  # judge-based
FUZZY_TEXT_FIELDS = ("items.name",)  # simple normalized match, no judge
EXACT_FIELDS = ("email",)
NUMERIC_FIELDS = ("items.quantity", "items.unitPrice")
FIELD_TYPES = (*EXACT_FIELDS, *SEMANTIC_FIELDS, *FUZZY_TEXT_FIELDS, *NUMERIC_FIELDS, "items.count")


def _normalize_str(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    return v.lower() if v else None


def _singularize(s: str) -> str:
    return s[:-1] if s.endswith("s") and len(s) > 1 else s


def _score_exact(ground_truth: str | None, prediction: str | None) -> float | None:
    """None vs None -> perfect match (nothing to extract, nothing invented).
    None vs value or value vs None -> hallucination/omission, score 0.
    Returns None only when field isn't applicable at all (unused here, kept
    for symmetry with _score_numeric)."""
    gt, pred = _normalize_str(ground_truth), _normalize_str(prediction)
    if gt is None and pred is None:
        return 1.0
    if gt is None or pred is None:
        return 0.0
    return 1.0 if gt == pred else 0.0


def _score_numeric(ground_truth: float | None, prediction: float | None) -> float:
    if ground_truth is None and prediction is None:
        return 1.0
    if ground_truth is None or prediction is None:
        return 0.0
    try:
        pred = float(prediction)
    except (TypeError, ValueError):
        return 0.0
    return 1.0 if abs(float(ground_truth) - pred) <= NUMERIC_TOLERANCE else 0.0


def _score_item_name(ground_truth: str | None, prediction: str | None) -> float:
    """Judge-free item-name match: exact after normalization, a singular/
    plural variant of each other, or one name contains the other (e.g.
    "Revision" / "Revisions", "Website Development" / "website dev"). Real
    paraphrases that fail all three ("Air Duct Cleaning" / "duct cleanings")
    are scored 0 -- a known, accepted gap, not guessed via a judge call."""
    gt, pred = _normalize_str(ground_truth), _normalize_str(prediction)
    if gt is None and pred is None:
        return 1.0
    if gt is None or pred is None:
        return 0.0
    if gt == pred:
        return 1.0
    if _singularize(gt) == _singularize(pred):
        return 1.0
    if len(gt) >= 3 and len(pred) >= 3 and (gt in pred or pred in gt):
        return 1.0
    return 0.0


def _score_semantic(
    field_name: str, ground_truth: str | None, prediction: str | None, use_judge: bool = True
) -> float | None:
    """Returns None (not 0.0) when both values are non-empty but the judge is
    disabled -- "not evaluated" must never collapse into "wrong", or a
    disabled judge would silently inflate the error rate."""
    gt, pred = _normalize_str(ground_truth), _normalize_str(prediction)
    if gt is None and pred is None:
        return 1.0
    if gt is None or pred is None:
        return 0.0
    if not use_judge:
        return None
    # judge on the original (non-lowercased) strings — casing may carry signal
    return judge_field_match(field_name, ground_truth.strip(), prediction.strip())


def score_fields(
    ground_truth: InvoiceFields, prediction: InvoiceFields, use_semantic_judge: bool = True
) -> dict[str, float]:
    """Per-record score (0-1) for each field type. Missing keys mean the field
    type didn't apply to this record (e.g. no items in ground truth and none
    predicted -> items.* keys still present at 1.0 via the None/None rule,
    except when there simply are no line items to score at all).

    use_semantic_judge=False skips LLM-judge calls entirely, for clientName/
    address only (items.name never needs it, see module docstring): trivial
    cases (both missing, or exactly one missing) are still scored without
    it, but non-trivial semantic comparisons are left out of the returned
    dict rather than guessed -- see _score_semantic. Use this when
    ANTHROPIC_API_KEY isn't available and you still want the exact/
    tolerance/item-name fields scored.
    """
    scores: dict[str, float] = {}

    scores["email"] = _score_exact(ground_truth.email, prediction.email)
    client_name_score = _score_semantic(
        "clientName", ground_truth.clientName, prediction.clientName, use_semantic_judge
    )
    if client_name_score is not None:
        scores["clientName"] = client_name_score
    address_score = _score_semantic("address", ground_truth.address, prediction.address, use_semantic_judge)
    if address_score is not None:
        scores["address"] = address_score

    gt_items = ground_truth.items or []
    pred_items = prediction.items or []
    scores["items.count"] = 1.0 if len(gt_items) == len(pred_items) else 0.0

    if gt_items or pred_items:
        n = min(len(gt_items), len(pred_items))
        name_scores, qty_scores, price_scores = [], [], []
        for i in range(n):
            gt_item, pred_item = gt_items[i], pred_items[i]
            name_scores.append(_score_item_name(gt_item.name, pred_item.name))
            qty_scores.append(_score_numeric(gt_item.quantity, pred_item.quantity))
            price_scores.append(_score_numeric(gt_item.unitPrice, pred_item.unitPrice))
        # unmatched items beyond the shorter list are extra errors, not free
        # passes -- and always trivially scorable (one side has no
        # counterpart at all: an omitted or hallucinated whole item), and
        # none of items.name/quantity/unitPrice need a judge, so this always
        # applies regardless of use_semantic_judge.
        extra = max(len(gt_items), len(pred_items)) - n
        name_scores += [0.0] * extra
        qty_scores += [0.0] * extra
        price_scores += [0.0] * extra

        scores["items.name"] = sum(name_scores) / len(name_scores)
        scores["items.quantity"] = sum(qty_scores) / len(qty_scores)
        scores["items.unitPrice"] = sum(price_scores) / len(price_scores)
    # else: no items on either side -> nothing to score, keys omitted (not
    # forced to 1.0) so aggregate_scores() doesn't count a vacuous "pass"

    return scores


def aggregate_scores(per_record_scores: list[dict[str, float]]) -> dict[str, dict[str, float]]:
    """Layer 1 output: for each field type, mean score, error rate (score < 1
    treated as an error — semantic judge scores are continuous, so this is a
    stricter reading than the raw mean) and n (records where the field type
    was applicable)."""
    result: dict[str, dict[str, float]] = {}
    for field in FIELD_TYPES:
        values = [rec[field] for rec in per_record_scores if field in rec]
        if not values:
            continue
        n = len(values)
        errors = sum(1 for v in values if v < 1.0)
        result[field] = {
            "mean_score": sum(values) / n,
            "error_rate": errors / n,
            "n": n,
        }
    return result
