import pandas as pd
import random
from datetime import datetime, timedelta

# Merchant description patterns as they'd realistically appear in bank statements
merchant_patterns = {
    "Food": ["UPI-ZOMATO-{}", "UPI-SWIGGY-{}", "POS MCDONALDS {}", "UPI-LOCALRESTAURANT-{}"],
    "Shopping": ["UPI-AMAZON-{}", "UPI-FLIPKART-{}", "POS MYNTRA {}"],
    "Transport": ["UPI-UBER-{}", "UPI-OLA-{}", "POS PETROLPUMP {}"],
    "Bills": ["UPI-ELECTRICITYBOARD-{}", "UPI-AIRTEL-{}", "UPI-JIO-{}"],
    "Entertainment": ["UPI-NETFLIX-{}", "UPI-BOOKMYSHOW-{}", "UPI-SPOTIFY-{}"],
    "Groceries": ["UPI-BIGBASKET-{}", "POS DMART {}", "UPI-LOCALGROCERY-{}"]
}

def random_txn_id():
    return str(random.randint(100000, 999999))

def generate_statement(num_transactions=300, months_back=6):
    rows = []
    end_date = datetime.now()
    start_date = end_date - timedelta(days=months_back * 30)
    balance = 20000.00

    salary_dates = []
    for m in range(months_back):
        month_start = start_date + timedelta(days=m * 30)
        salary_day = month_start + timedelta(days=random.randint(0, 4))
        salary_dates.append(salary_day)

    num_spend_txns = num_transactions - len(salary_dates)
    spend_dates = [start_date + (end_date - start_date) * random.random() for _ in range(num_spend_txns)]

    monthly_salary = 40000
    total_income = monthly_salary * months_back
    total_spend_budget = total_income * 0.85
    avg_spend_per_txn = total_spend_budget / num_spend_txns

    events = [(d, "salary") for d in salary_dates] + [(d, "spend") for d in spend_dates]
    events.sort(key=lambda x: x[0])

    for date, kind in events:
        # Decide if this transaction is a cheque (rare, ~4% of spend transactions)
        is_cheque = (kind == "spend") and (random.random() < 0.04)

        if kind == "salary":
            credit = round(random.uniform(monthly_salary * 0.95, monthly_salary * 1.05), 2)
            debit = None
            desc = "UPI-SALARY-CREDIT-" + random_txn_id()
            balance += credit
            ref_no = ""
            value_date = date  # digital credit - reflects same day

        elif is_cheque:
            debit = round(max(50, random.gauss(avg_spend_per_txn, avg_spend_per_txn * 0.4)), 2)
            credit = None
            desc = "CHQ PAID " + random_txn_id()
            balance -= debit
            ref_no = str(random.randint(100000, 999999))  # cheque number
            value_date = date + timedelta(days=random.randint(1, 3))  # cheques take a few days to clear

        else:
            category = random.choice(list(merchant_patterns.keys()))
            pattern = random.choice(merchant_patterns[category])
            desc = pattern.format(random_txn_id())
            debit = round(max(50, random.gauss(avg_spend_per_txn, avg_spend_per_txn * 0.4)), 2)
            credit = None
            balance -= debit
            ref_no = ""  # blank - normal for UPI/POS transactions
            value_date = date  # digital debit - reflects same day

        rows.append({
            "Txn Date": date.strftime("%d/%m/%Y"),
            "Value Date": value_date.strftime("%d/%m/%Y"),
            "Description": desc,
            "Ref No./Cheque No.": ref_no,
            "Withdrawal Amt.": debit,
            "Deposit Amt.": credit,
            "Closing Balance": round(balance, 2)
        })

    df = pd.DataFrame(rows)
    return df

if __name__ == "__main__":
    df = generate_statement()
    print(df.head(15))
    print(f"\nTotal transactions: {len(df)}")

    import os
    os.makedirs("data", exist_ok=True)
    df.to_csv("data/sample_statement.csv", index=False)
    print("Saved to data/sample_statement.csv")