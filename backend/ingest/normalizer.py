"""
Row-level cleaning and canonicalization.

Input : raw rows (list of list of cells) + a column mapping {canonical: index}
Output: a DataFrame in the EXACT canonical contract downstream code expects:

    date        datetime64 - transaction date
    value_date  datetime64 - value date (falls back to date)
    description str
    ref_no      str
    amount      float64    - always POSITIVE
    type        str        - "debit" (money out) or "credit" (money in)
    balance     float64    - closing balance when known (NaN otherwise)

This is the same contract the original single-format parser.py produced, so
categorizer.py and insights.py keep working unchanged.
"""

import calendar
import re
from datetime import date, datetime, timedelta

import pandas as pd

from .errors import MappingRequired

EXCEL_EPOCH = date(1899, 12, 30)  # Excel serial day 0 (with the 1900 leap-year bug accounted for)

# Rows that are labels/totals, never transactions. Matched against the
# lowercased concatenation of the row's cells.
_SKIP_RE = re.compile(
    r"^(opening\s*balance|closing\s*balance|brought\s*forward|carried\s*forward|"
    r"balance\s*b/?f|b/?f|page\s*(total|\d+)|total|grand\s*total|sub\s*total|"
    r"statement\s*(summary|total)|transaction\s*total|closing\s*bal\s*this\s*period)"
)

_DATE_FORMATS = (
    "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y",
    "%d.%m.%Y", "%d.%m.%y",
    "%d-%b-%Y", "%d-%b-%y", "%d %b %Y", "%d %b %y",
    "%d-%B-%Y", "%d %B %Y", "%d%B%Y",
    "%d %m %Y",
    "%Y-%m-%d", "%Y/%m/%d",  # ISO - unambiguous, checked after day-first forms
)

_AMT_CLEAN_RE = re.compile(r"[^\d.\-()]")
_DRCR_SUFFIX_RE = re.compile(r"\b(dr|cr)\b\.?", re.IGNORECASE)


