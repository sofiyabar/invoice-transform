"""Traceability test: every $ figure in business_dict must trace back to a
metrics_dict key or a config value — never a hardcoded number. Keep this
test even under time pressure (see project brief, non-negotiable)."""

import pytest


@pytest.mark.skip(reason="TODO: evals.business_layer not implemented yet")
def test_every_dollar_figure_traces_to_metrics_dict_or_config():
    pass


@pytest.mark.skip(reason="TODO: evals.business_layer not implemented yet")
def test_business_layer_does_not_recompute_eval_metrics():
    pass
