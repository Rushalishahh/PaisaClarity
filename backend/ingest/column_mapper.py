"""
Column mapping - the core of the ingestion overhaul.

Real bank statements label their columns wildly differently ("Narration",
"Particulars", "Withdrawal Amt. (INR)", "Txn Date"...). This module:
  1. scans the first raw rows to FIND the header row,
  2. matches each header cell to a canonical field via a synonym dictionary
     (exact -> contains -> fuzzy), and
  3. falls back to content-based inference when headers are missing or
     unrecognised - and raises MappingRequired (never guesses silently)
     when confidence is low.

Canonical fields used downstream:
  date, value_date, description, debit, credit, amount, dr_cr, balance, reference
"""

import difflib
import re
from collections import Counter

from .errors import MappingRequired

# How many raw rows we scan looking for the header row.
MAX_HEADER_SCAN = 60
# How many data rows we inspect for the content-based fallback.
FALLBACK_ROWS = 400
# difflib threshold for fuzzy header matching.
FUZZY_THRESHOLD = 0.85

# Currency marker tokens stripped before matching ("Withdrawal Amt. (INR)").
_CURRENCY_RE = re.compile(r"\b(rs|inr|rupees)\b", re.IGNORECASE)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]")


def normalize_header(text) -> str:
    """Lowercase, drop currency markers, punctuation and everything non-alphanumeric."""
    s = str(text or "").lower()
    s = _CURRENCY_RE.sub(" ", s)
    s = _NON_ALNUM_RE.sub("", s)
    return s


# Synonym dictionary: canonical field -> normalized synonyms.
# Extended rather than shrunk from the spec list.
SYNONYMS = {
    "date": [
        "txndate", "transactiondate", "trandate", "transdate", "postingdate",
        "postdate", "date", "txndt", "txnDate".lower(), "transactiondt",
        "datetxn", "dateoftransaction",
    ],
    "value_date": ["valuedate", "valuedt", "valdt", "valued"],
    "description": [
        "description", "narration", "particulars", "transactionremarks",
        "remarks", "details", "transactiondetails", "transactiondescription",
        "narrationdetails", "desc", "transactionparticulars", "descriptionremarks",
    ],
    "debit": [
        "withdrawalamt", "withdrawals", "withdrawal", "debit", "debitamount",
        "dr", "dramount", "amountdebited", "withdrawalamount", "debitamt",
        "withdrawaldr", "payments", "payment", "paidout", "moneyout",
    ],
    "credit": [
        "depositamt", "deposits", "deposit", "credit", "creditamount",
        "cr", "cramount", "amountcredited", "depositamount", "creditamt",
        "receipts", "receipt", "paidin", "moneyin",
    ],
    "amount": ["amount", "transactionamount", "txnamount", "amt", "transactionvalue", "value"],
    "dr_cr": [
        "drcr", "crdr", "type", "transactiontype", "debitcredit", "txntype",
        "drcrindicator", "indicator", "entrytype",
    ],
    "balance": [
        "closingbalance", "balance", "runningbalance", "availablebalance",
        "bal", "closingbal", "accbalance", "accountbalance", "balanceamt",
        "currentbalance", "ledgerbalance",
    ],
    "reference": [
        "refno", "chqno", "chequeno", "refnochequeno", "instrumentno", "utr",
        "transactionid", "ref", "chqrefno", "chequerefno", "refchqno",
        "reference", "refnumber",
    ],
}

# Flat lookup: normalized synonym -> canonical (first definition wins,
# so keep the list order meaningful).
_FLAT = {}
for _canon, _syns in SYNONYMS.items():
    for _s in _syns:
        _FLAT.setdefault(_s, _canon)

# Canonical fields that MUST be present for a header row to count.
_REQUIRED_FOR_HEADER = ("date", "description")


def match_cell(text):
    """
    Match one raw header cell to a canonical field name, or None.
    Tiers: exact normalized -> prefix/contains (both directions, min length 4)
    -> fuzzy via difflib ratio >= 0.85.
    """
    key = normalize_header(text)
    if not key:
        return None
    if key in _FLAT:
        return _FLAT[key]
    # Contains: "withdrawalamtinr" contains "withdrawalamt"; also a cell
    # truncated mid-word ("Ref No./Cheque") is a PREFIX of a synonym.
    for syn, canon in _FLAT.items():
        if len(syn) >= 4 and (syn in key or (len(key) >= 4 and key in syn)):
            return canon
    # Fuzzy (catches OCR-ish and spacing artefacts).
    best, best_ratio = None, 0.0
    for syn, canon in _FLAT.items():
        ratio = difflib.SequenceMatcher(None, key, syn).ratio()
        if ratio > best_ratio:
            best, best_ratio = canon, ratio
    return best if best_ratio >= FUZZY_THRESHOLD else None


