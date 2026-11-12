"""Evaluation and benchmark suite comparing Rule-Based Categorizer vs Scikit-Learn ML Classifier.

Measures:
- Accuracy, Precision, Recall, Macro-F1
- False-positive resistance on adversarial sub-words (e.g. SALON vs SALARY, COLA vs OLA)
- Handling of unseen/unknown merchants
- Inference latency
"""

import os
import sys
import time
from typing import Dict, List, Tuple
import numpy as np

# Ensure backend root on python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from categorizer import categorize_with_explanation, normalize_description
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.metrics import classification_report, f1_score, precision_score, recall_score, accuracy_score


# ---------------------------------------------------------------------------
# Synthetic Benchmark Dataset with Challenging Real-World Indian Bank Narrations
# ---------------------------------------------------------------------------
DATASET: List[Tuple[str, str]] = [
    # Food
    ("UPI/12345/Zomato/pay", "Food"),
    ("POS 45678 SWIGGY BANGALORE IN", "Food"),
    ("UPI-MCDONALDS-DRIVE-THRU", "Food"),
    ("DOMINOS PIZZA ONLINE ORDER", "Food"),
    ("STARBUCKS COFFEE KORAMANGALA", "Food"),
    ("KFC RESTAURANT INDIRANAGAR", "Food"),
    ("CAFE COFFEE DAY AIRPORT", "Food"),
    ("LOCALRESTAURANT LUNCH THALI", "Food"),
    ("EATFIT MEAL SUBSCRIPTION", "Food"),
    ("BOX8 DESI MEALS PUNE", "Food"),
    ("FAASOS ROLLS ORDER", "Food"),
    ("POS SWIPE AT PIZZA HUT", "Food"),
    ("UPI/BURGER KING/MUMBAI", "Food"),
    ("SUBWAY SANDWICHES BANDRA", "Food"),
    ("HALDIRAM SWEETS AND RESTAURANT", "Food"),
    ("BARBEQUE NATION DINING", "Food"),

    # Groceries
    ("BIGBASKET GROCERY ORDER 9823", "Groceries"),
    ("POS DMART HYPERMARKET THANE", "Groceries"),
    ("BLINKIT 10 MIN GROCERY", "Groceries"),
    ("ZEPTO QUICK COMMERCE", "Groceries"),
    ("INSTAMART DAILY ESSENTIALS", "Groceries"),
    ("RELIANCE FRESH VEGETABLES", "Groceries"),
    ("MORE SUPERMARKET RETAIL", "Groceries"),
    ("NATURES BASKET GOURMET", "Groceries"),
    ("LOCALGROCERY STORE PURCHASE", "Groceries"),
    ("JIOMART ONLINE GROCERY", "Groceries"),
    ("SPENCERS RETAIL GROCERIES", "Groceries"),

    # Shopping
    ("AMAZON INDIA SELLER PAYMENT", "Shopping"),
    ("FLIPKART INTERNET PVT LTD", "Shopping"),
    ("MYNTRA DESIGNS APPAREL", "Shopping"),
    ("AJIO FASHION RELIANCE", "Shopping"),
    ("MEESHO ONLINE SHOPPING", "Shopping"),
    ("NYKAA COSMETICS RETAIL", "Shopping"),
    ("TATA CLIQ LUXURY STORE", "Shopping"),
    ("CROMA ELECTRONICS STORE", "Shopping"),
    ("RELIANCE DIGITAL GADGETS", "Shopping"),
    ("DECATHLON SPORTS INDIA", "Shopping"),
    ("IKEA FURNITURE NAGASANDRA", "Shopping"),
    ("ZARA RETAIL CLOTHING", "Shopping"),
    ("H&M APPAREL STORE", "Shopping"),

    # Transport
    ("UBER INDIA RIDE PAYMENT", "Transport"),
    ("OLA CABS TRIP RECEIPT", "Transport"),
    ("RAPIDO BIKE TAXI RIDE", "Transport"),
    ("IRCTC RAILWAY TICKET BOOKING", "Transport"),
    ("REDBUS INTERCITY BUS", "Transport"),
    ("METRO RAIL SMART CARD RECHARGE", "Transport"),
    ("PETROL PUMP HP FUEL", "Transport"),
    ("INDIAN OIL PETROL REFILL", "Transport"),
    ("BPCL AUTO FUEL STATION", "Transport"),
    ("SHELL PETROL STATION WHITEFIELD", "Transport"),
    ("FASTAG TOLL PLAZA CHARGE", "Transport"),
    ("MALL PARKING FEE CHARGES", "Transport"),

    # Bills
    ("ELECTRICITY BOARD BESCOM BILL", "Bills"),
    ("TATA POWER BILL PAYMENT", "Bills"),
    ("AIRTEL POSTPAID MOBILE BILL", "Bills"),
    ("JIO PREPAID RECHARGE PLAN", "Bills"),
    ("VODAFONE IDEA MONTHLY BILL", "Bills"),
    ("ACT FIBERNET BROADBAND BILL", "Bills"),
    ("INDANE CYLINDER REFILL BOOKING", "Bills"),
    ("HP GAS DOMESTIC CYLINDER", "Bills"),
    ("BBPS WATER SUPPLY BOARD", "Bills"),
    ("TATA PLAY DTH RECHARGE", "Bills"),
    ("SUN DIRECT SATELLITE TV", "Bills"),
    ("ADANI ELECTRICITY MUMBAI", "Bills"),

    # Entertainment
    ("NETFLIX MONTHLY SUBSCRIPTION", "Entertainment"),
    ("DISNEY HOTSTAR ANNUAL PACK", "Entertainment"),
    ("PRIME VIDEO DIGITAL ENTERTAINMENT", "Entertainment"),
    ("SPOTIFY PREMIUM MUSIC", "Entertainment"),
    ("BOOKMYSHOW MOVIE TICKETS PVR", "Entertainment"),
    ("YOUTUBE PREMIUM FAMILY PLAN", "Entertainment"),
    ("SONY LIV STREAMING SERVICE", "Entertainment"),
    ("ZEE5 ENTERTAINMENT PACK", "Entertainment"),
    ("GAANA PLUS SUBSCRIPTION", "Entertainment"),
    ("JIOSAVN PRO MUSIC", "Entertainment"),
    ("STEAM GAMING PURCHASE", "Entertainment"),

    # Health
    ("APOLLO PHARMACY MEDICINES", "Health"),
    ("PHARMEASY ONLINE PRESCRIPTION", "Health"),
    ("NETMEDS HEALTHCARE ORDER", "Health"),
    ("FORTIS HOSPITAL CONSULTATION", "Health"),
    ("MANIPAL HOSPITAL OPD CHARGES", "Health"),
    ("DR LAL PATHLABS DIAGNOSTICS", "Health"),
    ("CLINIC GENERAL PHYSICIAN VISIT", "Health"),

    # Investments
    ("ACH D- ZERODHA BROKING LTD", "Investments"),
    ("GROWW MUTUAL FUND SIP 123", "Investments"),
    ("KUVERA MF DIRECT INVESTMENT", "Investments"),
    ("UPSTOX SECURITIES TRADING", "Investments"),
    ("HDFC SECURITIES DEMAT", "Investments"),
    ("ICICI PRUDENTIAL MUTUAL FUND", "Investments"),
    ("PPF PUBLIC PROVIDENT FUND", "Investments"),
    ("NPS NATIONAL PENSION SCHEME", "Investments"),
    ("SIP HDFC TOP 100 FUND", "Investments"),

    # Insurance
    ("LIC OF INDIA PREMIUM PAYMENT", "Insurance"),
    ("HDFC LIFE INSURANCE POLICY", "Insurance"),
    ("SBI LIFE ASSURANCE CO", "Insurance"),
    ("ICICI PRU LIFE TERM PLAN", "Insurance"),
    ("BAJAJ ALLIANZ GENERAL INSURANCE", "Insurance"),
    ("MAX LIFE TERM INSURANCE", "Insurance"),
    ("TATA AIA LIFE INSURANCE", "Insurance"),

    # EMI & Loans
    ("HDFC HOME LOAN EMI DEDUCTION", "EMI & Loans"),
    ("SBI CAR LOAN AUTO DEBIT", "EMI & Loans"),
    ("BAJAJ FINANCE CONSUMER LOAN", "EMI & Loans"),
    ("ICICI PERSONAL LOAN EMI", "EMI & Loans"),

    # Rent
    ("HOUSE RENT PAYMENT FOR MONTH", "Rent"),
    ("SOCIETY MAINTENANCE CHARGES", "Rent"),
    ("LANDLORD FLAT RENTAL ACCOUNT", "Rent"),

    # Education
    ("SCHOOL ADMISSION TERM FEES", "Education"),
    ("COLLEGE QUARTERLY TUITION", "Education"),
    ("UDEMY ONLINE COURSE PURCHASE", "Education"),
    ("COURSERA LEARNING SUBSCRIPTION", "Education"),
    ("UNACADEMY PLUS CLASS FEES", "Education"),

    # Cash Withdrawal
    ("ATM CASH WITHDRAWAL KORAMANGALA", "Cash Withdrawal"),
    ("NFS ATM WDL MG ROAD", "Cash Withdrawal"),
    ("CASH WDL SELF FROM BRANCH", "Cash Withdrawal"),

    # Income
    ("SALARY CREDIT ACME CORP PVT", "Income"),
    ("MONTHLY PAYROLL DIRECT DEPOSIT", "Income"),
    ("CONSULTING STIPEND INTERNSHIP", "Income"),
    ("SAVINGS BANK INTEREST CREDIT", "Income"),
    ("INCOME TAX REFUND DEPOSIT", "Income"),

    # Transfers
    ("TRANSFER TO SELF SAVINGS ACC", "Transfers"),
    ("ACCOUNT TRANSFER TO BROTHER", "Transfers"),
    ("PAYTM P2P WALLET TRANSFER", "Transfers"),
    ("PHONEPE P2P MONEY SENT", "Transfers"),
    ("SPLITWISE EXPENSE SETTLEMENT", "Transfers"),

    # Challenging False-Positive Adversarial Cases
    ("SALON SERVICES CUT AND SHAVE", "Other"),       # Must not trigger 'SAL' (Income)
    ("COLA BEVERAGE PURCHASE AT CAFE", "Food"),     # Must not trigger 'OLA' (Transport)
    ("CHOCOLATE DESSERT SHOP", "Food"),             # Must not trigger 'OLA' (Transport)
    ("BARRISTER LEGAL CONSULTATION", "Other"),      # Must not trigger 'BAR'
    ("STEAM CARPET CLEANING", "Other"),             # Must not trigger 'TEA'
    ("LAS VEGAS HOTEL RESORT TRIP", "Travel"),      # Must not trigger 'GAS'
    ("FREEZE PACK MEAT SHOP", "Groceries"),         # Must not trigger 'ZEE'
    ("BOXING CHAMPION GYM FEES", "Other"),          # Must not trigger 'BOX'
    ("ATMA RAM JEWELLERS", "Other"),                # Must not trigger 'ATM'
    ("GENERIC HARDWARE CORNER STORE", "Other"),     # Unknown merchant fallback
    ("XYZ RANDOM MERCHANT 9812", "Other"),          # Unknown merchant fallback
]

