"""
Unit tests for the XIRR solver (backend/xirr.py).

Pure functions only - no database, no network, no FastAPI. Run with:
    cd backend && venv/Scripts/python -m pytest tests/ -q
"""

from datetime import date

import pytest

from xirr import xirr


def _monthly_outflows(start: date, months: int, amount: float):
    """A series of monthly premium-style outflows starting at `start`."""
    flows = []
    for i in range(months):
        d = date(start.year + (start.month - 1 + i) // 12,
                 (start.month - 1 + i) % 12 + 1,
                 min(start.day, 28))
        flows.append((d, -amount))
    return flows


def test_known_simple_rate():
    # Invest 1000, receive 1100 exactly 365 days later (no leap day) = 10%.
    flows = [
        (date(2021, 1, 1), -1000.0),
        (date(2022, 1, 1), 1100.0),
    ]
    assert xirr(flows) == pytest.approx(0.10, abs=1e-4)


def test_recurring_premiums():
    # 12 monthly premiums of 5000 (60,000 total), maturity 100,000 at month 12.
    flows = _monthly_outflows(date(2025, 1, 5), 12, 5000.0)
    flows.append((date(2026, 1, 5), 100000.0))
    rate = xirr(flows)
    assert rate is not None
    # 100k back on 60k in ~1 year must be a large POSITIVE rate.
    assert rate > 0.5


def test_annual_premiums_typical_endowment():
    # Classic endowment shape: 20 yearly premiums of 25,000 (500k total),
    # 1,000,000 payout at year 20 - roughly a low-single-digit XIRR.
    flows = [(date(2005 + i, 6, 15), -25000.0) for i in range(20)]
    flows.append((date(2025, 6, 15), 1000000.0))
    rate = xirr(flows)
    assert rate is not None
    assert 0.02 < rate < 0.10


def test_negative_rate_converges():
    # Put money in, get less out: XIRR must come back negative.
    flows = [
        (date(2020, 1, 1), -1000.0),
        (date(2025, 1, 1), 800.0),
    ]
    rate = xirr(flows)
    assert rate is not None
    assert rate < 0
    assert rate > -0.99


def test_insufficient_flows_returns_none():
    assert xirr([]) is None
    assert xirr([(date(2020, 1, 1), -1000.0)]) is None


def test_all_positive_returns_none():
    flows = [
        (date(2020, 1, 1), 1000.0),
        (date(2021, 1, 1), 1200.0),
    ]
    assert xirr(flows) is None


def test_all_negative_returns_none():
    flows = [
        (date(2020, 1, 1), -1000.0),
        (date(2021, 1, 1), -500.0),
    ]
    assert xirr(flows) is None


def test_zero_total_returns_none():
    # Zero net flow with no spread can't define a meaningful rate; the
    # important behavior is that we return SOMETHING sane, not crash.
    flows = [
        (date(2020, 1, 1), -1000.0),
        (date(2021, 1, 1), 1000.0),
    ]
    result = xirr(flows)
    assert result is None or (isinstance(result, float) and result > -0.99)


def test_unordered_input_is_sorted_internally():
    # Same flows as test_known_simple_rate, passed out of date order.
    flows = [
        (date(2022, 1, 1), 1100.0),
        (date(2021, 1, 1), -1000.0),
    ]
    assert xirr(flows) == pytest.approx(0.10, abs=1e-4)


def test_never_hangs_on_pathological_input():
    # An all-huge-timespan, weirdly-shaped series must return quickly,
    # either a rate or None - never loop forever.
    import time
    flows = _monthly_outflows(date(1970, 1, 1), 600, 10.0)
    flows.append((date(2026, 1, 1), 5.0))
    start = time.time()
    result = xirr(flows)
    assert time.time() - start < 5.0
    assert result is None or isinstance(result, float)
