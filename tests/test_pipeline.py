from generator import pipeline
from generator.pipeline import run_pipeline


def test_non_invoice_text_stops_at_intent_gate(monkeypatch):
    monkeypatch.setattr(pipeline, "is_invoice_request", lambda text: False)
    monkeypatch.setattr(
        pipeline,
        "parse_invoice_from_text",
        lambda text: (_ for _ in ()).throw(AssertionError("generator should not be called for non-invoice text")),
    )

    result = run_pipeline("do you know if the office is open Saturday?")

    assert result["is_invoice_request"] is False
    assert result["fields"] is None
    assert result["sufficiency"] is None
    assert result["parse_error"] is None


def test_complete_invoice_flows_through_all_three_stages(monkeypatch):
    monkeypatch.setattr(pipeline, "is_invoice_request", lambda text: True)
    monkeypatch.setattr(
        pipeline,
        "parse_invoice_from_text",
        lambda text: {
            "clientName": "Acme",
            "email": "",
            "address": "123 Main St",
            "items": [{"name": "Widget", "quantity": "2", "unitPrice": "10.0"}],
        },
    )

    result = run_pipeline("some invoice request text")

    assert result["is_invoice_request"] is True
    assert result["parse_error"] is None
    assert result["fields"].clientName == "Acme"
    assert result["fields"].email is None  # "" normalized to None
    assert result["fields"].items[0].quantity == 2.0  # coerced to float
    assert result["sufficiency"] == "complete"
    assert result["missing_critical_fields"] == []


def test_partial_invoice_reports_missing_critical_fields(monkeypatch):
    monkeypatch.setattr(pipeline, "is_invoice_request", lambda text: True)
    monkeypatch.setattr(
        pipeline,
        "parse_invoice_from_text",
        lambda text: {"clientName": "", "email": "a@b.com", "address": "123 Main St", "items": []},
    )

    result = run_pipeline("some invoice request text")

    assert result["sufficiency"] == "partial"
    assert result["missing_critical_fields"] == ["clientName", "items"]


def test_parse_failure_stops_before_completeness_check(monkeypatch):
    monkeypatch.setattr(pipeline, "is_invoice_request", lambda text: True)
    monkeypatch.setattr(
        pipeline,
        "parse_invoice_from_text",
        lambda text: (_ for _ in ()).throw(ValueError("bad json")),
    )

    result = run_pipeline("some invoice request text")

    assert result["is_invoice_request"] is True
    assert result["parse_error"] == "ValueError: bad json"
    assert result["fields"] is None
    assert result["sufficiency"] is None
