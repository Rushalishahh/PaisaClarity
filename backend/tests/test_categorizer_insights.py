import pytest
import pandas as pd
from categorizer import categorize, normalize_description, NON_SPENDING_CATEGORIES, CATEGORY_RULES
from insights import (
    _spending_debits,
    get_category_totals,
    get_monthly_category_spend,
    get_savings_summary,
    forecast_next_month_spend,
    detect_anomalies,
)


def test_non_spending_categories_constant():
    assert isinstance(NON_SPENDING_CATEGORIES, (set, list, tuple))
    assert set(NON_SPENDING_CATEGORIES) == {"Income", "Investments", "Transfers"}


def test_categorizer_required_categories_and_merchants():
    required_merchants = {
        "ZOMATO": "Food",
        "SWIGGY": "Food",
        "ZEPTO": "Groceries",
        "BLINKIT": "Groceries",
        "BIGBASKET": "Groceries",
        "DMART": "Groceries",
        "AMAZON": "Shopping",
        "FLIPKART": "Shopping",
        "MYNTRA": "Shopping",
        "UBER": "Transport",
        "OLA": "Transport",
        "RAPIDO": "Transport",
        "IRCTC": "Transport",
        "JIO": "Bills",
        "AIRTEL": "Bills",
        "NETFLIX": "Entertainment",
        "HOTSTAR": "Entertainment",
        "SPOTIFY": "Entertainment",
        "LIC": "Insurance",
        "ZERODHA": "Investments",
        "GROWW": "Investments",
        "SIP": "Investments",
    }

    for merchant, expected_category in required_merchants.items():
        narration = f"UPI/123456/{merchant}/PAYMENT"
        cat = categorize(narration)
        assert cat == expected_category, f"Expected {merchant} -> {expected_category}, got {cat}"


def test_normalization_rail_tokens_and_digits():
    narration = "UPI/POS/NEFT/IMPS/RTGS/ACH/ECS/BIL/BPAY/MMT/INB/ATM 9876 ZOMATO"
    norm = normalize_description(narration)
    assert "UPI" not in norm
    assert "POS" not in norm
    assert "9876" not in norm
    assert "ZOMATO" in norm


def test_insights_excludes_non_spending_categories():
    df = pd.DataFrame([
        {"type": "credit", "category": "Income", "amount": 100000.0, "date": pd.Timestamp("2026-01-05")},
        {"type": "debit", "category": "Investments", "amount": 20000.0, "date": pd.Timestamp("2026-01-10")},
        {"type": "debit", "category": "Transfers", "amount": 10000.0, "date": pd.Timestamp("2026-01-12")},
        {"type": "debit", "category": "Food", "amount": 5000.0, "date": pd.Timestamp("2026-01-15")},
        {"type": "debit", "category": "Rent", "amount": 25000.0, "date": pd.Timestamp("2026-01-01")},
        {"type": "debit", "category": "Other", "amount": 2000.0, "date": pd.Timestamp("2026-01-20")},
    ])

    spend_df = _spending_debits(df)
    categories_in_spend = set(spend_df["category"])
    assert "Investments" not in categories_in_spend
    assert "Transfers" not in categories_in_spend
    assert "Income" not in categories_in_spend
    assert "Food" in categories_in_spend
    assert "Rent" in categories_in_spend
    assert "Other" in categories_in_spend

    # category totals (excludes Other + Non-spending)
    cat_totals = get_category_totals(df)
    assert "Investments" not in cat_totals
    assert "Transfers" not in cat_totals
    assert "Rent" in cat_totals
    assert cat_totals["Rent"] == 25000.0
    assert cat_totals["Food"] == 5000.0

    # savings summary
    savings = get_savings_summary(df)
    # Total spend should be Food (5000) + Rent (25000) + Other (2000) = 32000
    assert savings["total_spend"] == 32000.0
    assert savings["total_income"] == 100000.0
    assert savings["total_saved"] == 68000.0
