import pytest

from evals.document_accuracy import (
    CRITICAL_FIELDS,
    by_group,
    critical_error_rate,
    document_field_scores,
    document_level_summary,
    resolution_rate,
)


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


CORRECT = {"email": 1.0, "clientName": 1.0, "items.name": 1.0, "items.quantity": 1.0, "items.unitPrice": 1.0, "items.count": 1.0}
WRONG_CLIENT = {**CORRECT, "clientName": 0.0}


def test_document_level_summary():
    per_record = [
        {"id": "a", "segment": "clean", "doc_type": "email", "parse_ok": True, "scores": CORRECT},
        {"id": "b", "segment": "noisy", "doc_type": "chat", "parse_ok": True, "scores": WRONG_CLIENT},
        {"id": "c", "segment": "noisy", "doc_type": "chat", "parse_ok": False, "scores": {}},
    ]
    summary = document_level_summary(per_record)
    assert summary["resolution_rate"] == 0.5
    assert summary["critical_error_rate"] == 0.5
    assert summary["n_resolution_scored"] == 2
    assert summary["critical_fields"] == ["clientName", "items"]
    assert set(summary["by_segment"]) == {"clean", "noisy"}
    assert set(summary["by_doc_type"]) == {"email", "chat"}


def test_document_level_summary_returns_none_when_nothing_scored():
    assert document_level_summary([]) is None


def test_by_group_slices_error_rate_and_resolution_rate_per_segment():
    per_record = [
        {"id": "a", "segment": "clean", "doc_type": "email", "parse_ok": True, "scores": CORRECT},
        {"id": "b", "segment": "clean", "doc_type": "chat", "parse_ok": True, "scores": CORRECT},
        {"id": "c", "segment": "noisy", "doc_type": "email", "parse_ok": True, "scores": WRONG_CLIENT},
        {"id": "d", "segment": "noisy", "doc_type": "chat", "parse_ok": True, "scores": WRONG_CLIENT},
    ]

    by_segment = by_group(per_record, "segment")
    assert set(by_segment) == {"clean", "noisy"}
    assert by_segment["clean"]["n_records"] == 2
    assert by_segment["clean"]["overall_error_rate"] == 0.0
    assert by_segment["clean"]["resolution_rate"] == 1.0
    assert by_segment["noisy"]["n_records"] == 2
    assert by_segment["noisy"]["overall_error_rate"] > 0.0
    assert by_segment["noisy"]["resolution_rate"] == 0.0  # clientName wrong -> critical field fails


def test_by_group_excludes_unscored_records():
    per_record = [
        {"id": "a", "segment": "clean", "doc_type": "email", "parse_ok": True, "scores": CORRECT},
        {"id": "b", "segment": "clean", "doc_type": "email", "parse_ok": False, "scores": {}},
    ]
    by_segment = by_group(per_record, "segment")
    assert by_segment["clean"]["n_records"] == 1


def test_by_group_empty_input_returns_empty_dict():
    assert by_group([], "segment") == {}
