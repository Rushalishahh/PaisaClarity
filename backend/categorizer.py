"""
Rule-based transaction categorizer for real Indian bank narrations.

Real descriptions look like:
    UPI/321456789012/Zomato/okaxis/payment
    POS 4567XXXXXX1234 SWIGGY
    NEFT-HDFCN52024-ACME CORP-SALARY
    ATM WDL
    ACH D- LIC OF INDIA
    BIL/BPAY/BBPS/ELECTRICITY BOARD
    EMI-XXXXXX HOME LOAN
    INT.PD

Strategy: normalize the narration FIRST (uppercase, strip digits and
banking-rail tokens), then match against one keyword table. All rules live
in the single CATEGORY_RULES structure below so adding a merchant or a
category is a one-line change.

NON_SPENDING_CATEGORIES is THE shared constant for the rest of the app:
savings rate, anomalies, budgets and the health score must never count
Income, Investments or self-Transfers as expenses.
"""

import re

# --- Single source of truth for rule-based categories -------------------
# Ordered: first match wins, so more specific rules go first (SIP/MUTUAL
# FUND must be checked before a bank's generic TRANSFER wording).
CATEGORY_RULES = {
    "Income": [
        "SALARY", "SAL", "PAYROLL", "WAGES", "STIPEND", "INTEREST CREDIT",
        "INT PD", "PENSION", "REFUND",
    ],
    "Rent": ["RENT", "SOCIETY MAINT", "LANDLORD"],
    "EMI & Loans": ["EMI", "LOAN", "FINANC", "BAJAJ FIN"],
    "Investments": [
        "SIP", "MUTUAL FUND", "ZERODHA", "GROWW", "KUVERA", "UPSTOX",
        "ANGEL ONE", "HDFC SEC", "ICICI DIRECT", "SHAREKHAN", "PPF", "NPS", "EPF",
    ],
    "Insurance": ["LIC", "HDFC LIFE", "SBI LIFE", "ICICI PRU", "INSURANCE", "BAJAJ ALLIANZ", "MAX LIFE", "TATA AIA", "POLICY PREMIUM"],
    "Cash Withdrawal": ["ATM WDL", "ATM CASH", "ATM WITHDRAWAL", "CASH WDL", "ATM", "WDL", "CASH", "WITHDRAWAL"],
    "Food": [
        "ZOMATO", "SWIGGY", "MCDONALDS", "MCDONALD", "DOMINOS", "PIZZA",
        "KFC", "STARBUCKS", "CAFE", "RESTAURANT", "HOTEL", "EATFIT", "BOX8", "FAASOS",
    ],
    "Groceries": [
        "BIGBASKET", "DMART", "BLINKIT", "ZEPTO", "GROFERS", "INSTAMART",
        "JIO MART", "JIOMART", "MORE SUPERMARKET", "GROCERY", "SUPERMARKET", "RELIANCE FRESH",
    ],
    "Shopping": [
        "AMAZON", "FLIPKART", "MYNTRA", "AJIO", "MEESHO", "NYKAA", "TATA CLIQ",
        "CROMA", "RELIANCE DIGITAL", "DECATHLON", "IKEA",
    ],
    "Transport": [
        "UBER", "OLA", "RAPIDO", "IRCTC", "REDBUS", "METRO", "PETROL", "FUEL",
        "INDIAN OIL", "HP PETROL", "BPCL", "SHELL", "FASTAG", "PARKING", "TOLL",
    ],
    "Travel": ["MAKE MY TRIP", "MAKEMYTRIP", "GOIBIBO", "CLEARTRIP", "YATRA", "AIR INDIA", "INDIGO", "VISTARA", "AKASA", "IXIGO", "EASEMYTRIP"],
    "Bills": [
        "ELECTRICITY", "POWER", "BESCOM", "MSEB", "TNEB", "TATA POWER", "ADANI",
        "AIRTEL", "JIO", "VODAFONE", "BSNL", "BROADBAND", "ACT FIBERNET",
        "GAS", "INDANE", "HP GAS", "BHARATGAS", "BBPS", "BPAY", "WATER BILL", "DTH", "TATASKY", "SUN DIRECT",
    ],
    "Entertainment": [
        "NETFLIX", "HOTSTAR", "PRIME VIDEO", "SPOTIFY", "PRIME", "BOOKMYSHOW",
        "YOUTUBE", "GAANA", "JIOSAVN", "DISNEY", "SONY LIV", "ZEE5", "GAMING",
    ],
    "Health": ["APOLLO", "PHARMEASY", "NETMEDS", "HOSPITAL", "CLINIC", "DIAGNOSTIC", "PHARMACY", "FORTIS"],
    "Education": ["SCHOOL", "COLLEGE", "TUITION", "UDEMY", "COURSERA", "UNACADEMY", "BYJU", "FEES"],
    "Transfers": [
        "SELF", "OWN", "ACCOUNT TRANSFER", "SPLITWISE", "PAYTM P2P", "PHONEPE P2P", "TRANSFER",
    ],
}
# "Other" is the explicit fallback - kept visible in the UI on purpose.
FALLBACK_CATEGORY = "Other"

