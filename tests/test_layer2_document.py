import pytest

from evals.layer2_document import (
    CRITICAL_FIELDS,
    critical_error_rate,
    document_field_scores,
    resolution_rate,
    weighted_document_score,
)

WEIGHTS = {"clientName": 0.35, "email": 0.10, "address": 0.10, "items": 0.45}


def test_document_field_scores_collapses_items_subfields():
    record = {
        "email": 1.0,
        "clientName": 0.8,
        "items.name": 1.0,
        "items.quantity": 1.0,
        "items.unitPrice": 0.5,
        "items.count": 1.0,
    }
    doc_fields = document_field_scores(record)
    assert doc_fields["email"] == 1.0
    assert doc_fields["clientName"] == 0.8
    assert doc_fields["items"] == pytest.approx((1.0 + 1.0 + 0.5 + 1.0) / 4)
    assert "address" not in doc_fields  # not present in the record at all


def test_document_field_scores_omits_items_when_not_applicable():
    doc_fields = document_field_scores({"email": 1.0})
    assert "items" not in doc_fields


def test_weighted_document_score():
    record = {"clientName": 1.0, "email": 0.0, "address": 1.0, "items.name": 1.0, "items.quantity": 1.0, "items.unitPrice": 1.0, "items.count": 1.0}
    score = weighted_document_score(record, WEIGHTS)
    # clientName(1.0*.35) + email(0.0*.10) + address(1.0*.10) + items(1.0*.45), total weight 1.0
    assert score == pytest.approx(0.35 + 0.0 + 0.10 + 0.45)


def test_weighted_document_score_none_when_nothing_applicable():
    assert weighted_document_score({}, WEIGHTS) is None


def test_resolution_rate_requires_all_critical_fields_correct():
    assert CRITICAL_FIELDS == ("clientName", "items")
    resolved = {
        "clientName": 1.0,
        "items.name": 1.0,
        "items.quantity": 1.0,
        "items.unitPrice": 1.0,
        "items.count": 1.0,
    }
    wrong_items = {**resolved, "items.unitPrice": 0.0}
    wrong_client = {**resolved, "clientName": 0.5}

    rate = resolution_rate([resolved, wrong_items, wrong_client])
    assert rate == pytest.approx(1 / 3)


def test_critical_error_rate_is_complementary_to_resolution_rate():
    docs = [
        {"clientName": 1.0, "items.name": 1.0, "items.quantity": 1.0, "items.unitPrice": 1.0, "items.count": 1.0},
        {"clientName": 0.0, "items.name": 1.0, "items.quantity": 1.0, "items.unitPrice": 1.0, "items.count": 1.0},
    ]
    assert critical_error_rate(docs) == pytest.approx(1 - resolution_rate(docs))


def test_documents_missing_a_critical_field_score_are_excluded_not_guessed():
    # clientName wasn't scored at all in this document (e.g. semantic judge
    # skipped) -- must be excluded from the rate, not counted as a failure
    scored = {"clientName": 1.0, "items.name": 1.0, "items.quantity": 1.0, "items.unitPrice": 1.0, "items.count": 1.0}
    unscored_client_name = {"items.name": 1.0, "items.quantity": 1.0, "items.unitPrice": 1.0, "items.count": 1.0}

    rate = resolution_rate([scored, unscored_client_name])
    assert rate == 1.0  # only the fully-scored document counts


def test_resolution_rate_raises_when_no_document_is_fully_scored():
    with pytest.raises(ValueError):
        resolution_rate([{"email": 1.0}])
