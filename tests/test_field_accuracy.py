import pytest

from data.schema import InvoiceFields, InvoiceItem
from evals.field_accuracy import _score_fuzzy_text, aggregate_scores, score_fields


def test_exact_match_strict_fields():
    gt = InvoiceFields(email="a@example.com")
    match = InvoiceFields(email="a@example.com")
    mismatch = InvoiceFields(email="b@example.com")
    missing = InvoiceFields(email=None)
    both_missing = InvoiceFields(email=None)

    assert score_fields(gt, match)["email"] == 1.0
    assert score_fields(gt, mismatch)["email"] == 0.0
    assert score_fields(gt, missing)["email"] == 0.0  # omission
    assert score_fields(InvoiceFields(email=None), InvoiceFields(email="a@example.com"))["email"] == 0.0  # hallucination
    assert score_fields(InvoiceFields(email=None), both_missing)["email"] == 1.0


def test_email_exact_match_is_punctuation_sensitive():
    """Unlike the fuzzy text fields, email must NOT strip periods --
    john.doe@x.com and johndoe@x.com are different addresses."""
    gt = InvoiceFields(email="john.doe@x.com")
    pred = InvoiceFields(email="johndoe@x.com")
    assert score_fields(gt, pred)["email"] == 0.0


def test_tolerance_match_numeric_fields():
    gt = InvoiceFields(items=[InvoiceItem(name="Widget", quantity=2, unitPrice=10.00)])
    close_enough = InvoiceFields(items=[InvoiceItem(name="Widget", quantity=2, unitPrice=10.005)])
    off = InvoiceFields(items=[InvoiceItem(name="Widget", quantity=2, unitPrice=10.5)])

    scores_close = score_fields(gt, close_enough)
    assert scores_close["items.unitPrice"] == 1.0
    assert scores_close["items.quantity"] == 1.0

    scores_off = score_fields(gt, off)
    assert scores_off["items.unitPrice"] == 0.0


def test_items_count_mismatch_is_an_error_not_silently_truncated():
    gt = InvoiceFields(items=[InvoiceItem(name="A", quantity=1, unitPrice=1), InvoiceItem(name="B", quantity=1, unitPrice=1)])
    pred = InvoiceFields(items=[InvoiceItem(name="A", quantity=1, unitPrice=1)])

    scores = score_fields(gt, pred)
    assert scores["items.count"] == 0.0
    # the unmatched second item counts as an error in every item.* field, not a free pass
    assert scores["items.quantity"] == 0.5
    assert scores["items.unitPrice"] == 0.5


def test_fuzzy_text_trivial_cases():
    assert score_fields(InvoiceFields(clientName=None), InvoiceFields(clientName=None))["clientName"] == 1.0
    assert score_fields(InvoiceFields(clientName="X"), InvoiceFields(clientName=None))["clientName"] == 0.0  # omission
    assert score_fields(InvoiceFields(clientName=None), InvoiceFields(clientName="X"))["clientName"] == 0.0  # hallucination


@pytest.mark.parametrize(
    "gt_val,pred_val,expected",
    [
        # clientName-shaped cases (real mismatches from generator_predictions.jsonl,
        # see conversation record "clientName и address тоже почини так же")
        ("Wardiere Inc.", "Wardiere Inc", 1.0),  # trailing punctuation
        ("Green Gardens", "Bill Green Gardens", 1.0),  # containment
        ("Hans Casper", "Hans", 1.0),  # containment -- known gap: forgives a dropped last name
        ("Widget", "Gadget", 0.0),  # genuinely different
        # address-shaped cases
        ("123 Anywhere St., Any City, ST", "123 Anywhere St., Any City, ST.", 1.0),  # trailing period
        ("123 Anywhere St.,  Any City", "123 anywhere st, any city", 1.0),  # double space + case
        # items.name-shaped cases
        ("Revision", "Revisions", 1.0),  # plural
        ("Website Development", "website dev", 1.0),  # substring
        ("Air Duct Cleaning", "duct cleanings", 0.0),  # real paraphrase, not caught -- known gap
    ],
)
def test_score_fuzzy_text_matching_rules(gt_val, pred_val, expected):
    assert _score_fuzzy_text(gt_val, pred_val) == expected


def test_items_name_scored_when_prediction_has_no_items_at_all():
    """n==0 (nothing to match by index): every ground-truth item name is
    simply absent from the prediction, a deterministic 0."""
    gt = InvoiceFields(items=[InvoiceItem(name="Widget", quantity=1, unitPrice=1), InvoiceItem(name="Gadget", quantity=1, unitPrice=1)])
    pred = InvoiceFields(items=[])

    scores = score_fields(gt, pred)
    assert scores["items.name"] == 0.0


def test_aggregate_scores_error_rate_and_mean():
    per_record = [
        {"email": 1.0, "clientName": 1.0},
        {"email": 0.0, "clientName": 0.8},
        {"email": 1.0, "clientName": 0.4},
    ]
    agg = aggregate_scores(per_record)
    assert agg["email"]["n"] == 3
    assert agg["email"]["error_rate"] == pytest.approx(1 / 3)
    assert agg["email"]["mean_score"] == pytest.approx(2 / 3)
    # fuzzy-text scores < 1.0 count as errors even though they're not 0
    assert agg["clientName"]["error_rate"] == pytest.approx(2 / 3)
    assert agg["clientName"]["mean_score"] == pytest.approx((1.0 + 0.8 + 0.4) / 3)


def test_aggregate_scores_skips_field_types_never_applicable():
    agg = aggregate_scores([{"email": 1.0}, {"email": 1.0}])
    assert "clientName" not in agg
    assert agg["email"]["n"] == 2