# Categories that are NOT expenses for savings-rate / anomaly / budget math.
# Income (money in), Investments (putting money into your own investments)
# and self-Transfers (moving money between your own accounts) must never
# count as spending.
NON_SPENDING_CATEGORIES = {"Income", "Investments", "Transfers"}

# --- Category aliases (old saved statements -> current categories) -------
# Statement.result is a stored JSON blob: analyses saved BEFORE a renaming
# round still carry the old category strings. Instead of a one-off data
# migration, GET endpoints apply this map at READ time so old rows render
# under the new names. Old name -> current name; anything not listed is
# already current.
CATEGORY_ALIASES = {
    "Subscription": "Entertainment",
    "Subscriptions": "Entertainment",
    "Utilities": "Bills",
    "Telecom": "Bills",
    "Fuel": "Transport",
    "Loan": "EMI & Loans",
    "EMI": "EMI & Loans",
    "Cash": "Cash Withdrawal",
    "Healthcare": "Health",
    "Vacation": "Travel",
    "Trips": "Travel",
    "Investment": "Investments",
    "Transfer": "Transfers",
    "Salary": "Income",
}


def apply_category_aliases(data, _key=None):
    """
    Recursively walk a stored statement-result dict and rewrite old category
    names to the current ones:
      - any dict entry whose key is "category" gets its VALUE aliased
        (subscriptions, anomalies, month_over_month_trend items ...)
      - a dict under the key "category_totals" gets its KEYS aliased
        (amounts are summed when an old name collides with a new one)
    Returns a new structure; the stored JSON is never mutated.
    """
    if isinstance(data, dict):
        if _key == "category_totals":
            merged = {}
            for name, amount in data.items():
                new_name = CATEGORY_ALIASES.get(name, name)
                merged[new_name] = merged.get(new_name, 0) + amount
            return {k: apply_category_aliases(v, k) for k, v in merged.items()}
        return {k: apply_category_aliases(v, k) for k, v in data.items()}
    if isinstance(data, list):
        return [apply_category_aliases(item, _key) for item in data]
    if isinstance(data, str) and _key == "category":
        return CATEGORY_ALIASES.get(data, data)
    return data

# Banking-rail tokens that carry no merchant information.
_RAIL_TOKENS = {
    "UPI", "POS", "NEFT", "IMPS", "RTGS", "ACH", "ECS", "BIL", "BPAY", "BBPS",
    "MMT", "INB", "ATM", "NFS", "CARD", "CHQ", "TXN", "PMT", "P2A", "MB", "IB",
    "ACHD", "ACHC", "CLG", "CHARGES", "CHARGE", "GST", "TO", "FROM", "BY", "VIA",
    "REF", "NO", "DR", "CR", "SI",
}

_RAIL_RE = re.compile(
    r"\b(UPI|POS|NEFT|IMPS|RTGS|ACH|ECS|BIL|BPAY|BBPS|MMT|INB|ATM|NFS|NACH|MAB|INFT)\b/?"
)

_TOKEN_RE = re.compile(r"[A-Z]+")


def normalize_description(description: str) -> str:
    """
    Uppercase, strip digits/IDs and banking-rail tokens so
    'UPI/321456789012/Zomato/okaxis/payment' -> 'ZOMATO OKAXIS PAYMENT'
    and rules can match plain merchant words.
    """
    text = str(description or "").upper()
    text = _RAIL_RE.sub(" ", text)
    text = re.sub(r"\d+", " ", text)          # reference numbers
    text = re.sub(r"[^A-Z ]", " ", text)      # punctuation
    words = _TOKEN_RE.findall(text)
    words = [w for w in words if w not in _RAIL_TOKENS and len(w) > 1]
    return " ".join(words)


def categorize(description: str) -> str:
    """Return a category for a narration, or FALLBACK_CATEGORY ('Other')."""
    normalized = normalize_description(description)
    if not normalized:
        raw_upper = str(description or "").upper()
        if "ATM" in raw_upper:
            return "Cash Withdrawal"
        return FALLBACK_CATEGORY
    for category, keywords in CATEGORY_RULES.items():
        for keyword in keywords:
            if keyword.upper() in normalized:
                return category
    return FALLBACK_CATEGORY


def add_categories(df):
    """Add a `category` column to the canonical transactions DataFrame."""
    df = df.copy()
    df["category"] = df["description"].apply(categorize)
    return df


if __name__ == "__main__":
    samples = [
        "UPI/321456789012/Zomato/okaxis/payment",
        "POS 4567XXXXXX1234 SWIGGY",
        "NEFT-HDFCN52024-ACME CORP-SALARY",
        "ATM WDL 1234",
        "ACH D- LIC OF INDIA",
        "BIL/BPAY/BBPS/BESCOM/ELECTRICITY",
        "EMI-434343 HOME LOAN INSTALMENT",
        "SIP B25SIP278 HDFC MUTUAL FUND",
        "IMPS-SELF-TRANSFER-879",
        "INT.PD 2026-05",
        "MARATHAHLL STORE PURCHASE",
    ]
    for s in samples:
        print(f"{s!r:55} -> {categorize(s)}  ({normalize_description(s)})")