# Multiply to generate a robust 600-sample test set with variations
EXPANDED_DATASET: List[Tuple[str, str]] = []
for desc, cat in DATASET:
    EXPANDED_DATASET.append((desc, cat))
    EXPANDED_DATASET.append((f"UPI/{desc}/PAYMENT-REF-109", cat))
    EXPANDED_DATASET.append((f"POS DEBIT {desc} CARD 4402", cat))
    EXPANDED_DATASET.append((f"NEFT-{desc}-TRANSFER-091", cat))
    EXPANDED_DATASET.append((f"ACH DR {desc} AUTO", cat))


def evaluate_categorization_models() -> Dict[str, Any]:
    """Train ML model and compare against Rule-Based categorizer on stratified held-out data."""
    X = [item[0] for item in EXPANDED_DATASET]
    y = [item[1] for item in EXPANDED_DATASET]

    # Stratified 80/20 train/test split
    sss = StratifiedShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    train_idx, test_idx = next(sss.split(X, y))

    X_train = [X[i] for i in train_idx]
    y_train = [y[i] for i in train_idx]
    X_test = [X[i] for i in test_idx]
    y_test = [y[i] for i in test_idx]

    # 1. Rule-Based Categorizer Evaluation
    t0 = time.perf_counter()
    y_pred_rule = [categorize_with_explanation(x).category for x in X_test]
    rule_latency_ms = ((time.perf_counter() - t0) / len(X_test)) * 1000

    rule_acc = accuracy_score(y_test, y_pred_rule)
    rule_macro_f1 = f1_score(y_test, y_pred_rule, average="macro", zero_division=0)
    rule_macro_prec = precision_score(y_test, y_pred_rule, average="macro", zero_division=0)
    rule_macro_rec = recall_score(y_test, y_pred_rule, average="macro", zero_division=0)

    # 2. Scikit-Learn ML Classifier Pipeline
    ml_pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True)),
        ("clf", LogisticRegression(C=5.0, max_iter=300, random_state=42)),
    ])
    ml_pipeline.fit(X_train, y_train)

    t0 = time.perf_counter()
    y_pred_ml = ml_pipeline.predict(X_test)
    ml_latency_ms = ((time.perf_counter() - t0) / len(X_test)) * 1000

    ml_acc = accuracy_score(y_test, y_pred_ml)
    ml_macro_f1 = f1_score(y_test, y_pred_ml, average="macro", zero_division=0)
    ml_macro_prec = precision_score(y_test, y_pred_ml, average="macro", zero_division=0)
    ml_macro_rec = recall_score(y_test, y_pred_ml, average="macro", zero_division=0)

    # 3. Adversarial Edge Case Testing (Word boundary false-positive resistance)
    adversarial_samples = [
        ("SALON BEAUTY SERVICES", "Other"),
        ("COLA COLD DRINK", "Food"),
        ("BARRISTER ADVOCATE FEE", "Other"),
        ("STEAM CLEANING LAUNDRY", "Other"),
        ("BOXING FITNESS GYM", "Other"),
        ("ATMA SHANTI ASHRAM", "Other"),
        ("FREEZE ICECREAM CONE", "Food"),
    ]
    rule_adv_correct = sum(1 for text, true_cat in adversarial_samples if categorize_with_explanation(text).category == true_cat)
    ml_adv_correct = sum(1 for text, true_cat in adversarial_samples if ml_pipeline.predict([text])[0] == true_cat)

    return {
        "dataset_size": len(EXPANDED_DATASET),
        "train_size": len(X_train),
        "test_size": len(X_test),
        "rule_based": {
            "accuracy": round(float(rule_acc), 4),
            "macro_f1": round(float(rule_macro_f1), 4),
            "macro_precision": round(float(rule_macro_prec), 4),
            "macro_recall": round(float(rule_macro_rec), 4),
            "latency_ms_per_txn": round(float(rule_latency_ms), 4),
            "adversarial_score": f"{rule_adv_correct}/{len(adversarial_samples)}",
        },
        "scikit_learn_ml": {
            "accuracy": round(float(ml_acc), 4),
            "macro_f1": round(float(ml_macro_f1), 4),
            "macro_precision": round(float(ml_macro_prec), 4),
            "macro_recall": round(float(ml_macro_rec), 4),
            "latency_ms_per_txn": round(float(ml_latency_ms), 4),
            "adversarial_score": f"{ml_adv_correct}/{len(adversarial_samples)}",
        },
    }


if __name__ == "__main__":
    res = evaluate_categorization_models()
    print("=== CATEGORIZATION EVALUATION BENCHMARK RESULTS ===")
    print(f"Dataset: {res['dataset_size']} total ({res['train_size']} train, {res['test_size']} test)")
    print("\n--- Rule-Based Categorizer (Whole-Word Regex + Normalization) ---")
    for k, v in res["rule_based"].items():
        print(f"  {k}: {v}")
    print("\n--- Scikit-Learn ML Classifier (TF-IDF + LogisticRegression) ---")
    for k, v in res["scikit_learn_ml"].items():
        print(f"  {k}: {v}")

