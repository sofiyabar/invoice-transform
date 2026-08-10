from data.schema import InvoiceFields, InvoiceItem
from generator.completeness_gate import check_sufficiency, missing_critical_fields


def _item():
    return InvoiceItem(name="Widget", quantity=1, unitPrice=1.0)


def test_complete_when_all_critical_fields_present():
    fields = InvoiceFields(clientName="Acme", address="123 Main St", items=[_item()])
    assert missing_critical_fields(fields) == set()
    assert check_sufficiency(fields) == "complete"


def test_complete_ignores_missing_email():
    # email is deliberately not critical -- see CHANGELOG.md 2026-08-10
    fields = InvoiceFields(clientName="Acme", address="123 Main St", items=[_item()], email=None)
    assert check_sufficiency(fields) == "complete"


def test_partial_when_some_critical_fields_missing():
    fields = InvoiceFields(clientName="Acme", address=None, items=[_item()])
    assert missing_critical_fields(fields) == {"address"}
    assert check_sufficiency(fields) == "partial"


def test_partial_when_two_of_three_critical_fields_missing():
    fields = InvoiceFields(clientName=None, address=None, items=[_item()])
    assert missing_critical_fields(fields) == {"clientName", "address"}
    assert check_sufficiency(fields) == "partial"


def test_none_when_all_critical_fields_missing():
    fields = InvoiceFields(clientName=None, address=None, items=None)
    assert missing_critical_fields(fields) == {"clientName", "address", "items"}
    assert check_sufficiency(fields) == "none"


def test_empty_string_and_empty_list_count_as_missing():
    fields = InvoiceFields(clientName="", address="   ", items=[])
    assert missing_critical_fields(fields) == {"clientName", "address", "items"}
    assert check_sufficiency(fields) == "none"
