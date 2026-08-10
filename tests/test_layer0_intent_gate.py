import pytest

from evals.layer0_intent_gate import aggregate_intent_scores, score_intent


def test_score_intent_true_positive():
    result = score_intent(ground_truth=True, prediction=True)
    assert result == {"ground_truth": True, "prediction": True, "correct": True, "error_type": None}


def test_score_intent_true_negative():
    result = score_intent(ground_truth=False, prediction=False)
    assert result["correct"] is True
    assert result["error_type"] is None


def test_score_intent_false_positive():
    # ground truth says "not an invoice request", gate said "yes" -- the
    # expensive error (hallucinated invoice)
    result = score_intent(ground_truth=False, prediction=True)
    assert result["correct"] is False
    assert result["error_type"] == "false_positive"


def test_score_intent_false_negative():
    # ground truth says "is an invoice request", gate said "no" -- the cheap
    # error (just friction/re-prompt)
    result = score_intent(ground_truth=True, prediction=False)
    assert result["correct"] is False
    assert result["error_type"] == "false_negative"


def test_aggregate_intent_scores_rates_and_accuracy():
    per_record = [
        score_intent(True, True),    # TP
        score_intent(True, True),    # TP
        score_intent(True, False),   # FN
        score_intent(False, False),  # TN
        score_intent(False, True),   # FP
    ]
    agg = aggregate_intent_scores(per_record)

    assert agg["n"] == 5
    assert agg["n_positive"] == 3
    assert agg["n_negative"] == 2
    assert agg["tp"] == 2
    assert agg["tn"] == 1
    assert agg["fp"] == 1
    assert agg["fn"] == 1
    assert agg["accuracy"] == pytest.approx(3 / 5)
    assert agg["fp_rate"] == pytest.approx(1 / 2)  # 1 FP out of 2 actual negatives
    assert agg["fn_rate"] == pytest.approx(1 / 3)  # 1 FN out of 3 actual positives


def test_aggregate_intent_scores_handles_empty_input():
    assert aggregate_intent_scores([]) == {"n": 0}


def test_aggregate_intent_scores_handles_single_class_ground_truth():
    # all-positive ground truth -> no actual negatives -> fp_rate undefined,
    # not a division-by-zero crash or a misleading 0.0
    per_record = [score_intent(True, True), score_intent(True, False)]
    agg = aggregate_intent_scores(per_record)
    assert agg["n_negative"] == 0
    assert agg["fp_rate"] is None
    assert agg["fn_rate"] == pytest.approx(1 / 2)
