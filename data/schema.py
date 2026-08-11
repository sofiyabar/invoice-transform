"""Shared data contract between generator/, data/ loaders, and evals/.

Every dataset loader and the synthetic generator must produce records
matching InvoiceRecord; every generator.base_generator.generate() call
must produce a dict scoreable against InvoiceFields.
"""

from enum import Enum

from pydantic import BaseModel


class Segment(str, Enum):
    CLEAN = "clean"
    NOISY = "noisy"
    EDGE_CASE = "edge_case"


class DocType(str, Enum):
    EMAIL = "email"
    CHAT = "chat"
    RECEIPT_OCR = "receipt_ocr"


class InvoiceItem(BaseModel):
    """One line item within an invoice's items list."""

    name: str
    quantity: float
    unitPrice: float


class InvoiceFields(BaseModel):
    """Ground-truth / predicted invoice fields (field-accuracy scoring target)."""

    clientName: str | None = None
    email: str | None = None
    address: str | None = None
    items: list[InvoiceItem] | None = None


class InvoiceRecord(BaseModel):
    """One evaluation example: input text + ground truth + metadata."""

    id: str
    raw_text: str
    ground_truth: InvoiceFields
    segment: Segment
    doc_type: DocType
    source: str


class IntentGateRecord(BaseModel):
    """One evaluation example for Intake Gate, Step 1 (is-invoice-intent
    classifier). Covers every row of the dataset, invoice and non-invoice
    alike -- distinct from InvoiceRecord, which requires real ground_truth
    fields that non-invoice rows don't have."""

    id: str
    raw_text: str
    is_invoice_request: bool
    source: str


# Fields whose absence actually blocks building a usable invoice. email is
# deliberately excluded -- an invoice without it is still usable. See
# CHANGELOG.md 2026-08-10 for how this was chosen and validated against the
# dataset (sufficiency_label was recomputed against this exact set).
CRITICAL_FIELDS = ("clientName", "items", "address")


class SufficiencyGateRecord(BaseModel):
    """One evaluation example for Intake Gate, Step 2 (data sufficiency check).
    Only applies to rows where is_invoice_request is True -- sufficiency
    doesn't mean anything for non-invoice text."""

    id: str
    raw_text: str
    sufficiency_label: str  # "none" | "partial" | "complete"
    missing_critical_fields: list[str]  # ground truth, subset of CRITICAL_FIELDS
    source: str
