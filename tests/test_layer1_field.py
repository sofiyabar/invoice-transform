import pytest

from data.schema import InvoiceFields, InvoiceItem
from evals import layer1_field
from evals.layer1_field import aggregate_scores, score_fields


@pytest.fixture(autouse=True)
def stub_judge(monkeypatch):
    """clientName/address still go through the judge -- stub it so
    non-judge-focused tests don't make real Anthropic calls. items.name no
    longer calls the judge at all (see _score_item_name), so this only
    matters for clientName/address tests now."""
    monkeypatch.setattr(layer1_field, "judge_field_match", lambda field, gt, pred: 1.0 if gt == pred else 0.0)


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


def test_semantic_judge_free_text_fields(monkeypatch):
    monkeypatch.setattr(layer1_field, "judge_field_match", lambda field, gt, pred: 0.8)

    gt = InvoiceFields(clientName="Helena Paquet")
    pred = InvoiceFields(clientName="H. Paquet")
    scores = score_fields(gt, pred)
    assert scores["clientName"] == 0.8

    # None/None and mismatched-None short-circuit without calling the judge
    monkeypatch.setattr(
        layer1_field,
        "judge_field_match",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("judge should not be called")),
    )
    assert score_fields(InvoiceFields(clientName=None), InvoiceFields(clientName=None))["clientName"] == 1.0
    assert score_fields(InvoiceFields(clientName="X"), InvoiceFields(clientName=None))["clientName"] == 0.0


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
    # semantic scores < 1.0 count as errors even though they're not 0
    assert agg["clientName"]["error_rate"] == pytest.approx(2 / 3)
    assert agg["clientName"]["mean_score"] == pytest.approx((1.0 + 0.8 + 0.4) / 3)


def test_aggregate_scores_skips_field_types_never_applicable():
    agg = aggregate_scores([{"email": 1.0}, {"email": 1.0}])
    assert "clientName" not in agg
    assert agg["email"]["n"] == 2


def test_use_semantic_judge_false_skips_judge_but_scores_trivial_cases(monkeypatch):
    monkeypatch.setattr(
        layer1_field,
        "judge_field_match",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("judge should not be called when disabled")),
    )

    # non-trivial semantic comparison: omitted entirely, not guessed as an error
    scores = score_fields(
        InvoiceFields(clientName="Helena Paquet"),
        InvoiceFields(clientName="H. Paquet"),
        use_semantic_judge=False,
    )
    assert "clientName" not in scores
    # exact/numeric fields are unaffected
    assert "email" in scores

    # trivial cases still resolve without the judge
    both_none = score_fields(InvoiceFields(clientName=None), InvoiceFields(clientName=None), use_semantic_judge=False)
    assert both_none["clientName"] == 1.0
    one_missing = score_fields(InvoiceFields(clientName="X"), InvoiceFields(clientName=None), use_semantic_judge=False)
    assert one_missing["clientName"] == 0.0


def test_items_name_is_judge_free(monkeypatch):
    """items.name must never call the judge -- see module docstring
    (conversation record "парситься они должны простым методом а не
    судьей"). Assert this holds even with use_semantic_judge=True."""
    monkeypatch.setattr(
        layer1_field,
        "judge_field_match",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("items.name must not call the judge")),
    )
    gt = InvoiceFields(items=[InvoiceItem(name="Website Development", quantity=1, unitPrice=1)])
    pred = InvoiceFields(items=[InvoiceItem(name="website dev", quantity=1, unitPrice=1)])

    scores = score_fields(gt, pred, use_semantic_judge=True)
    assert scores["items.name"] == 1.0  # substring match, no judge needed


@pytest.mark.parametrize(
    "gt_name,pred_name,expected",
    [
        ("Widget", "Widget", 1.0),  # exact
        ("Widget", "widget", 1.0),  # case-insensitive
        ("Revision", "Revisions", 1.0),  # plural
        ("Revisions", "Revision", 1.0),  # singular
        ("Website Development", "website dev", 1.0),  # substring
        ("Air Duct Cleaning", "duct cleanings", 0.0),  # real paraphrase, not caught -- known gap
        ("Widget", "Gadget", 0.0),  # genuinely different
    ],
)
def test_score_item_name_matching_rules(gt_name, pred_name, expected):
    assert layer1_field._score_item_name(gt_name, pred_name) == expected


def test_items_name_scored_when_prediction_has_no_items_at_all():
    """n==0 (nothing to match by index): every ground-truth item name is
    simply absent from the prediction, a deterministic 0."""
    gt = InvoiceFields(items=[InvoiceItem(name="Widget", quantity=1, unitPrice=1), InvoiceItem(name="Gadget", quantity=1, unitPrice=1)])
    pred = InvoiceFields(items=[])

    scores = score_fields(gt, pred, use_semantic_judge=False)
    assert scores["items.name"] == 0.0
