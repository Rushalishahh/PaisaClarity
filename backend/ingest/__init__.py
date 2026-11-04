"""
Statement ingestion package.

parse_statement(file_bytes, filename, password=None, column_mapping=None)
  -> ParseResult(transactions: DataFrame, report: dict)

Dispatch is by CONTENT (magic bytes), not extension:
  %PDF            -> pdf_reader
  PK (zip)        -> xlsx via excel_reader
  OLE2 header     -> xls  via excel_reader
  otherwise       -> delimited text via csv_reader

The output DataFrame matches the canonical contract downstream code has
always consumed (date/value_date/description/ref_no/amount/type/balance),
so categorizer.py and insights.py work unchanged.
"""

import pandas as pd

from . import column_mapper, csv_reader, excel_reader, normalizer, pdf_reader
from .errors import CorruptFile, UnsupportedFormat

MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB - enforced by the API layer too


class ParseResult:
    def __init__(self, transactions: pd.DataFrame, report: dict):
        self.transactions = transactions
        self.report = report


def _sniff_format(file_bytes: bytes, filename: str) -> str:
    if file_bytes[:4] == b"%PDF":
        return "pdf"
    if file_bytes[:2] == b"PK":
        return "xlsx"
    if file_bytes[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return "xls"
    # Not a known binary - decide between delimited text and nothing.
    ext = (filename or "").lower().rsplit(".", 1)[-1] if "." in (filename or "") else ""
    if ext in ("csv", "txt", ""):
        return "csv"
    # Extension claims excel/pdf but the bytes disagree -> reject clearly.
    raise UnsupportedFormat(
        f"This file is named .{ext} but its contents are not a {ext.upper()} file. "
        "Re-export or re-download the statement and try again."
    )


def parse_statement(file_bytes: bytes, filename: str, password=None, column_mapping=None) -> ParseResult:
    if len(file_bytes) > MAX_FILE_BYTES:
        from .errors import FileTooLarge
        raise FileTooLarge("File is larger than the 10 MB limit.")

    if not file_bytes:
        raise CorruptFile("The uploaded file is empty.")

    source_format = _sniff_format(file_bytes, filename)

    if source_format == "pdf":
        rows, meta = pdf_reader.read(file_bytes, password=password)
    elif source_format in ("xlsx", "xls"):
        rows, meta = excel_reader.read(file_bytes, filename)
    else:
        rows, meta = csv_reader.read(file_bytes)

    report = {
        "source_format": meta.get("source_format", source_format),
        "rows_found": len(rows),
        "rows_parsed": 0,
        "rows_skipped": 0,
        "skipped_reasons": [],
        "date_range": None,
        "mapping_used": {},
        "warnings": list(meta.get("warnings", [])),
    }
    if meta.get("encoding"):
        report["encoding"] = meta["encoding"]
    if meta.get("delimiter"):
        report["delimiter"] = meta["delimiter"]
    if meta.get("strategy"):
        report["warnings"].append(f"PDF table extracted using the '{meta['strategy']}' strategy.")
        report["strategy"] = meta["strategy"]

    header_index, mapping = column_mapper.find_header(rows)

    if header_index is None and not column_mapping:
        # No recognizable header: give the content fallback a chance before
        # asking the user (empty/blank files are handled by the fallback's
        # errors).
        sample_rows = [[str(c) for c in r] for r in rows[:3]]
        try:
            mapping, how = column_mapper.content_fallback(rows, None)
            header_index = -1  # no header row; all rows are data
            report["mapping_used"]["method"] = how
        except Exception:
            from .errors import MappingRequired
            raise MappingRequired(
                "We couldn't identify the columns in this file. "
                "Please map them manually.",
                headers=rows[0] if rows else [],
                sample_rows=sample_rows,
            )
    elif column_mapping:
        header_cells = rows[header_index] if header_index is not None else rows[0]
        mapping = column_mapper.resolve_user_mapping(header_cells, column_mapping)
        report["mapping_used"]["method"] = "user_provided"
    else:
        report["mapping_used"]["method"] = "header_synonyms"

    # A user-provided mapping but no recognizable header row: the mapping
    # resolves against the first row; treat everything as data.
    if header_index is None:
        header_index = -1

    report["mapping_used"]["columns"] = column_mapper.build_mapping_used(
        rows[header_index] if header_index >= 0 else (rows[0] if rows else []), mapping
    )

    df = normalizer.normalize_rows(rows, mapping, header_index, report)

    # Opening/closing balance: first/last parsed balance values, when present.
    balances = df["balance"].dropna()
    if not balances.empty:
        report["opening_balance"] = float(balances.iloc[0])
        report["closing_balance"] = float(balances.iloc[-1])

    return ParseResult(transactions=df, report=report)