def _score_header_row(cells):
    """
    Score how header-like a raw row is. Returns (score, mapping) where
    mapping is {canonical: column_index}. A row must match date +
    description + at least one amount-ish column (debit/credit/amount)
    to score at all.
    """
    mapping = {}
    for idx, cell in enumerate(cells):
        canon = match_cell(cell)
        if canon and canon not in mapping:
            mapping[canon] = idx

    # Banks that only print a value date (no txn date): promote it to the
    # primary date column as a fallback (spec: value date only when no txn date).
    if "date" not in mapping and "value_date" in mapping:
        mapping["date"] = mapping.pop("value_date")

    if not all(f in mapping for f in _REQUIRED_FOR_HEADER):
        return 0, mapping
    if not any(f in mapping for f in ("debit", "credit", "amount")):
        return 0, mapping

    score = 0
    score += 3  # passed the mandatory gates
    score += 2 if "date" in mapping else 0
    score += 2 if "description" in mapping else 0
    # Prefer explicit debit+credit pairs over a bare amount column.
    score += 3 if ("debit" in mapping and "credit" in mapping) else 0
    score += 1 if "amount" in mapping else 0
    score += 2 if "balance" in mapping else 0
    score += 1 if "reference" in mapping else 0
    score += 1 if "value_date" in mapping and mapping["value_date"] != mapping["date"] else 0
    return score, mapping


def find_header(rows):
    """
    Scan the first MAX_HEADER_SCAN rows; return (header_index, mapping) for
    the best-scoring row, or (None, {}) if nothing qualifies. Ties go to the
    earliest row.
    """
    best_idx, best_score, best_mapping = None, 0, {}
    for i, row in enumerate(rows[:MAX_HEADER_SCAN]):
        score, mapping = _score_header_row(row)
        if score > best_score:
            best_idx, best_score, best_mapping = i, score, mapping
    return best_idx, best_mapping


def resolve_user_mapping(header_cells, column_mapping):
    """
    Resolve a UI-supplied mapping like {"date": "Withdrawal Amt.", ...} into
    {canonical: column_index}. Values are raw header texts as displayed in
    the mapping modal; matched by normalized equality first, then contains.
    Raises MappingRequired when a required field cannot be resolved.
    """
    normalized_cells = [normalize_header(c) for c in header_cells]
    resolved = {}
    for canon, raw in (column_mapping or {}).items():
        if not raw:
            continue
        want = normalize_header(raw)
        idx = None
        for i, cell in enumerate(normalized_cells):
            if cell == want:
                idx = i
                break
        if idx is None:
            for i, cell in enumerate(normalized_cells):
                if cell and want and (want in cell or cell in want):
                    idx = i
                    break
        if idx is not None:
            resolved[canon] = idx
    missing = [f for f in _REQUIRED_FOR_HEADER if f not in resolved]
    if missing or not any(f in resolved for f in ("debit", "credit", "amount", "balance")):
        raise MappingRequired(
            "The chosen columns don't cover a date, a description and an amount field.",
            headers=[str(c) for c in header_cells],
        )
    return resolved


def _is_mostly_dates(values):
    """A column is a date column when >=80% of its non-empty cells parse as dates."""
    from .normalizer import parse_date_any  # local import avoids a cycle

    non_empty = [v for v in values if str(v).strip() != ""]
    if len(non_empty) < 3:
        return False
    hits = sum(1 for v in non_empty if parse_date_any(v) is not None)
    return hits / len(non_empty) >= 0.8


def _is_mostly_numeric(values):
    from .normalizer import parse_amount  # local import avoids a cycle

    non_empty = [v for v in values if str(v).strip() != ""]
    if len(non_empty) < 3:
        return False, 0.0
    hits = 0
    for v in non_empty:
        val, _side = parse_amount(v)
        if val is not None:
            hits += 1
    return hits / len(non_empty) >= 0.8, hits / len(non_empty)


