import pytest

from evals.layer0_completeness_gate import (
    aggregate_missing_fields_scores,
    aggregate_sufficiency_scores,
    score_missing_fields,
    score_sufficiency,
)


def test_score_sufficiency_correct():
    result = score_sufficiency("partial", "partial")
    assert result["correct"] is True
    assert result["error_type"] is None


def test_score_sufficiency_missed_shortage():
    # said "complete" when it was actually "partial" -- predicted MORE
    # complete than reality, the dangerous direction
    result = score_sufficiency(ground_truth="partial", prediction="complete")
    assert result["correct"] is False
    assert result["error_type"] == "missed_shortage"


def test_score_sufficiency_asked_unnecessarily():
    # said "partial" when it was actually "complete" -- predicted LESS
    # complete than reality, just friction
    result = score_sufficiency(ground_truth="complete", prediction="partial")
    assert result["correct"] is False
    assert result["error_type"] == "asked_unnecessarily"


def test_score_sufficiency_none_to_complete_is_missed_shortage():
    # biggest possible miss in the dangerous direction
    result = score_sufficiency(ground_truth="none", prediction="complete")
    assert result["error_type"] == "missed_shortage"


def test_aggregate_sufficiency_scores():
    per_record = [
        score_sufficiency("complete", "complete"),
        score_sufficiency("partial", "partial"),
        score_sufficiency("partial", "complete"),  # missed_shortage
        score_sufficiency("complete", "partial"),  # asked_unnecessarily
        score_sufficiency("none", "none"),
    ]
    agg = aggregate_sufficiency_scores(per_record)

    assert agg["n"] == 5
    assert agg["accuracy"] == pytest.approx(3 / 5)
    assert agg["missed_shortage"] == 1
    assert agg["missed_shortage_rate"] == pytest.approx(1 / 5)
    assert agg["asked_unnecessarily"] == 1
    assert agg["asked_unnecessarily_rate"] == pytest.approx(1 / 5)
    assert agg["confusion_matrix"]["partial->complete"] == 1
    assert agg["confusion_matrix"]["complete->complete"] == 1


def test_aggregate_sufficiency_scores_handles_empty_input():
    assert aggregate_sufficiency_scores([]) == {"n": 0}


def test_score_missing_fields():
    result = score_missing_fields(ground_truth_missing={"clientName", "address"}, predicted_missing={"clientName", "items"})
    assert result["true_positives"] == ["clientName"]
    assert result["false_positives"] == ["items"]
    assert result["false_negatives"] == ["address"]


def test_score_missing_fields_perfect_match():
    result = score_missing_fields(ground_truth_missing={"address"}, predicted_missing={"address"})
    assert result["true_positives"] == ["address"]
    assert result["false_positives"] == []
    assert result["false_negatives"] == []


def test_aggregate_missing_fields_scores():
    per_record = [
        score_missing_fields({"clientName", "address"}, {"clientName", "items"}),  # tp=1, fp=1, fn=1
        score_missing_fields({"address"}, {"address"}),  # tp=1
        score_missing_fields(set(), set()),  # nothing missing, nothing predicted
    ]
    agg = aggregate_missing_fields_scores(per_record)

    assert agg["tp"] == 2
    assert agg["fp"] == 1
    assert agg["fn"] == 1
    assert agg["precision"] == pytest.approx(2 / 3)
    assert agg["recall"] == pytest.approx(2 / 3)
    assert agg["f1"] == pytest.approx(2 / 3)


def test_aggregate_missing_fields_scores_handles_no_predictions():
    agg = aggregate_missing_fields_scores([score_missing_fields(set(), set())])
    assert agg["tp"] == 0
    assert agg["precision"] is None
    assert agg["recall"] is None
    assert agg["f1"] is None