def parse_date_any(value):
    """
    Day-first date parsing for Indian banks across the common formats,
    plus Excel serial numbers. Returns datetime or None.

    NOTE: never US-style - dd/mm wins over mm/dd. Truly ambiguous ISO-like
    values are parsed day-first too (Y-m-d is explicit, everything else is
    day-first by Indian convention).
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    s = str(value).strip()
    if not s:
        return None
    # Excel serial number (integer or float as text): 45000-ish is ~2023.
    if re.fullmatch(r"\d{4,7}(\.\d+)?", s):
        try:
            serial = float(s)
            if 20000 <= serial <= 60000:  # ~1954..2064 - sane serial range
                return datetime.combine(EXCEL_EPOCH + timedelta(days=int(serial)), datetime.min.time())
        except ValueError:
            pass
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    # Last resort: dateutil-free "dd-MMM-yy" variants already covered above;
    # try pandas' flexible parser ONLY for unambiguous ISO timestamps.
    if re.match(r"^\d{4}-\d{2}-\d{2}T", s):
        try:
            return pd.to_datetime(s).to_pydatetime()
        except (ValueError, TypeError):
            return None
    return None


def parse_amount(value):
    """
    Robust amount parsing. Returns (float|None, "debit"|"credit"|None).

    Handles: lakh grouping (1,00,000.00), currency markers (Rs., INR, rupee),
    spaces, parentheses negatives, trailing "Dr"/"Cr" suffixes, "-" and ""
    as None. The Dr/Cr suffix (layout 4) sets the side.
    """
    if value is None:
        return None, None
    if isinstance(value, (int, float)):
        return float(value), None
    s = str(value).strip()
    if not s or s in {"-", "--", "NA", "N/A", "na", "nil", "NIL", "."}:
        return None, None

    side = None
    m = _DRCR_SUFFIX_RE.search(s)
    if m:
        side = "debit" if m.group(1).lower() == "dr" else "credit"
        s = _DRCR_SUFFIX_RE.sub(" ", s)

    negative = False
    if "(" in s and ")" in s:
        negative = True
        s = s.replace("(", " ").replace(")", " ")
    s = _AMT_CLEAN_RE.sub("", s).replace(",", "").strip()
    if not s or s in {"-", "."}:
        return None, side
    try:
        val = float(s)
    except ValueError:
        return None, side
    if negative:
        val = -abs(val)
    return val, side


def _row_text(cells):
    return " ".join(str(c).strip() for c in cells if str(c).strip()).lower()


def _cells_at(row, mapping):
    """Pull the mapped cells out of a raw row (padded to mapping size)."""
    out = {}
    for canon, idx in mapping.items():
        out[canon] = row[idx] if idx < len(row) else ""
    return out


def normalize_rows(rows, mapping, header_index, report):
    """
    Turn raw rows + mapping into the canonical DataFrame, collecting
    skipped reasons and balance warnings into `report` as we go.

    Layout support (documented):
      (1) separate debit + credit columns
      (2) single signed amount column (negative = debit)
      (3) unsigned amount + Dr/Cr indicator column
      (4) Dr/Cr suffixes on the amount strings themselves
      (5) single amount + balance column: infer side from whether the
          running balance FELL (debit) or ROSE (credit) vs the previous row
          - heuristic, flagged in report.warnings
    """
    parsed = []       # dicts: {date, description, ref_no, amount, type, balance, order}
    skipped = []      # (row_index, reason)
    skipped_reasons = []

    has_debit_credit = "debit" in mapping and "credit" in mapping
    has_amount = "amount" in mapping
    has_drcr_col = "dr_cr" in mapping
    has_balance = "balance" in mapping

    def skip(i, reason):
        skipped.append(i)
        skipped_reasons.append(f"row {i}: {reason}")

    prev_balance = None
    last_txn = None  # for continuation-line merging

    data_rows = [
        (i, r) for i, r in enumerate(rows) if header_index is None or i > header_index
    ]

    for i, row in data_rows:
        cells = _cells_at(row, mapping)
        text = _row_text(row)

        # --- Drop non-transaction rows (totals, legends, repeated headers...) ---
        # An OPENING BALANCE / BROUGHT FORWARD line (date prefix or not) is a
        # label row, but it seeds the balance-delta baseline for layout 5.
        if _SKIP_RE.match(text) or "opening balance" in text or "brought forward" in text:
            if has_balance and ("opening balance" in text or "brought forward" in text):
                seed, _ = parse_amount(cells.get("balance"))
                if seed is not None and prev_balance is None:
                    prev_balance = seed
            skip(i, "non-transaction row (balance/total/legend)")
            continue
        date_val = parse_date_any(cells.get("date"))
        if date_val is None and _row_text([cells.get("date")]) in {"date", "txn date", "transaction date"}:
            skip(i, "repeated header row")
            continue

        # --- Amounts ---
        debit = credit = None
        balance_val = None
        if has_balance:
            balance_val, _ = parse_amount(cells.get("balance"))

        if has_debit_credit:
            debit, _ = parse_amount(cells.get("debit"))
            credit, _ = parse_amount(cells.get("credit"))
        elif has_amount:
            amount_raw, side = parse_amount(cells.get("amount"))
            if has_drcr_col:
                indicator = str(cells.get("dr_cr") or "").strip().lower()
                if side is None and indicator:
                    if indicator.startswith("d"):
                        side = "debit"
                    elif indicator.startswith("c"):
                        side = "credit"
            if amount_raw is not None:
                if side == "debit":
                    debit, credit = abs(amount_raw), None
                elif side == "credit":
                    debit, credit = None, abs(amount_raw)
                elif amount_raw < 0:
                    # Signed amount column (layout 2): negative = money out.
                    debit, credit = abs(amount_raw), None
                elif amount_raw > 0 and has_balance and prev_balance is not None:
                    # Unsigned amount + balance column (layout 5): a positive
                    # number carries no direction, so the running balance
                    # decides - fell = debit, rose = credit (documented
                    # heuristic, see spec layout 5).
                    delta = balance_val - prev_balance
                    if delta < 0:
                        debit, credit = amount_raw, None
                    elif delta > 0:
                        debit, credit = None, amount_raw
                    else:
                        debit = credit = None  # balance flat - nothing happened
                elif amount_raw > 0:
                    # No balance to cross-check: trust the sign (layout 2).
                    debit, credit = None, amount_raw

        # --- Balance-delta inference (layout 5): did the balance fall or rise? ---
        if debit is None and credit is None:
            if balance_val is not None and prev_balance is not None:
                delta = balance_val - prev_balance
                if abs(delta) > 0.005:
                    # Money left the account -> debit; money entered -> credit.
                    # The amount is the delta magnitude (the amount column for
                    # this layout is either absent or empty on this row).
                    if delta < 0:
                        debit, credit = abs(delta), None
                    else:
                        debit, credit = None, delta
                    report.setdefault("warnings", []).append(
                        "Debit/credit sides inferred from balance changes "
                        "(balance-delta heuristic) - amounts may include bank charges."
                    )
            if debit is None and credit is None:
                # No date and no amount and some text -> possible continuation of
                # the previous transaction's description (multi-line narrations).
                # ONLY merge when this row is the one immediately after the last
                # parsed transaction; otherwise (e.g. a footer two rows later)
                # the row is a legend or total line and must be skipped.
                desc = str(cells.get("description") or "").strip()
                if (
                    not date_val
                    and desc
                    and last_txn is not None
                    and i == last_txn["order"] + 1  # must be the very next raw row
                ):
                    last_txn["description"] = (last_txn["description"].rstrip() + " " + desc).strip()
                    continue
                skip(i, "no valid date+amount" if not date_val else "zero amount")
                continue

        if date_val is None:
            skip(i, "missing or unparseable date")
            continue
        if debit is None and credit is None:
            skip(i, "no amount")
            continue
        if debit is not None and credit is not None:
            skip(i, "both debit and credit present")
            continue
        if debit is not None and debit <= 0:
            skip(i, "non-positive debit")
            continue
        if credit is not None and credit <= 0:
            skip(i, "non-positive credit")
            continue

        desc = re.sub(r"\s+", " ", str(cells.get("description") or "").strip())
        ref_raw = str(cells.get("reference") or "").strip()
        try:
            ref_no = str(int(float(ref_raw))) if re.fullmatch(r"\d+(\.0+)?", ref_raw) else ref_raw
        except ValueError:
            ref_no = ref_raw

        txn = {
            "date": date_val,
            "description": desc,
            "ref_no": ref_no,
            "amount": float(debit if debit is not None else credit),
            "type": "debit" if debit is not None else "credit",
            "balance": float(balance_val) if balance_val is not None else None,
            "order": i,
        }
        parsed.append(txn)
        last_txn = txn
        if balance_val is not None:
            prev_balance = balance_val

    if not parsed:
        from .errors import NoTransactions
        raise NoTransactions(
            "No valid transactions were found in this file.",
            report={**report, "rows_skipped": len(skipped), "skipped_reasons": skipped_reasons[:50]},
        )

    # --- Balance sanity check: prev balance +/- amount ~= current balance ---
    # Statements show the balance AFTER each transaction, so the running-
    # balance invariant is: cur.balance = prev.balance - cur.amount (cur is
    # a debit) or prev.balance + cur.amount (cur is a credit). Using cur's
    # amount (not prev's) is what makes this check exact; the previous
    # version applied prev's amount and false-flagged every row.
    balance_failures = 0
    balance_rows = [t for t in parsed if t["balance"] is not None]
    for prev, cur in zip(balance_rows, balance_rows[1:]):
        expected = prev["balance"] - cur["amount"] if cur["type"] == "debit" else prev["balance"] + cur["amount"]
        if abs(expected - cur["balance"]) > 1.0:  # ₹1 tolerance for rounding
            balance_failures += 1
    if balance_failures:
        report.setdefault("warnings", []).append(
            f"{balance_failures} rows failed the running-balance sanity check "
            "(previous balance +/- amount != current balance) - some rows may be out of order."
        )

    # --- Sort by date, stable within a day (original file order wins) ---
    df = pd.DataFrame(parsed)
    df["value_date"] = df["date"]  # value date not tracked separately post-mapping; date is canonical
    df = df.sort_values(["date", "order"], kind="stable").reset_index(drop=True)
    df = df[["date", "value_date", "description", "ref_no", "amount", "type", "balance"]]
    df["description"] = df["description"].astype(str)
    df["ref_no"] = df["ref_no"].astype(str)

    report["rows_parsed"] = len(df)
    report["rows_skipped"] = len(skipped)
    report["skipped_reasons"] = skipped_reasons[:100]
    report["date_range"] = {
        "from": df["date"].min().strftime("%Y-%m-%d"),
        "to": df["date"].max().strftime("%Y-%m-%d"),
    }
    return df
