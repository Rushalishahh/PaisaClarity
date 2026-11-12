"""Advanced spending forecasting models and uncertainty estimation for PaisaClarity (Phase 10).

Implements and evaluates:
1. Linear Regression Forecaster
2. Rolling Average Forecaster (3-month and 6-month)
3. Seasonal Naive Forecaster
4. Hybrid Run-Rate Forecaster with Outlier-Filtered Discretionary Burn + Recurring Commitments
"""

import calendar
from dataclasses import dataclass, field
import datetime as dt
from decimal import Decimal
import math
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression


@dataclass
class ForecastExplanation:
    forecast_period: str
    predicted_total: float
    actual_mtd: float
    confirmed_recurring: float
    projected_discretionary: float
    uncertainty_lower: float
    uncertainty_upper: float
    method_used: str
    explanation: str
    confidence_level: str  # "high", "medium", "low"
    historical_months_used: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "forecast_period": self.forecast_period,
            "predicted_total": round(self.predicted_total, 2),
            "actual_mtd": round(self.actual_mtd, 2),
            "confirmed_recurring": round(self.confirmed_recurring, 2),
            "projected_discretionary": round(self.projected_discretionary, 2),
            "uncertainty_range": {
                "lower_bound": round(self.uncertainty_lower, 2),
                "upper_bound": round(self.uncertainty_upper, 2),
            },
            "method_used": self.method_used,
            "explanation": self.explanation,
            "confidence_level": self.confidence_level,
            "historical_months_used": self.historical_months_used,
        }


def forecast_linear_regression(monthly_series: List[float]) -> float:
    """Fit a linear regression on historical chronological monthly totals."""
    if len(monthly_series) < 2:
        return monthly_series[-1] if monthly_series else 0.0
    X = np.arange(len(monthly_series)).reshape(-1, 1)
    y = np.array(monthly_series)
    model = LinearRegression()
    model.fit(X, y)
    pred = model.predict([[len(monthly_series)]])[0]
    return max(0.0, float(pred))


def forecast_rolling_average(monthly_series: List[float], window: int = 3) -> float:
    """Simple moving average of the most recent N completed months."""
    if not monthly_series:
        return 0.0
    w = min(window, len(monthly_series))
    recent = monthly_series[-w:]
    return float(np.mean(recent))


def forecast_seasonal_naive(monthly_series: List[float]) -> float:
    """Seasonal naive model: predict spend based on the same month from previous year (or lag-1 fallback)."""
    if not monthly_series:
        return 0.0
    if len(monthly_series) >= 12:
        return float(monthly_series[-12])
    return float(monthly_series[-1])


def forecast_hybrid_month_end(
    today: dt.date,
    mtd_expenses: float,
    daily_spend_history: List[float],
    upcoming_recurring_total: float,
    completed_months_history: Optional[List[float]] = None,
) -> ForecastExplanation:
    """Outlier-resistant hybrid month-end spending forecast.

    Decomposes forecast into:
    1. Actual month-to-date spent so far.
    2. Confirmed upcoming recurring commitments due this month.
    3. Estimated discretionary pace for remaining days using IQR outlier filtering.
    4. Explicit uncertainty range (95% confidence interval).
    """
    _, days_in_month = calendar.monthrange(today.year, today.month)
    days_elapsed = max(1, today.day)
    days_remaining = max(0, days_in_month - days_elapsed)

    # 1. Filter out one-time outlier spikes from daily history using IQR
    clean_daily = [s for s in daily_spend_history if s > 0]
    if len(clean_daily) >= 5:
        q25, q75 = np.percentile(clean_daily, [25, 75])
        iqr = q75 - q25
        upper_bound = q75 + 1.5 * iqr
        filtered_daily = [s for s in clean_daily if s <= upper_bound]
        daily_pace = float(np.mean(filtered_daily)) if filtered_daily else (mtd_expenses / days_elapsed)
        std_err = float(np.std(filtered_daily)) if len(filtered_daily) > 1 else (daily_pace * 0.25)
    else:
        daily_pace = mtd_expenses / days_elapsed
        std_err = daily_pace * 0.30

    projected_discretionary = daily_pace * days_remaining
    predicted_total = mtd_expenses + upcoming_recurring_total + projected_discretionary

    # Uncertainty bound: sqrt of days_remaining scaling for random walk volatility
    volatility = std_err * math.sqrt(max(1, days_remaining)) * 1.96
    lower_bound = max(mtd_expenses + upcoming_recurring_total, predicted_total - volatility)
    upper_bound = predicted_total + volatility

    # Confidence rating based on history depth and days elapsed
    hist_len = len(completed_months_history) if completed_months_history else 0
    if days_elapsed >= 15 and hist_len >= 3:
        conf = "high"
    elif days_elapsed >= 7 or hist_len >= 2:
        conf = "medium"
    else:
        conf = "low"

    period_str = f"{calendar.month_name[today.month]} {today.year}"
    explanation = (
        f"Forecast for {period_str} based on ₹{mtd_expenses:,.2f} spent MTD ({days_elapsed}/{days_in_month} days), "
        f"₹{upcoming_recurring_total:,.2f} in confirmed upcoming recurring commitments, and an estimated "
        f"daily discretionary pace of ₹{daily_pace:,.2f}/day for the remaining {days_remaining} day(s)."
    )

    return ForecastExplanation(
        forecast_period=period_str,
        predicted_total=predicted_total,
        actual_mtd=mtd_expenses,
        confirmed_recurring=upcoming_recurring_total,
        projected_discretionary=projected_discretionary,
        uncertainty_lower=lower_bound,
        uncertainty_upper=upper_bound,
        method_used="Hybrid Run-Rate with Outlier-Resistant Discretionary Burn + Confirmed Recurring Bills",
        explanation=explanation,
        confidence_level=conf,
        historical_months_used=hist_len,
    )
