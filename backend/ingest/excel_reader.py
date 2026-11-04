"""
Excel readers (.xlsx via openpyxl, legacy .xls via xlrd).

Both return the FIRST sheet that contains a detectable header row, as raw
rows in the same shape csv_reader produces - typed cells (real dates,
real numbers) are preserved because column_mapper/normalizer understand
them. Merged cells read as None for non-anchor cells and are treated as
empty strings.
"""

from .errors import CorruptFile, UnsupportedFormat


def _cells_from_xlsx(sheet):
    rows = []
    for row in sheet.iter_rows(values_only=True):
        rows.append(["" if c is None else c for c in row])
    # Drop leading/trailing fully-empty rows (spacer rows around tables).
    while rows and not any(str(c).strip() for c in rows[0]):
        rows.pop(0)
    while rows and not any(str(c).strip() for c in rows[-1]):
        rows.pop()
    return rows


def _cells_from_xls(sheet):
    rows = []
    for r in range(sheet.nrows):
        rows.append([sheet.cell_value(r, c) for c in range(sheet.ncols)])
    while rows and not any(str(c).strip() for c in rows[0]):
        rows.pop(0)
    while rows and not any(str(c).strip() for c in rows[-1]):
        rows.pop()
    return rows


def read(file_bytes: bytes, filename: str):
    """
    Returns (rows, meta). rows come from the first sheet whose content
    includes a date-ish column in its first 30 rows (cheap pre-filter);
    if none qualifies, the first non-empty sheet is used and header
    detection decides the rest.
    """
    lowered = (filename or "").lower()
    # Content first: xlsx is a zip (PK), xls is OLE2 (D0 CF).
    is_zip = file_bytes[:2] == b"PK"
    is_ole = file_bytes[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

    if is_zip or lowered.endswith(".xlsx"):
        if not is_zip:
            raise UnsupportedFormat("This file says .xlsx but is not an Excel workbook.")
        try:
            from openpyxl import load_workbook
        except ImportError as e:  # pragma: no cover
            raise CorruptFile("openpyxl is not installed") from e
        try:
            import io
            wb = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
        except Exception as e:
            raise CorruptFile(f"Could not open the Excel file: {e}") from e
        try:
            sheets = list(wb.worksheets)
            chosen = None
            for ws in sheets:
                rows = _cells_from_xlsx(ws)
                if not rows:
                    continue
                head = rows[:30]
                if any(str(c) for row in head for c in row):
                    # Cheap "does this sheet look like it has data" check;
                    # real header detection happens in column_mapper.
                    has_dateish = any(
                        isinstance(c, (int, float)) or "/" in str(c) or "-" in str(c)
                        for row in head
                        for c in row
                    )
                    if has_dateish:
                        chosen = rows
                        break
                    if chosen is None:
                        chosen = rows
            if chosen is None:
                raise CorruptFile("The workbook has no readable sheets.")
            return chosen, {"source_format": "xlsx", "sheet_count": len(sheets)}
        finally:
            try:
                wb.close()
            except Exception:
                pass

    if is_ole or lowered.endswith(".xls"):
        if not is_ole:
            raise UnsupportedFormat("This file says .xls but is not a legacy Excel workbook.")
        try:
            import io
            import xlrd
        except ImportError as e:  # pragma: no cover
            raise CorruptFile("xlrd is not installed") from e
        try:
            book = xlrd.open_workbook(file_contents=file_bytes)
        except Exception as e:
            raise CorruptFile(f"Could not open the Excel file: {e}") from e
        chosen = None
        for sheet in book.sheets():
            rows = _cells_from_xls(sheet)
            if rows:
                chosen = rows
                break
        if chosen is None:
            raise CorruptFile("The workbook has no readable sheets.")
        return chosen, {"source_format": "xls", "sheet_count": book.nsheets}

    raise UnsupportedFormat("Unsupported Excel file type.")
