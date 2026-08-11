"""Assign segment/doc_type labels to records that don't already carry them
(e.g. real-world sources like Enron, where labels aren't given for free).

TODO: implement heuristic or LLM-based labeling per config/segments.yaml.
"""

from data.schema import InvoiceRecord, Segment


def label_segment(record: InvoiceRecord) -> Segment:
    raise NotImplementedError("TODO: implement segment labeling")
