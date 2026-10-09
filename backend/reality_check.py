"""
Policy Reality Check - arithmetic on what a user already owns.

Combines two things the app already stores:
  1. A policy's premium schedule (start_date, premium_amount,
     premium_frequency) and maturity data, reconstructed into a dated
     cash-flow series and solved for XIRR (see xirr.py).
  2. Real historical NAVs for a large Nifty 50 index fund (see
     market_data.py), simulating "what the same premiums would have bought"
     as an honest benchmark.

IMPORTANT FRAMING (reflected in every message string below): this is an
informational calculation on data the user entered - NEVER advice to
surrender, switch, or buy anything. Every function here degrades to None
plus a message when a number can't be honestly computed.
"""

from datetime import date

from market_data import get_scheme_nav_history, get_nav_on_or_before
from xirr import xirr

# Benchmark fund - see BENCHMARK_FUND_NAME. Verified live against
# https://api.mfapi.in/mf/search?q=nifty%2050%20index (resolves to this
# scheme) and https://api.mfapi.in/mf/100822/latest (returns a current NAV).
#
# Why this fund:
# - UTI Nifty 50 Index Fund - Regular Plan - Growth is one of India's oldest
#   and largest Nifty 50 index funds (launched 2000), so its NAV history
#   covers the 2005-2015 era when most traditional policies being analyzed
#   were sold - a younger fund would leave early premium dates with no
#   benchmark price at all.
# - It's a plain market-cap-weighted Nifty 50 tracker: the standard
#   "passive equity alternative" reference point, and a large, well-known
#   asset manager (UTI) rather than an obscure scheme.
# - Regular Plan (not Direct) is deliberate: policy premiums are typically
#   paid through an agent/distributor channel, so the regular-plan NAV is
#   the like-for-like comparison. Index fund expense ratios are low enough
#   that this choice barely moves the number.
BENCHMARK_SCHEME_CODE = "100822"
BENCHMARK_FUND_NAME = "UTI Nifty 50 Index Fund - Regular Plan - Growth"

# If data looks wrong (e.g. a start_date decades in the past combined with a
# monthly premium), cap the reconstructed premium series rather than hanging
# the request or generating millions of rows. 1000 monthly premiums spans
# over 80 years - far beyond any real policy.
MAX_PREMIUM_PERIODS = 1000

# Days in a month/quarter for date arithmetic. We add months via a helper
# rather than timedelta(days=30) so due dates stay on the same day-of-month.
_DAYS_IN_QUARTER = 91  # not used for arithmetic - kept for documentation


def add_months(d: date, months: int) -> date:
    """Add `months` to a date, clamping day-of-month (Jan 31 + 1mo -> Feb 28)."""
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    # Clamp to the last valid day of the target month.
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    last_day = (next_month - date.resolution).day
    return date(year, month, min(d.day, last_day))


def build_premium_dates(start_date: date, frequency: str, today: date) -> list[date]:
    """
    Generate every premium payment date from start_date through today at the
    policy's frequency. Returns [] for unknown/missing frequencies. The
    MAX_PREMIUM_PERIODS cap protects against bad data (start_date "1900-01-01")
    producing an absurd number of payments.
    """
    frequency = (frequency or "").strip().lower()
    if frequency == "monthly":
        step = 1
    elif frequency == "quarterly":
        step = 3
    elif frequency == "yearly":
        step = 12
    else:
        return []

    dates: list[date] = []
    current = start_date
    while current <= today and len(dates) < MAX_PREMIUM_PERIODS:
        dates.append(current)
        current = add_months(current, step)
    return dates


