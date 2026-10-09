import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression

from categorizer import NON_SPENDING_CATEGORIES


def _spending_debits(df):
    """
    The one definition of "spending" used everywhere below: debits whose
    category is NOT in NON_SPENDING_CATEGORIES (Income/Investments/Transfers
    are not purchases). 'Other' debits DO count as spend - the money did
    leave the account - they're just not charted per-category.
    """
    return df[(df["type"] == "debit") & (~df["category"].isin(NON_SPENDING_CATEGORIES))]


def get_category_totals(df):
    """Total spend per category for the chart (excludes non-spending + 'Other')."""
    spend_df = df[(df["type"] == "debit") & (~df["category"].isin(NON_SPENDING_CATEGORIES)) & (df["category"] != "Other")]
    totals = spend_df.groupby("category")["amount"].sum().sort_values(ascending=False)
    return totals


def get_uncategorized_summary(df):
    """
    Report uncategorized ('Other') transactions separately instead of
    folding them into normal category analysis - e.g. cheque payments
    where we don't know the actual purpose from the description alone.
    """
    other_df = df[(df["type"] == "debit") & (df["category"] == "Other")]

    if len(other_df) == 0:
        return {
            "count": 0,
            "total_amount": 0.0,
            "message": "No uncategorized transactions."
        }

    return {
        "count": len(other_df),
        "total_amount": round(other_df["amount"].sum(), 2),
        "message": f"{len(other_df)} uncategorized transactions "
                   f"(₹{round(other_df['amount'].sum(), 2)}) — mostly cheque payments "
                   f"without a clear description. Consider labeling these manually."
    }


def get_monthly_category_spend(df):
    """Spend per category, per month - needed for trend/anomaly detection. Excludes non-spending categories and 'Other'."""
    spend_df = df[(df["type"] == "debit") & (~df["category"].isin(NON_SPENDING_CATEGORIES)) & (df["category"] != "Other")].copy()
    spend_df["month"] = spend_df["date"].dt.to_period("M")
    monthly = spend_df.groupby(["month", "category"])["amount"].sum().reset_index()
    return monthly


def _exclude_current_month(monthly_df):
    """
    Drop the current calendar month from monthly aggregates since it's
    always incomplete (in progress) and would skew trend/anomaly comparisons.
    """
    current_month = pd.Timestamp.now().to_period("M")
    return monthly_df[monthly_df["month"] != current_month].copy()


def detect_anomalies(monthly_df, threshold=1.5):
    """
    Flag category-months where spend is significantly above that category's average.
    threshold=1.5 means: flag if spend is 50% higher than usual average for that category.
    """
    monthly_df = _exclude_current_month(monthly_df)
    anomalies = []
    category_avg = monthly_df.groupby("category")["amount"].mean()

    for _, row in monthly_df.iterrows():
        avg = category_avg[row["category"]]
        if row["amount"] > avg * threshold:
            pct_increase = ((row["amount"] - avg) / avg) * 100
            anomalies.append({
                "month": str(row["month"]),
                "category": row["category"],
                "amount": round(row["amount"], 2),
                "average": round(avg, 2),
                "pct_increase": round(pct_increase, 1)
            })
    return anomalies


def get_savings_summary(df):
    """
    Overall income vs spend vs savings rate.

    Income = credits that are not self-Transfers (a transfer in from your
             own account is not income; Income-category credits ARE income).
    Spend  = debits NOT in NON_SPENDING_CATEGORIES (SIPs, self-transfers
             and other own-money movements are not spending).
    """
    income_df = df[(df["type"] == "credit") & (df["category"] != "Transfers")]
    spend_df = _spending_debits(df)
    total_income = income_df["amount"].sum()
    total_spend = spend_df["amount"].sum()
    saved = total_income - total_spend
    savings_rate = (saved / total_income * 100) if total_income > 0 else 0

    return {
        "total_income": round(total_income, 2),
        "total_spend": round(total_spend, 2),
        "total_saved": round(saved, 2),
        "savings_rate_pct": round(savings_rate, 1)
    }


def get_month_over_month_trend(monthly_df):
    """
    For each category, compare latest month's spend to the previous month.
    Returns % change - more intuitive than comparing to a long-term average.
    """
    monthly_df = _exclude_current_month(monthly_df)
    trends = []
    for category in monthly_df["category"].unique():
        cat_data = monthly_df[monthly_df["category"] == category].sort_values("month")
        if len(cat_data) < 2:
            continue  # need at least 2 months to compare

        latest = cat_data.iloc[-1]
        previous = cat_data.iloc[-2]

        if previous["amount"] > 0:
            pct_change = ((latest["amount"] - previous["amount"]) / previous["amount"]) * 100
        else:
            pct_change = 0

        trends.append({
            "category": category,
            "latest_month": str(latest["month"]),
            "latest_amount": round(latest["amount"], 2),
            "previous_month": str(previous["month"]),
            "previous_amount": round(previous["amount"], 2),
            "pct_change": round(pct_change, 1)
        })

    return trends


