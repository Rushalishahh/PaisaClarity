"""
CSV raw-row reader.

Banks do not export clean CSVs: account address, "Statement period" and
other metadata lines sit ABOVE the header row, and totals/legends sit BELOW
the data. So we do NOT use pandas.read_csv with a fixed header - we decode
the bytes, sniff the delimiter, and hand back raw rows; header location is
column_mapper's job.
"""

import csv
import io

from .errors import CorruptFile

# Encoding fallback chain: Excel exports are often utf-8-sig (BOM) or the
# Windows-1252 "ANSI" codepage; latin-1 never fails, so it is the last resort.
ENCODINGS = ("utf-8-sig", "utf-8", "cp1252", "latin-1")


def decode(file_bytes: bytes):
    last_err = None
    for enc in ENCODINGS:
        try:
            return file_bytes.decode(enc), enc
        except (UnicodeDecodeError, ValueError) as e:
            last_err = e
    raise CorruptFile(f"Could not decode the file as text ({last_err}). Is it really a CSV?")


def sniff_dialect(text: str):
    """
    Try csv.Sniffer for the delimiter, but banks' metadata lines confuse it,
    so we also brute-force the four common delimiters and keep the one that
    parses the most columns consistently. Falls back to plain comma.
    """
    sample = text[:65536]
    candidates = [",", ";", "\t", "|"]
    best = None
    best_score = -1
    for delim in candidates:
        try:
            rows = list(csv.reader(io.StringIO(sample), delimiter=delim, quotechar='"'))
        except csv.Error:
            continue
        if not rows:
            continue
        # Score = number of columns in the widest row, penalised when rows
        # have wildly different widths (wrong delimiter usually fragments
        # every line into single-column rows).
        widths = [len(r) for r in rows if r]
        if not widths:
            continue
        score = max(widths) - (max(widths) - min(widths)) * 0.5
        if score > best_score:
            best_score = score
            best = delim
    return best or ","


def read(file_bytes: bytes):
    """
    Returns (rows, meta): rows is a list of list-of-str (ragged allowed,
    quoted multi-line fields handled by the csv module), meta records the
    encoding and delimiter chosen for the ingest report.
    """
    text, encoding = decode(file_bytes)
    delimiter = sniff_dialect(text)
    rows = []
    for row in csv.reader(io.StringIO(text), delimiter=delimiter, quotechar='"'):
        # Drop fully-empty rows but keep ragged ones (padded later).
        if row and any(str(c).strip() for c in row):
            rows.append([str(c) for c in row])
    return rows, {"encoding": encoding, "delimiter": delimiter}