def reconstruct_policy_cashflows(
    start_date: date,
    premium_amount: float,
    frequency: str,
    today: date,
    maturity_date: date | None,
    maturity_value: float | None,
    invested_amount: float,
) -> dict:
    """
    Build the dated cash-flow series for one policy and solve its XIRR.

    - One negative flow per premium date (premium_amount).
    - Final positive flow:
        * maturity_value if today >= maturity_date (the policy actually paid out), or
        * invested_amount (total premiums paid) as an explicitly-labeled ESTIMATE
          when the policy is still running - we don't have insurer surrender-value
          tables, so this assumes you could exit at par today, which real
          traditional policies typically don't allow. Callers must surface
          `is_estimated_current_value` so the UI can caveat it.

    Returns a dict with everything the endpoint needs; `policy_xirr` may be
    None if the series can't produce a rate.
    """
    premium_dates = build_premium_dates(start_date, frequency, today)

    # No premiums reconstructed (bad frequency, cap hit with zero periods,
    # etc.) - no honest calculation possible.
    if not premium_dates:
        return {
            "premium_dates": [],
            "policy_xirr": None,
            "is_estimated_current_value": False,
            "total_premiums_paid": 0.0,
            "num_premiums_counted": 0,
            "message": "Could not reconstruct premium payments - check the policy's start date and premium frequency.",
        }

    # Sanity check against the stored invested_amount: if it disagrees with
    # the reconstructed schedule by a lot, the user's schedule assumptions
    # (or the stored total) are off - prefer the reconstructed count for the
    # cash-flow series but surface the discrepancy in a message.
    reconstructed_total = len(premium_dates) * premium_amount
    if invested_amount and abs(reconstructed_total - invested_amount) > max(1.0, invested_amount * 0.05):
        discrepancy_note = (
            f"Reconstructed premiums total about {round(reconstructed_total):,.0f} "
            f"but the recorded invested amount is {round(invested_amount):,.0f} - "
            f"the calculation uses the reconstructed schedule."
        )
    else:
        discrepancy_note = None

    cashflows = [(d, -premium_amount) for d in premium_dates]

    if maturity_date is not None and today >= maturity_date:
        # Policy matured - the final inflow is what it actually paid.
        final_amount = float(maturity_value) if maturity_value is not None else 0.0
        is_estimated = False
        final_date = maturity_date
    else:
        # Still running - estimate current value at total premiums paid.
        final_amount = float(invested_amount) if invested_amount else reconstructed_total
        is_estimated = True
        final_date = today

    cashflows.append((final_date, final_amount))

    policy_xirr = xirr(cashflows)

    return {
        "premium_dates": premium_dates,
        "policy_xirr": policy_xirr,
        "is_estimated_current_value": is_estimated,
        "total_premiums_paid": round(reconstructed_total, 2),
        "num_premiums_counted": len(premium_dates),
        "message": discrepancy_note,
    }


def simulate_benchmark_investment(
    premium_dates: list[date],
    premium_amount: float,
    nav_history: list[tuple[date, float]],
    today: date,
) -> dict:
    """
    "What the same money would have done in a Nifty 50 index fund instead."

    On each premium date, buy units of the benchmark fund at the nearest
    available historical NAV on or before that date (weekends/holidays have
    no NAV). Value the total units at the fund's LATEST NAV.

    Returns benchmark_xirr (may be None) plus the pieces needed for
    transparency (units bought, current value).
    """
    if not premium_dates or premium_amount <= 0 or not nav_history:
        return {
            "benchmark_xirr": None,
            "total_units": 0.0,
            "current_value": None,
        }

    latest_nav = nav_history[-1][1]  # history is sorted oldest-first
    today_value_date = nav_history[-1][0]

    total_units = 0.0
    cashflows: list[tuple[date, float]] = []

    for premium_date in premium_dates:
        nav = get_nav_on_or_before(nav_history, premium_date)
        if nav is None:
            # History starts after this premium date (fund didn't exist yet).
            # Skip that premium honestly rather than inventing a price.
            continue
        units = premium_amount / nav
        total_units += units
        cashflows.append((premium_date, -premium_amount))

    if not cashflows:
        return {
            "benchmark_xirr": None,
            "total_units": 0.0,
            "current_value": None,
        }

    # Value today: total units * latest NAV. If the fund's history somehow
    # ends before today, use its last available date as the valuation date.
    current_value = total_units * latest_nav
    valuation_date = min(today, today_value_date)

    cashflows.append((valuation_date, current_value))

    benchmark_xirr = xirr(cashflows)

    return {
        "benchmark_xirr": benchmark_xirr,
        "total_units": round(total_units, 4),
        "current_value": round(current_value, 2),
    }


