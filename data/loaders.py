"""Load external datasets into the unified InvoiceRecord schema.

TODO: implement loaders per source (SROIE, Enron, HF invoice datasets, ...),
each returning list[InvoiceRecord]. Kept separate per source so a broken/
skipped source doesn't block the others.
"""

from data.schema import InvoiceRecord


def load_sroie() -> list[InvoiceRecord]:
    raise NotImplementedError("TODO: fix schema mismatch, see notebooks/datasets_searching.ipynb")


def load_enron_filtered() -> list[InvoiceRecord]:
    raise NotImplementedError("TODO: filter Enron email dataset for invoice/payment context")
