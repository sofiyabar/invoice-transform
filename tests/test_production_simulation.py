import pytest

from evals.production_simulation import (
    batch_trend,
    csat_proxy_stub,
    latency_estimate,
    latency_stats,
)


def test_latency_stats_computes_p50_p95_mean():
    stats = latency_stats([1000, 1500, 2000, 2500, 3000, 3500, 4000, 5000, 6000, 10000])
    assert stats["n"] == 10
    assert stats["mean"] == pytest.approx(3850.0)
    assert stats["p50"] <= stats["p95"]


def test_latency_stats_raises_on_empty_input():
    with pytest.raises(ValueError):
        latency_stats([])


def test_latency_estimate_is_explicitly_labeled():
    est = latency_estimate()
    assert est["is_estimate"] is True
    assert est["p50"] < est["p95"]


def test_csat_proxy_stub_is_explicitly_labeled():
    result = csat_proxy_stub(critical_error_rate=0.123, delta=0.05)
    assert result["is_stub"] is True
    assert result["thumbs_down_rate"] == pytest.approx(0.173)
    assert result["thumbs_up_rate"] == pytest.approx(0.827)


def test_csat_proxy_stub_caps_at_100_percent():
    result = csat_proxy_stub(critical_error_rate=0.98, delta=0.05)
    assert result["thumbs_down_rate"] == 1.0
    assert result["thumbs_up_rate"] == 0.0


def test_batch_trend_not_implemented():
    with pytest.raises(NotImplementedError):
        batch_trend([])