def compute_reality_check(policy) -> dict:
    """
    Full reality-check calculation for one policy Investment row.

    Returns the endpoint response shape directly. Every failure mode
    (missing start_date, missing schedule fields, non-convergent XIRR,
    benchmark API down) degrades to None values + a clear message - never a
    500, never a fabricated number.
    """
    today = date.today()

    # --- Guard: the fields the calculation fundamentally needs ---
    if policy.start_date is None:
        return {
            "policy_xirr_pct": None,
            "benchmark_xirr_pct": None,
            "benchmark_fund_name": BENCHMARK_FUND_NAME,
            "is_estimated_current_value": False,
            "total_premiums_paid": None,
            "num_premiums_counted": 0,
            "message": "Add a start date to calculate this. Edit the policy and set when it began.",
        }

    if not policy.premium_amount or not policy.premium_frequency:
        return {
            "policy_xirr_pct": None,
            "benchmark_xirr_pct": None,
            "benchmark_fund_name": BENCHMARK_FUND_NAME,
            "is_estimated_current_value": False,
            "total_premiums_paid": None,
            "num_premiums_counted": 0,
            "message": "Premium amount and frequency are needed to reconstruct this policy's payment history.",
        }

    if policy.start_date > today:
        return {
            "policy_xirr_pct": None,
            "benchmark_xirr_pct": None,
            "benchmark_fund_name": BENCHMARK_FUND_NAME,
            "is_estimated_current_value": False,
            "total_premiums_paid": None,
            "num_premiums_counted": 0,
            "message": "This policy's start date is in the future - nothing to calculate yet.",
        }

    # --- 1. Policy cash flows and XIRR ---
    policy_result = reconstruct_policy_cashflows(
        start_date=policy.start_date,
        premium_amount=float(policy.premium_amount),
        frequency=policy.premium_frequency,
        today=today,
        maturity_date=policy.maturity_date,
        maturity_value=float(policy.maturity_value) if policy.maturity_value is not None else None,
        invested_amount=float(policy.invested_amount) if policy.invested_amount is not None else 0.0,
    )

    # --- 2. Benchmark simulation on the same premium dates ---
    nav_history = get_scheme_nav_history(BENCHMARK_SCHEME_CODE)
    benchmark_result = {"benchmark_xirr": None, "total_units": 0.0, "current_value": None}
    if nav_history is None:
        benchmark_note = "Benchmark comparison unavailable right now - the market data service didn't respond."
    else:
        benchmark_note = None
        benchmark_result = simulate_benchmark_investment(
            premium_dates=policy_result["premium_dates"],
            premium_amount=float(policy.premium_amount),
            nav_history=nav_history,
            today=today,
        )

    # --- 3. Assemble the response, folding every partial failure into a message ---
    messages = [m for m in (policy_result["message"], benchmark_note) if m]
    if policy_result["policy_xirr"] is None and policy_result["premium_dates"]:
        messages.append(
            "The return couldn't be computed from this data - check the policy's dates and amounts."
        )

    return {
        "policy_xirr_pct": (
            round(policy_result["policy_xirr"] * 100, 2)
            if policy_result["policy_xirr"] is not None
            else None
        ),
        "benchmark_xirr_pct": (
            round(benchmark_result["benchmark_xirr"] * 100, 2)
            if benchmark_result["benchmark_xirr"] is not None
            else None
        ),
        "benchmark_fund_name": BENCHMARK_FUND_NAME,
        "is_estimated_current_value": policy_result["is_estimated_current_value"],
        "total_premiums_paid": policy_result["total_premiums_paid"],
        "num_premiums_counted": policy_result["num_premiums_counted"],
        "message": " ".join(messages) if messages else None,
    }
