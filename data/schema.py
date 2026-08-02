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


class InvoiceFields(BaseModel):
    """Ground-truth / predicted invoice fields (Layer 1 scoring target)."""

    company: str | None = None
    date: str | None = None
    address: str | None = None
    total: str | None = None
    invoice_number: str | None = None
    currency: str | None = None
    line_items: list[str] | None = None


class InvoiceRecord(BaseModel):
    """One evaluation example: input text + ground truth + metadata."""

    id: str
    raw_text: str
    ground_truth: InvoiceFields
    segment: Segment
    doc_type: DocType
    source: str
