"""Layer 0, Step 1 — Intent gate scoring: how good is generator.intent_gate's
is-invoice-intent decision compared to ground truth?

Ground truth comes from data.schema.IntentGateRecord.is_invoice_request
(loaded via data.loaders.load_intent_gate_dataset()) -- every row of the
dataset, invoice and non-invoice alike. The actual classification call lives
in generator/intent_gate.py, not here -- this module only scores decisions
already made, exactly like evals/layer1_field.py only scores predictions
already generated (the generator call itself happens in evals/runner.py).

Two-function API, mirrors evals/layer1_field.py (score_fields + aggregate_scores):
  score_intent()             -- per-record correct/error_type against ground
                                truth.
  aggregate_intent_scores()  -- rolls per-record results up into the actual
                                Layer 0 Step 1 output: accuracy + FP rate +
                                FN rate.

FP and FN are reported separately, never merged into F1: per project_brief.md
they cost differently (FP = a hallucinated invoice sent to a client -- an
expensive, trust-damaging error; FN = the tool just asks the user to
re-prompt -- cheap friction), and Layer 6's business-impact formulas need
them apart, not blended into one number.

Step 2 (data sufficiency: no data / partial / complete) is not implemented
here yet -- out of scope for this pass.
"""


def score_intent(ground_truth: bool, prediction: bool) -> dict:
    """Per-record result for one (ground_truth, prediction) pair.

    error_type distinguishes the two failure modes that Layer 6 prices
    differently -- see module docstring."""
    correct = ground_truth == prediction
    error_type = None
    if not correct:
        error_type = "false_positive" if prediction else "false_negative"
    return {
        "ground_truth": ground_truth,
        "prediction": prediction,
        "correct": correct,
        "error_type": error_type,
    }


def aggregate_intent_scores(per_record: list[dict]) -> dict:
    """Layer 0 Step 1 output: accuracy, plus FP rate and FN rate kept apart.

    fp_rate is computed over actual negatives (n_negative), fn_rate over
    actual positives (n_positive) -- the standard definitions, not "errors
    over all records", so each rate answers "given the true class, how often
    did the gate get it wrong" rather than being diluted by class balance.
    """
    n = len(per_record)
    if n == 0:
        return {"n": 0}

    n_positive = sum(1 for r in per_record if r["ground_truth"])
    n_negative = n - n_positive
    tp = sum(1 for r in per_record if r["correct"] and r["ground_truth"])
    tn = sum(1 for r in per_record if r["correct"] and not r["ground_truth"])
    fp = sum(1 for r in per_record if r["error_type"] == "false_positive")
    fn = sum(1 for r in per_record if r["error_type"] == "false_negative")

    return {
        "n": n,
        "n_positive": n_positive,
        "n_negative": n_negative,
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "accuracy": (tp + tn) / n,
        "fp_rate": fp / n_negative if n_negative else None,
        "fn_rate": fn / n_positive if n_positive else None,
    }
