import csv
import os
from collections import defaultdict
import pytest
from categorizer import categorize, CATEGORY_RULES

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def test_four_known_false_positives_fixed():
    """Verify that keywords are no longer matched as substrings inside longer words."""
    # 1. 'SAL' was matching inside 'SALON' -> Income
    assert categorize("UPI/123456/SALON BLISS/okaxis") == "Other"

    # 2. 'OLA' was matching inside 'COLA' -> Transport
    assert categorize("POS COCA COLA OUTLET") == "Other"

    # 3. 'GAS' was matching inside 'GASOLINE' -> Bills
    assert categorize("UPI/5566/GASOLINE STATION") == "Other"

    # 4. 'PRIME' was matching inside 'PRIMEMART' -> Entertainment
    assert categorize("POS 4567 PRIMEMART") == "Other"


def test_must_keep_working_cases():
    """Verify standard and tricky narrations continue to classify correctly."""
    cases = [
        ("UPI/987654/SWIGGY/BANGALORE", "Food"),
        ("POS 5544 ZOMATO ORDER", "Food"),
        ("NEFT-HDFCN52024-ACME CORP-SALARY CREDIT", "Income"),
        ("ATM WDL CASH 5000", "Cash Withdrawal"),
        ("UPI/112233/NETFLIX/SUBSCRIPTION", "Entertainment"),
        ("UPI/334455/UBER RIDES/MUMBAI", "Transport"),
        ("ACH D- LIC POLICY PREMIUM", "Insurance"),
        ("SIP B25SIP278 HDFC MUTUAL FUND", "Investments"),
        ("UPI/123/Zomato/okaxis/payment", "Food"),
        ("EMI-XXXXXX HOME LOAN", "EMI & Loans"),
        ("BIL/BPAY/BBPS/BESCOM ELECTRICITY BILL", "Bills"),
        ("UPI/667788/FLAT MONTHLY RENT/BANGALORE", "Rent"),
    ]
    for narration, expected in cases:
        actual = categorize(narration)
        assert actual == expected, f"Failed on '{narration}': expected {expected}, got {actual}"


def test_multi_word_phrase_matching():
    """Verify multi-word keywords match properly as whole phrases."""
    phrases = [
        ("SIP HDFC MUTUAL FUND INVESTMENT", "Investments"),
        ("ATM WDL KORAMANGALA BLR", "Cash Withdrawal"),
        ("MAKE MY TRIP FLIGHT TICKET", "Travel"),
        ("HDFC LIFE POLICY RENEWAL", "Insurance"),
        ("TATA POWER BILL PAYMENT", "Bills"),
        ("Q4 INTEREST CREDIT SAVINGS", "Income"),
        ("MONTHLY SOCIETY MAINT CHARGE", "Rent"),
        ("BAJAJ FINANCE MONTHLY INSTALMENT", "EMI & Loans"),
    ]
    for narration, expected in phrases:
        actual = categorize(narration)
        assert actual == expected, f"Failed phrase '{narration}': expected {expected}, got {actual}"


def test_keyword_does_not_match_inside_longer_word():
    """Verify boundaries prevent partial/stem matches inside other English words."""
    false_positives = [
        ("SALON BLISS HAIRCUT", "Income"),
        ("CHILLED COCA COLA DRINK", "Transport"),
        ("STATION ROAD GASOLINE", "Bills"),
        ("SHOP AT PRIMEMART STORE", "Entertainment"),
        ("DELICIOUS FRESH BAKERY", "Insurance"),        # 'LIC' inside DELICIOUS
        ("PREMIUM COTTON SHIRTS", "EMI & Loans"),       # 'EMI' inside PREMIUM
        ("CURRENT ACCOUNT CHARGES", "Rent"),           # 'RENT' inside CURRENT
        ("EMPOWER FITNESS GYM", "Bills"),              # 'POWER' inside EMPOWER
        ("DOWNTOWN BOOKSTORE", "Transfers"),           # 'OWN' inside DOWNTOWN
        ("WOODEN BOOKSHELF RETAIL", "Transfers"),       # 'SELF' inside BOOKSHELF
        ("ORGANIC CASHEW NUT PACK", "Cash Withdrawal"), # 'CASH' inside CASHEW
    ]
    for narration, forbidden_category in false_positives:
        actual = categorize(narration)
        assert actual != forbidden_category, (
            f"False positive on '{narration}': matched {forbidden_category}"
        )


def test_every_keyword_in_category_rules_matches_itself():
    """
    Ensure every keyword in CATEGORY_RULES can match itself as a standalone token.
    Guards against malformed regexes, accidental empty strings, or unmatchable rules.
    """
    for category, keywords in CATEGORY_RULES.items():
        for kw in keywords:
            actual = categorize(kw)
            assert actual == category, (
                f"Keyword self-matching failed for '{kw}' in category '{category}': "
                f"categorized as '{actual}'"
            )


def test_labeled_dev_split_accuracy(capsys):
    """
    Load labeled_transactions.csv and assert accuracy on the dev split >= 95%.
    Prints per-category precision and recall for transparency.
    """
    csv_path = os.path.join(FIXTURES_DIR, "labeled_transactions.csv")
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        dev_rows = [r for r in reader if r["split"] == "dev"]

    total = len(dev_rows)
    correct = 0
    tp = defaultdict(int)
    fp = defaultdict(int)
    fn = defaultdict(int)
    all_categories = set()

    for r in dev_rows:
        desc = r["description"]
        expected = r["expected_category"]
        predicted = categorize(desc)
        all_categories.add(expected)
        all_categories.add(predicted)

        if predicted == expected:
            correct += 1
            tp[expected] += 1
        else:
            fp[predicted] += 1
            fn[expected] += 1

    accuracy = correct / total if total > 0 else 0

    # Print report for visibility
    print("\n--- DEV SPLIT EVALUATION REPORT ---")
    print(f"Overall Accuracy: {correct}/{total} ({accuracy:.2%})")
    print(f"{'Category':<18} | {'Precision':<10} | {'Recall':<10} | {'Support':<8}")
    print("-" * 52)
    for cat in sorted(all_categories):
        p = tp[cat] / (tp[cat] + fp[cat]) if (tp[cat] + fp[cat]) > 0 else 0.0
        rec = tp[cat] / (tp[cat] + fn[cat]) if (tp[cat] + fn[cat]) > 0 else 0.0
        support = tp[cat] + fn[cat]
        print(f"{cat:<18} | {p:<9.2%} | {rec:<9.2%} | {support:<8}")

    # Dev split covers targeted Indian banking patterns; justify >= 95% threshold
    assert accuracy >= 0.95, f"Dev split accuracy {accuracy:.2%} is below 95% threshold"