def forecast_next_month_spend(df):
    """
    Simple linear regression: predict next month's TOTAL spend
    based on the trend across previous months. Excludes 'Other' and
    the current (incomplete) month.
    """
    spend_df = _spending_debits(df).copy()
    spend_df["month"] = spend_df["date"].dt.to_period("M")
    monthly_totals = spend_df.groupby("month")["amount"].sum().reset_index()

    current_month = pd.Timestamp.now().to_period("M")
    monthly_totals = monthly_totals[monthly_totals["month"] != current_month]

    monthly_totals = monthly_totals.sort_values("month").reset_index(drop=True)

    if len(monthly_totals) < 3:
        return {"error": "Not enough months of data to forecast (need at least 3)"}

    X = np.arange(len(monthly_totals)).reshape(-1, 1)
    y = monthly_totals["amount"].values

    model = LinearRegression()
    model.fit(X, y)

    next_month_index = np.array([[len(monthly_totals)]])
    prediction = model.predict(next_month_index)[0]

    # Spending can never be negative - a regression extrapolation going below
    # zero just means we don't have enough data for a reliable trend line yet
    prediction = max(0, prediction)

    return {
        "predicted_next_month_spend": round(float(prediction), 2),
        "based_on_months": len(monthly_totals),
        "trend_slope_per_month": round(float(model.coef_[0]), 2),
        "low_confidence": len(monthly_totals) < 4  # flag if based on very few months
    }


import re

# Generic banking/transaction-rail tokens that show up in descriptions but
# aren't part of the merchant's name - strip these out before grouping.
_GENERIC_DESCRIPTION_TOKENS = {
    "UPI", "POS", "NEFT", "IMPS", "ACH", "CHQ", "PAID", "RTGS", "ATM", "CARD", "TXN"
}


def _normalize_merchant(description):
    """
    Bank statement descriptions usually embed a random reference/transaction
    ID alongside the merchant name (e.g. 'UPI-ZOMATO-785386'). Grouping by
    the raw description would treat every single transaction as a unique
    "merchant", since that ID is different every time - so we strip out
    digits and generic banking-rail tokens (UPI, POS, NEFT...) to get a
    stable merchant name to group on (e.g. 'ZOMATO').
    """
    words = re.findall(r"[A-Za-z]+", description.upper())
    merchant_words = [w for w in words if w not in _GENERIC_DESCRIPTION_TOKENS]
    return " ".join(merchant_words) if merchant_words else description.upper()


def detect_recurring_subscriptions(df, min_occurrences=2, amount_tolerance=0.1):
    """
    Detect likely recurring subscriptions/bills by grouping debit transactions
    by normalized merchant name and checking for a consistent amount recurring
    across multiple distinct months.

    - min_occurrences: minimum number of distinct months a merchant must
      appear in to be considered "recurring" (default 2).
    - amount_tolerance: max fractional deviation from the average amount for
      a transaction to still count as "the same" recurring charge (default
      10%, e.g. Rs.499 one month and Rs.509 the next both count).
    """
    spend_df = df[(df["type"] == "debit") & (~df["category"].isin(NON_SPENDING_CATEGORIES)) & (df["category"] != "Other")].copy()
    if spend_df.empty:
        return []

    spend_df["month"] = spend_df["date"].dt.to_period("M")
    spend_df["merchant"] = spend_df["description"].apply(_normalize_merchant)

    subscriptions = []
    for merchant, group in spend_df.groupby("merchant"):
        # Collapse to one amount per month (in case a merchant is charged
        # more than once in the same month, e.g. two separate purchases)
        monthly_amounts = group.groupby("month")["amount"].mean()

        if len(monthly_amounts) < min_occurrences:
            continue

        avg_amount = monthly_amounts.mean()
        if avg_amount == 0:
            continue

        # All months' amounts must stay within tolerance of the average
        # for this to look like a fixed recurring charge rather than
        # coincidentally-similar one-off purchases
        deviations = (monthly_amounts - avg_amount).abs() / avg_amount
        if (deviations > amount_tolerance).any():
            continue

        months_sorted = sorted(monthly_amounts.index)
        subscriptions.append({
            "merchant": merchant,
            "category": group["category"].iloc[0],
            "average_amount": round(avg_amount, 2),
            "months_seen": len(monthly_amounts),
            "first_seen": str(months_sorted[0]),
            "last_seen": str(months_sorted[-1]),
            "estimated_annual_cost": round(avg_amount * 12, 2),
        })

    subscriptions.sort(key=lambda s: s["average_amount"], reverse=True)
    return subscriptions


def get_savings_suggestions(monthly_df, savings_summary):
    """
    Rule-based personalized suggestions using data we already computed:
    - Flag categories trending up
    - Suggest a concrete savings amount if cutting back
    """
    suggestions = []
    trends = get_month_over_month_trend(monthly_df)

    for t in trends:
        if t["pct_change"] > 30:  # category grew more than 30% vs last month
            potential_savings = round(t["latest_amount"] * 0.2, 2)  # suggest cutting 20%
            suggestions.append(
                f"Your {t['category']} spending rose {t['pct_change']}% last month "
                f"(₹{t['previous_amount']} → ₹{t['latest_amount']}). "
                f"Cutting it by 20% could save you ₹{potential_savings} next month."
            )

    if savings_summary["savings_rate_pct"] < 20:
        suggestions.append(
            f"Your current savings rate is {savings_summary['savings_rate_pct']}%. "
            f"Financial experts generally recommend saving at least 20% of income — "
            f"consider reviewing your top spending categories."
        )
    elif savings_summary["savings_rate_pct"] > 40:
        suggestions.append(
            f"Great job — you're saving {savings_summary['savings_rate_pct']}% of your income, "
            f"well above the recommended 20% benchmark."
        )

    if not suggestions:
        suggestions.append("Your spending looks stable with no major red flags this period.")

    return suggestions