def content_fallback(rows, header_index):
    """
    Infer columns from CONTENT when headers are missing/unrecognised.

    Heuristics (documented for the owner):
      - date: leftmost column whose cells parse as dates >=80% of the time
      - description: non-date column with the longest average text
      - numeric columns: >=80% numeric cells
      - debit/credit: a SPARSE numeric column (most cells empty - a debit
        row has no credit value and vice versa)
      - balance: the DENSE numeric column with the strongest trend across
        row order (running balances move smoothly); never negative preferred
      - single dense numeric column + balance -> signed amount column

    Low confidence (can't satisfy date+description+amount) raises
    MappingRequired - we never guess silently.
    """
    sample = rows[header_index + 1 : header_index + 1 + FALLBACK_ROWS] if header_index is not None else rows[-FALLBACK_ROWS:]
    if not sample:
        raise MappingRequired("No data rows found to infer columns from.", headers=[])
    width = max(len(r) for r in sample)
    columns = [[r[i] if i < len(r) else "" for r in sample] for i in range(width)]

    date_cols = [i for i, col in enumerate(columns) if _is_mostly_dates(col)]
    if not date_cols:
        raise MappingRequired(
            "Could not find a column of dates in this file.",
            headers=[str(c) for c in rows[header_index]] if header_index is not None else [],
            sample_rows=[[str(c) for c in r] for r in sample[:3]],
        )
    date_idx = date_cols[0]

    # Description: longest average text length among stringy, non-date columns.
    desc_idx, desc_score = None, 0.0
    for i, col in enumerate(columns):
        if i == date_idx or (len(date_cols) > 1 and i in date_cols[1:]):
            continue
        texts = [str(v) for v in col if str(v).strip() != ""]
        if not texts:
            continue
        avg_len = sum(len(t) for t in texts) / len(texts)
        if avg_len > desc_score:
            desc_idx, desc_score = i, avg_len
    if desc_idx is None or desc_score < 3:
        raise MappingRequired(
            "Could not find a description column in this file.",
            headers=[str(c) for c in rows[header_index]] if header_index is not None else [],
            sample_rows=[[str(c) for c in r] for r in sample[:3]],
        )

    numeric = []
    for i, col in enumerate(columns):
        if i in (date_idx, desc_idx):
            continue
        is_num, frac = _is_mostly_numeric(col)
        if is_num:
            non_empty = [v for v in col if str(v).strip() != ""]
            numeric.append((i, non_empty, frac))

    mapping = {"date": date_idx, "description": desc_idx}
    if len(date_cols) > 1:
        mapping["value_date"] = date_cols[1]

    # Split numeric columns into sparse (amount-like) and dense (balance-like).
    sparse = [n for n in numeric if len(n[1]) < 0.7 * len(sample)]
    dense = [n for n in numeric if len(n[1]) >= 0.7 * len(sample)]

    if sparse:
        sparse.sort(key=lambda n: n[0])
        if len(sparse) >= 2:
            mapping["debit"], mapping["credit"] = sparse[0][0], sparse[1][0]
        else:
            # One sparse column only: cannot tell debit from credit -> ask the user.
            raise MappingRequired(
                "Found one amount column but can't tell debits from credits - "
                "please map the columns manually.",
                headers=[str(c) for c in rows[header_index]] if header_index is not None else [],
                sample_rows=[[str(c) for c in r] for r in sample[:3]],
            )
        if dense:
            # Balance = dense column with strongest |trend| across row order.
            def trend_strength(idx):
                vals = []
                for r_i, r in enumerate(sample):
                    v = r[idx] if idx < len(r) else ""
                    from .normalizer import parse_amount as _pa
                    val, _ = _pa(v)
                    if val is not None:
                        vals.append((r_i, val))
                if len(vals) < 3:
                    return 0.0
                n = len(vals)
                mean_x = sum(x for x, _ in vals) / n
                mean_y = sum(y for _, y in vals) / n
                cov = sum((x - mean_x) * (y - mean_y) for x, y in vals)
                var_x = sum((x - mean_x) ** 2 for x, _ in vals)
                var_y = sum((y - mean_y) ** 2 for _, y in vals)
                if var_x == 0 or var_y == 0:
                    return 0.0
                return abs(cov / ((var_x ** 0.5) * (var_y ** 0.5)))

            dense.sort(key=lambda n: trend_strength(n[0]), reverse=True)
            mapping["balance"] = dense[0][0]
            remaining = [d[0] for d in dense[1:]]
            if remaining:
                mapping["amount"] = remaining[0]
    elif dense:
        # Layout 5: one amount column + balance column. Signed values
        # (negative = money out) and the balance-delta heuristic are
        # handled in normalizer. Pick the two densest numeric columns;
        # balance = the one with the stronger trend.
        def trend_strength(idx):
            from .normalizer import parse_amount as _pa
            vals = []
            for r_i, r in enumerate(sample):
                v = r[idx] if idx < len(r) else ""
                val, _ = _pa(v)
                if val is not None:
                    vals.append((r_i, val))
            if len(vals) < 3:
                return 0.0
            n = len(vals)
            mean_x = sum(x for x, _ in vals) / n
            mean_y = sum(y for _, y in vals) / n
            cov = sum((x - mean_x) * (y - mean_y) for x, y in vals)
            var_x = sum((x - mean_x) ** 2 for x, _ in vals)
            var_y = sum((y - mean_y) ** 2 for _, y in vals)
            if var_x == 0 or var_y == 0:
                return 0.0
            return abs(cov / ((var_x ** 0.5) * (var_y ** 0.5)))

        dense.sort(key=lambda n: trend_strength(n[0]), reverse=True)
        mapping["balance"] = dense[0][0]
        if len(dense) >= 2:
            mapping["amount"] = dense[1][0]
        else:
            raise MappingRequired(
                "Found a balance column but no amount column - please map the columns manually.",
                headers=[str(c) for c in rows[header_index]] if header_index is not None else [],
                sample_rows=[[str(c) for c in r] for r in sample[:3]],
            )
    else:
        raise MappingRequired(
            "Could not find any amount columns in this file.",
            headers=[str(c) for c in rows[header_index]] if header_index is not None else [],
            sample_rows=[[str(c) for c in r] for r in sample[:3]],
        )

    return mapping, "content_fallback"


def build_mapping_used(raw_header_cells, mapping):
    """Human-readable {canonical: raw header text} for the ingest report."""
    used = {}
    for canon, idx in mapping.items():
        if 0 <= idx < len(raw_header_cells):
            used[canon] = str(raw_header_cells[idx])
    return used
