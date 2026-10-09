"""
XIRR solver - the annualized rate of return for a series of dated cash flows.

Pure arithmetic with no FastAPI/DB/requests dependencies, so it can be unit
tested in isolation (see tests/test_xirr.py). Same convention as Excel's
XIRR function, which also uses Newton-Raphson because there is no closed-form
solution:

    0 = sum_i  CF_i / (1 + r)^(days(i) / 365)

- negative cash flow = money OUT (a premium you paid)
- positive cash flow = money IN (maturity payout, current value)
"""

from datetime import date

# Cap the iterations so pathological inputs (e.g. huge day counts, all-positive
# series) can never make the endpoint hang - we return None instead.
MAX_ITERATIONS = 100

# Standard Excel-style initial guess.
INITIAL_GUESS = 0.1

# Newton-Raphson is considered converged when an iteration changes the rate
# by less than this much.
TOLERANCE = 1e-7


def _npv(rate: float, cashflows: list[tuple[date, float]], base_date: date) -> float:
    """Net present value of the series discounted at `rate`."""
    return sum(
        amount / ((1.0 + rate) ** ((d - base_date).days / 365.0))
        for d, amount in cashflows
    )


def _npv_derivative(rate: float, cashflows: list[tuple[date, float]], base_date: date) -> float:
    """Analytic derivative of the NPV with respect to `rate`."""
    total = 0.0
    for d, amount in cashflows:
        t = (d - base_date).days / 365.0
        total += -t * amount / ((1.0 + rate) ** (t + 1.0))
    return total


def xirr(cashflows: list[tuple[date, float]]) -> float | None:
    """
    Compute XIRR for a list of (date, amount) pairs.

    - negative amount = money OUT (premiums paid)
    - positive amount = money IN (payout / current value)

    Returns the annualized rate as a float (e.g. 0.055 = 5.5%), or None when
    the calculation can't be done. None (never an exception) keeps callers
    like the reality-check endpoint graceful - a non-convergent series just
    means "we can't honestly state a number here".

    A rate of exactly -100% would mean the money went to zero, which breaks
    the discounting math (division by zero), so it's guarded against like any
    other failure case.
    """
    if not cashflows or len(cashflows) < 2:
        # Need at least one outflow and one inflow to have any return at all.
        return None

    # Excel requires at least one positive and one negative flow; without
    # that, no rate can make the NPV zero (or every rate can).
    has_positive = any(amount > 0 for _, amount in cashflows)
    has_negative = any(amount < 0 for _, amount in cashflows)
    if not (has_positive and has_negative):
        return None

    cashflows = sorted(cashflows, key=lambda cf: cf[0])
    base_date = cashflows[0][0]

    # Guard against a zero/negative rate breaking the discount factor.
    rate = INITIAL_GUESS
    if rate <= -0.99:
        rate = -0.99

    for _ in range(MAX_ITERATIONS):
        # (1 + rate)**t can overflow float range mid-iteration when a step
        # sends the rate wildly out of range. That's divergence, not a crash
        # condition - treat it the same as non-convergence and return None.
        try:
            npv = _npv(rate, cashflows, base_date)
            derivative = _npv_derivative(rate, cashflows, base_date)
        except OverflowError:
            return None

        if derivative == 0.0:
            return None  # can't step; give up honestly rather than hang

        next_rate = rate - npv / derivative

        # If a step would overshoot past -100%, clamp just above it so the
        # discount factor stays valid and iteration can recover.
        if next_rate <= -0.99:
            next_rate = -0.99

        if abs(next_rate - rate) < TOLERANCE:
            return next_rate

        rate = next_rate

    return None  # didn't converge within the cap - no crash, no hang
