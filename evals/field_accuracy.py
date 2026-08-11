"""Field Accuracy (formerly "Layer 1") — field-level scoring.

JD metric: "error rate per field type".
Strict fields (email) -> exact match.
Numeric fields (items[].quantity, items[].unitPrice) -> tolerance match.
Free-text fields (clientName, address, items[].name) -> simple normalized
text match (see _score_fuzzy_text), NOT an LLM judge. Empirically, on this
dataset's real generator predictions: 231/237 clientName pairs, 134/134
address pairs, and 1028/1069 item-name pairs resolve via exact-after-
normalization, a punctuation/whitespace variant, a singular/plural variant,
or one value containing the other (see conversation record "clientName и
address тоже почини так же" / "покажи что сейчас бывает в name"). The
remaining few-percent gap (mostly a dropped last name or a genuine
paraphrase like "Air Duct Cleaning" / "duct cleanings") is a known, accepted
trade-off for not depending on ANTHROPIC_API_KEY -- evals/judges/field_judge.py
still exists and works if a judge-based re-score of that residual gap is
ever wanted, it's just not in this module's default path.

Two-step API:
  score_fields()      -- per-record, per-field-type scores (0-1) for one
                          (ground_truth, prediction) pair.
  aggregate_scores()  -- rolls per-record scores up across a dataset into
                          the actual field-accuracy output: mean score +
                          error rate per field type. This is what feeds
                          document accuracy / business impact and the
                          dashboard.

Item alignment assumption: ground_truth.items and prediction.items are
compared pairwise by index (no fuzzy re-ordering/matching of line items). A
length mismatch is itself scored as an error (see items.count below) rather
than silently truncating the shorter list — masking it would understate the
real error rate.
"""

import re

from data.schema import InvoiceFields

NUMERIC_TOLERANCE = 0.01  # absolute; quantity/unitPrice are already clean floats in ground truth
FUZZY_TEXT_FIELDS = ("clientName", "address", "items.name")  # simple normalized match, no judge
EXACT_FIELDS = ("email",)
NUMERIC_FIELDS = ("items.quantity", "items.unitPrice")
FIELD_TYPES = (*EXACT_FIELDS, *FUZZY_TEXT_FIELDS, *NUMERIC_FIELDS, "items.count")


def _normalize_str(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    return v.lower() if v else None


def _fuzzy_normalize(v: str) -> str:
    """Extra normalization on top of _normalize_str, for fuzzy text fields
    only -- NOT used for email, where a period is meaningful (john.doe@x.com
    != johndoe@x.com)."""
    v = re.sub(r"[.,]", "", v)
    return re.sub(r"\s+", " ", v).strip()


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


def _score_fuzzy_text(ground_truth: str | None, prediction: str | None) -> float:
    """Judge-free free-text match, used for clientName/address/items.name
    alike: exact after normalization (case, punctuation, whitespace), a
    singular/plural variant, or one value containing the other (e.g.
    "Wardiere Inc." / "Wardiere Inc", "123 Anywhere St, Any City" /
    "123 anywhere st. any city", "Website Development" / "website dev").
    A real paraphrase that fails all three is scored 0 -- see module
    docstring for the measured coverage/gap."""
    gt, pred = _normalize_str(ground_truth), _normalize_str(prediction)
    if gt is None and pred is None:
        return 1.0
    if gt is None or pred is None:
        return 0.0
    gt, pred = _fuzzy_normalize(gt), _fuzzy_normalize(pred)
    if gt == pred:
        return 1.0
    if _singularize(gt) == _singularize(pred):
        return 1.0
    if len(gt) >= 3 and len(pred) >= 3 and (gt in pred or pred in gt):
        return 1.0
    return 0.0


def score_fields(ground_truth: InvoiceFields, prediction: InvoiceFields) -> dict[str, float]:
    """Per-record score (0-1) for each field type. Missing keys mean the field
    type didn't apply to this record (e.g. no items in ground truth and none
    predicted -> items.* keys still present at 1.0 via the None/None rule,
    except when there simply are no line items to score at all)."""
    scores: dict[str, float] = {}

    scores["email"] = _score_exact(ground_truth.email, prediction.email)
    scores["clientName"] = _score_fuzzy_text(ground_truth.clientName, prediction.clientName)
    scores["address"] = _score_fuzzy_text(ground_truth.address, prediction.address)

    gt_items = ground_truth.items or []
    pred_items = prediction.items or []
    scores["items.count"] = 1.0 if len(gt_items) == len(pred_items) else 0.0

    if gt_items or pred_items:
        n = min(len(gt_items), len(pred_items))
        name_scores, qty_scores, price_scores = [], [], []
        for i in range(n):
            gt_item, pred_item = gt_items[i], pred_items[i]
            name_scores.append(_score_fuzzy_text(gt_item.name, pred_item.name))
            qty_scores.append(_score_numeric(gt_item.quantity, pred_item.quantity))
            price_scores.append(_score_numeric(gt_item.unitPrice, pred_item.unitPrice))
        # unmatched items beyond the shorter list are extra errors, not free
        # passes -- and always trivially scorable (one side has no
        # counterpart at all: an omitted or hallucinated whole item)
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
    """Field-accuracy output: for each field type, mean score, error rate (score < 1
    treated as an error) and n (records where the field type was applicable)."""
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
