"""Layer 0, Step 2 — Completeness gate scoring: how good is
generator.completeness_gate's data-sufficiency decision compared to ground
truth?

Ground truth comes from data.schema.SufficiencyGateRecord (loaded via
data.loaders.load_sufficiency_gate_dataset()) -- only rows where
is_invoice_request is True, see CHANGELOG.md 2026-08-10 for how
sufficiency_label and missing_critical_fields were derived.

This module only scores decisions already made -- generator/completeness_gate.py
does the actual classification, exactly the same split as Step 1
(evals/layer0_intent_gate.py + generator/intent_gate.py).

Per project_brief.md, Step 2 needs two separate metric families:

  score_sufficiency() / aggregate_sufficiency_scores() -- multi-class
    accuracy across {none, partial, complete}, plus the two error directions
    kept apart (never blended into one number, same reasoning as Step 1's
    FP/FN split):
      - "missed_shortage": predicted MORE complete than reality (e.g. said
        "complete" when it was "partial") -- the dangerous direction, risks
        sending/building an invoice that's actually missing something.
      - "asked_unnecessarily": predicted LESS complete than reality -- just
        friction, an unneeded re-prompt.

  score_missing_fields() / aggregate_missing_fields_scores() -- precision/
    recall on WHICH critical fields were correctly flagged missing. Not an
    LLM-judge task the way project_brief.md frames it in general, because
    here both ground truth and prediction are derived the same deterministic
    way from InvoiceFields (see generator/completeness_gate.py) -- there's no
    fuzzy text judgment involved.
"""

_LEVEL_ORDER = {"none": 0, "partial": 1, "complete": 2}


def score_sufficiency(ground_truth: str, prediction: str) -> dict:
    """Per-record result for one (ground_truth, prediction) pair of
    sufficiency labels ("none"/"partial"/"complete")."""
    correct = ground_truth == prediction
    error_type = None
    if not correct:
        if _LEVEL_ORDER[prediction] > _LEVEL_ORDER[ground_truth]:
            error_type = "missed_shortage"
        else:
            error_type = "asked_unnecessarily"
    return {
        "ground_truth": ground_truth,
        "prediction": prediction,
        "correct": correct,
        "error_type": error_type,
    }


def aggregate_sufficiency_scores(per_record: list[dict]) -> dict:
    """Layer 0 Step 2 sufficiency-label output: accuracy, the two error
    directions kept apart, and a full confusion matrix for detail."""
    n = len(per_record)
    if n == 0:
        return {"n": 0}

    correct = sum(1 for r in per_record if r["correct"])
    missed_shortage = sum(1 for r in per_record if r["error_type"] == "missed_shortage")
    asked_unnecessarily = sum(1 for r in per_record if r["error_type"] == "asked_unnecessarily")

    confusion: dict[str, int] = {}
    for r in per_record:
        key = f"{r['ground_truth']}->{r['prediction']}"
        confusion[key] = confusion.get(key, 0) + 1

    return {
        "n": n,
        "accuracy": correct / n,
        "missed_shortage": missed_shortage,
        "missed_shortage_rate": missed_shortage / n,
        "asked_unnecessarily": asked_unnecessarily,
        "asked_unnecessarily_rate": asked_unnecessarily / n,
        "confusion_matrix": confusion,
    }


def score_missing_fields(ground_truth_missing: set[str], predicted_missing: set[str]) -> dict:
    """Per-record set comparison: which critical fields did we correctly
    flag as missing, miss, or wrongly flag."""
    ground_truth_missing = set(ground_truth_missing)
    predicted_missing = set(predicted_missing)
    return {
        "true_positives": sorted(ground_truth_missing & predicted_missing),
        "false_positives": sorted(predicted_missing - ground_truth_missing),
        "false_negatives": sorted(ground_truth_missing - predicted_missing),
    }


def aggregate_missing_fields_scores(per_record: list[dict]) -> dict:
    """Precision/recall on identifying which specific critical fields are
    missing, pooled across all records (micro-averaged, not per-record
    macro-averaged -- records where nothing is missing contribute zero to
    every count rather than skewing the average with an undefined 0/0)."""
    tp = sum(len(r["true_positives"]) for r in per_record)
    fp = sum(len(r["false_positives"]) for r in per_record)
    fn = sum(len(r["false_negatives"]) for r in per_record)

    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = (2 * precision * recall / (precision + recall)) if precision and recall and (precision + recall) else None

    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }
