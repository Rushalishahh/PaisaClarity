"""Chronological backtesting and forecasting evaluation benchmark for PaisaClarity (Phase 10).

Evaluates:
1. Linear Regression
2. Rolling Average (3-Month)
3. Rolling Average (6-Month)
4. Seasonal Naive
5. Hybrid Run-Rate with IQR Outlier Filtering & Recurring Commitments

Metrics:
- MAE (Mean Absolute Error)
- WAPE (Weighted Absolute Percentage Error)
- Forecast Bias (Mean Error: y_hat - y)
- Outlier Shock Resilience
- Sparse History Performance
"""

import calendar
from collections import defaultdict
import datetime as dt
import math
import random
from typing import Dict, List, Tuple
import numpy as np

from forecasting import (
    forecast_linear_regression,
    forecast_rolling_average,
    forecast_seasonal_naive,
    forecast_hybrid_month_end,
)


def generate_synthetic_spending_history(
    start_date: dt.date,
    num_months: int = 24,
    seed: int = 42,
) -> Tuple[Dict[str, List[Tuple[dt.date, float]]], Dict[str, float]]:
    """Generates synthetic daily transactions with recurring bills, discretionary spend,

    seasonal holiday spikes, and random outlier shocks.
    Returns:
        monthly_txs: dict of month_key -> list of (date, amount)
        monthly_actual_totals: dict of month_key -> total expense
    """
    random.seed(seed)
    np.random.seed(seed)

    recurring_rules = [
        {"day": 5, "amount": 25000.0, "name": "Rent"},
        {"day": 10, "amount": 1200.0, "name": "Broadband"},
        {"day": 15, "amount": 999.0, "name": "Netflix/Prime"},
        {"day": 20, "amount": 2800.0, "name": "Electricity"},
    ]

    monthly_txs = defaultdict(list)
    monthly_actual_totals = defaultdict(float)

    curr_year = start_date.year
    curr_month = start_date.month

    for m_idx in range(num_months):
        month_key = f"{curr_year}-{curr_month:02d}"
        _, days_in_month = calendar.monthrange(curr_year, curr_month)

        # 1. Recurring bills
        for rec in recurring_rules:
            bill_date = dt.date(curr_year, curr_month, min(rec["day"], days_in_month))
            amt = rec["amount"] + random.uniform(-50.0, 50.0)  # minor fluctuation
            monthly_txs[month_key].append((bill_date, round(amt, 2)))

        # 2. Daily discretionary spending
        for day in range(1, days_in_month + 1):
            d = dt.date(curr_year, curr_month, day)
            # Weekend bump
            is_weekend = d.weekday() >= 5
            mean_spend = 1200.0 if is_weekend else 700.0
            daily_amt = max(0.0, float(np.random.normal(mean_spend, 300.0)))
            if daily_amt > 50.0:
                monthly_txs[month_key].append((d, round(daily_amt, 2)))

        # 3. Seasonal festival spike (October/November = Diwali, December = year-end trip)
        if curr_month in (10, 11):
            spike_day = dt.date(curr_year, curr_month, 18)
            monthly_txs[month_key].append((spike_day, round(random.uniform(20000.0, 35000.0), 2)))
        elif curr_month == 12:
            spike_day = dt.date(curr_year, curr_month, 24)
            monthly_txs[month_key].append((spike_day, round(random.uniform(15000.0, 25000.0), 2)))

        # 4. Occasional random outlier shocks (e.g. medical emergency, electronics)
        if m_idx in (6, 15, 21):
            shock_day = dt.date(curr_year, curr_month, 12)
            shock_amt = 45000.0 if m_idx == 6 else (60000.0 if m_idx == 15 else 35000.0)
            monthly_txs[month_key].append((shock_day, shock_amt))

        # Calculate ground truth total for this month
        tot = sum(amt for _, amt in monthly_txs[month_key])
        monthly_actual_totals[month_key] = round(tot, 2)

        # Advance to next month
        curr_month += 1
        if curr_month > 12:
            curr_month = 1
            curr_year += 1

    return monthly_txs, monthly_actual_totals


def run_chronological_backtest() -> Dict[str, Any]:
    """Runs a rolling chronological forecast evaluation across 24 synthetic months."""
    start_date = dt.date(2024, 1, 1)
    monthly_txs, monthly_actual_totals = generate_synthetic_spending_history(start_date, num_months=24)
    month_keys = sorted(monthly_txs.keys())

    # We evaluate from month 7 onwards (so models have at least 6 months of historical data)
    eval_months = month_keys[6:]

    # Model prediction accumulators
    # checkpoints: day 10, day 15, day 20 of the month
    checkpoints = [10, 15, 20]

    results_by_model = {
        "Linear Regression": {"errors": [], "signed_errors": [], "actuals": []},
        "Rolling 3-Month": {"errors": [], "signed_errors": [], "actuals": []},
        "Rolling 6-Month": {"errors": [], "signed_errors": [], "actuals": []},
        "Seasonal Naive": {"errors": [], "signed_errors": [], "actuals": []},
        "Hybrid Run-Rate (Outlier-Filtered)": {"errors": [], "signed_errors": [], "actuals": []},
    }

    # Recurring commitments info for hybrid model
    recurring_bills = [
        {"day": 5, "amount": 25000.0},
        {"day": 10, "amount": 1200.0},
        {"day": 15, "amount": 999.0},
        {"day": 20, "amount": 2800.0},
    ]

    for m_idx, m_key in enumerate(eval_months):
        year, month = map(int, m_key.split("-"))
        _, days_in_month = calendar.monthrange(year, month)
        actual_total = monthly_actual_totals[m_key]

        # Prior completed months series
        prev_keys = month_keys[: 6 + m_idx]
        prior_monthly_totals = [monthly_actual_totals[k] for k in prev_keys]

        for check_day in checkpoints:
            today = dt.date(year, month, check_day)

            # Actual MTD spend up to check_day
            txs_in_month = monthly_txs[m_key]
            mtd_txs = [t for t in txs_in_month if t[0] <= today]
            mtd_expenses = sum(t[1] for t in mtd_txs)

            # Daily spend history for MTD
            daily_spend_map = defaultdict(float)
            for d, amt in mtd_txs:
                daily_spend_map[d.day] += amt
            daily_history = [daily_spend_map.get(d, 0.0) for d in range(1, check_day + 1)]

            # Confirmed upcoming recurring commitments due after check_day
            upcoming_recurring = sum(
                rec["amount"] for rec in recurring_bills if rec["day"] > check_day
            )

            # 1. Linear Regression on prior completed months + current MTD annualized
            pred_lr = forecast_linear_regression(prior_monthly_totals)
            # Adjust LR based on elapsed portion if midway through
            # Pure monthly series forecaster
            results_by_model["Linear Regression"]["errors"].append(abs(pred_lr - actual_total))
            results_by_model["Linear Regression"]["signed_errors"].append(pred_lr - actual_total)
            results_by_model["Linear Regression"]["actuals"].append(actual_total)

            # 2. Rolling 3-Month
            pred_r3 = forecast_rolling_average(prior_monthly_totals, window=3)
            results_by_model["Rolling 3-Month"]["errors"].append(abs(pred_r3 - actual_total))
            results_by_model["Rolling 3-Month"]["signed_errors"].append(pred_r3 - actual_total)
            results_by_model["Rolling 3-Month"]["actuals"].append(actual_total)

            # 3. Rolling 6-Month
            pred_r6 = forecast_rolling_average(prior_monthly_totals, window=6)
            results_by_model["Rolling 6-Month"]["errors"].append(abs(pred_r6 - actual_total))
            results_by_model["Rolling 6-Month"]["signed_errors"].append(pred_r6 - actual_total)
            results_by_model["Rolling 6-Month"]["actuals"].append(actual_total)

            # 4. Seasonal Naive
            pred_sn = forecast_seasonal_naive(prior_monthly_totals)
            results_by_model["Seasonal Naive"]["errors"].append(abs(pred_sn - actual_total))
            results_by_model["Seasonal Naive"]["signed_errors"].append(pred_sn - actual_total)
            results_by_model["Seasonal Naive"]["actuals"].append(actual_total)

            # 5. Hybrid Run-Rate with Outlier-Resistant Discretionary Pace
            hybrid_res = forecast_hybrid_month_end(
                today=today,
                mtd_expenses=mtd_expenses,
                daily_spend_history=daily_history,
                upcoming_recurring_total=upcoming_recurring,
                completed_months_history=prior_monthly_totals,
            )
            pred_hybrid = hybrid_res.predicted_total
            results_by_model["Hybrid Run-Rate (Outlier-Filtered)"]["errors"].append(abs(pred_hybrid - actual_total))
            results_by_model["Hybrid Run-Rate (Outlier-Filtered)"]["signed_errors"].append(pred_hybrid - actual_total)
            results_by_model["Hybrid Run-Rate (Outlier-Filtered)"]["actuals"].append(actual_total)

    # Compute aggregate metrics
    benchmark_metrics = {}
    for model_name, data in results_by_model.items():
        errs = np.array(data["errors"])
        signed = np.array(data["signed_errors"])
        actuals = np.array(data["actuals"])

        mae = float(np.mean(errs))
        wape = float(np.sum(errs) / np.sum(actuals)) * 100.0
        bias = float(np.mean(signed))

        benchmark_metrics[model_name] = {
            "MAE": round(mae, 2),
            "WAPE_pct": round(wape, 2),
            "Forecast_Bias": round(bias, 2),
            "Samples": len(errs),
        }

    # Evaluate specific edge case: Extreme Outlier Shock Resilience
    # A single ₹80,000 one-off spike on Day 8
    today_shock = dt.date(2025, 5, 12)
    daily_spend_shock = [800.0, 950.0, 600.0, 750.0, 80000.0, 850.0, 900.0, 700.0, 1100.0, 650.0, 800.0, 900.0]
    mtd_shock = sum(daily_spend_shock)

    # Unfiltered naive run-rate:
    naive_daily_pace = mtd_shock / 12.0
    naive_month_end = mtd_shock + (naive_daily_pace * (31 - 12))

    # Hybrid model with IQR filtering:
    hybrid_shock = forecast_hybrid_month_end(
        today=today_shock,
        mtd_expenses=mtd_shock,
        daily_spend_history=daily_spend_shock,
        upcoming_recurring_total=5000.0,
        completed_months_history=[55000.0, 58000.0, 54000.0],
    )

    outlier_comparison = {
        "day": 12,
        "mtd_spend": round(mtd_shock, 2),
        "outlier_amount": 80000.0,
        "naive_run_rate_forecast": round(naive_month_end, 2),
        "hybrid_forecast": round(hybrid_shock.predicted_total, 2),
        "uncertainty_lower": round(hybrid_shock.uncertainty_lower, 2),
        "uncertainty_upper": round(hybrid_shock.uncertainty_upper, 2),
        "distortion_prevented": round(naive_month_end - hybrid_shock.predicted_total, 2),
    }

    # Evaluate Sparse History Edge Case (only 1 completed month)
    sparse_hybrid = forecast_hybrid_month_end(
        today=dt.date(2025, 2, 5),
        mtd_expenses=4500.0,
        daily_spend_history=[900.0, 850.0, 950.0, 1000.0, 800.0],
        upcoming_recurring_total=15000.0,
        completed_months_history=[42000.0],
    )
    sparse_comparison = {
        "confidence_level": sparse_hybrid.confidence_level,
        "predicted_total": round(sparse_hybrid.predicted_total, 2),
        "uncertainty_range": f"₹{sparse_hybrid.uncertainty_lower:,.2f} - ₹{sparse_hybrid.uncertainty_upper:,.2f}",
        "explanation": sparse_hybrid.explanation,
    }

    return {
        "chronological_benchmark": benchmark_metrics,
        "outlier_shock_evaluation": outlier_comparison,
        "sparse_history_evaluation": sparse_comparison,
    }


if __name__ == "__main__":
    results = run_chronological_backtest()
    print("=" * 80)
    print("CHRONOLOGICAL SPENDING FORECASTING BENCHMARK RESULTS")
    print("=" * 80)
    print(f"{'Model':<35} | {'MAE (₹)':<12} | {'WAPE (%)':<10} | {'Forecast Bias (₹)':<18}")
    print("-" * 80)
    for model, m in results["chronological_benchmark"].items():
        print(f"{model:<35} | ₹{m['MAE']:<11,.2f} | {m['WAPE_pct']:<8.2f}% | ₹{m['Forecast_Bias']:<17,.2f}")

    print("\n" + "=" * 80)
    print("OUTLIER SHOCK RESILIENCE TEST")
    print("=" * 80)
    o = results["outlier_shock_evaluation"]
    print(f"MTD Spend with ₹80,000 Outlier on Day 12: ₹{o['mtd_spend']:,.2f}")
    print(f"Naive Daily Run-Rate Forecast (Distorted):  ₹{o['naive_run_rate_forecast']:,.2f}")
    print(f"Hybrid Run-Rate Forecast (IQR Filtered):   ₹{o['hybrid_forecast']:,.2f}")
    print(f"Expected Uncertainty Range:                ₹{o['uncertainty_lower']:,.2f} to ₹{o['uncertainty_upper']:,.2f}")
    print(f"Distortion Prevented by Outlier Filtering: ₹{o['distortion_prevented']:,.2f}")

    print("\n" + "=" * 80)
    print("SPARSE HISTORY EDGE CASE TEST")
    print("=" * 80)
    s = results["sparse_history_evaluation"]
    print(f"Confidence Level Assigned:                 {s['confidence_level']}")
    print(f"Predicted Total:                           ₹{s['predicted_total']:,.2f}")
    print(f"Uncertainty Range:                         {s['uncertainty_range']}")
    print(f"Explanation:                               {s['explanation']}")

