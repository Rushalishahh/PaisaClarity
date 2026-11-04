"""
PDF statement reader (text-based PDFs only - NO OCR).

Three extraction strategies, tried in order; the first that produces a
recognizable header (via column_mapper) and >= 3 data rows wins:
  1. pdfplumber's line-based table detector (page.extract_tables())
  2. its text-based table strategy (extract_tables with text settings
     using vertical_strategy="text", horizontal_strategy="text")
  3. borderless fallback: reconstruct rows from extract_words grouped by
     y-position.
     NOTE: Strategy 3 is NOT reliable for borderless PDFs - it produces
     ragged column splits and is not maintained. Borderless PDFs are only
     supported when strategy 1 or 2 successfully detects the table.

Tables are stitched across pages; repeated headers and footers are dropped.
"""

import io
import re

from .errors import CorruptFile, PasswordRequired, ScannedPdfUnsupported, WrongPassword
from . import column_mapper

MAX_PDF_PAGES = 200  # safety cap - a pathological upload must not hang a worker

_FOOTER_RE = re.compile(
    r"^(page\s*\d+|statement\s*period|account\s*statement|generated\s*on|"
    r"continued|end\s*of\s*statement|this\s*is\s*a\s*computer\s*generated)",
    re.IGNORECASE,
)


def _is_password_error(exc):
    """True when pdfminer/pdfplumber signals an encrypted-but-unlocked failure."""
    txt_parts = [str(exc), repr(exc), type(exc).__name__]
    if hasattr(exc, "args"):
        for arg in exc.args:
            txt_parts.extend([str(arg), repr(arg), type(arg).__name__])
    txt = " ".join(txt_parts).lower()
    return "password" in txt or "encrypt" in txt or "pdfpasswordincorrect" in txt


def _open_pdf(file_bytes, password):
    try:
        import pdfplumber
        pdf = pdfplumber.open(io.BytesIO(file_bytes), password=password or "")
    except Exception as e:
        msg = str(e)
        # pdfminer surfaces encryption state in different exception types;
        # sniff the exception details so we can answer precisely.
        if _is_password_error(e):
            if password:
                raise WrongPassword("The password you entered is not correct for this PDF.")
            raise PasswordRequired("This PDF is password protected. Enter the password your bank uses (often your PAN or date of birth).")
        raise CorruptFile(f"Could not open the PDF: {msg}")
    return pdf


def _page_text(pdf, password=None):
    """
    Extract all text across pages. Re-raises password errors so they surface
    as clean PasswordRequired / WrongPassword even when encryption is enforced
    per-page (some PDF producers open fine but fail on content access).
    """
    parts = []
    for page in pdf.pages[:MAX_PDF_PAGES]:
        try:
            parts.append(page.extract_text() or "")
        except Exception as e:
            if _is_password_error(e):
                if password:
                    raise WrongPassword("The password you entered is not correct for this PDF.")
                raise PasswordRequired(
                    "This PDF is password protected. Enter the password your bank uses "
                    "(often your PAN or date of birth)."
                )
            parts.append("")
    return "\n".join(parts)


def _row_is_header_like(cells):
    matched = sum(1 for c in cells if column_mapper.match_cell(c))
    return matched >= 3 and any(column_mapper.match_cell(c) == "date" for c in cells)


def _rows_from_line_tables(pdf):
    rows = []
    for page in pdf.pages[:MAX_PDF_PAGES]:
        try:
            tables = page.extract_tables() or []
        except Exception:
            continue
        for table in tables:
            for row in table:
                rows.append(["" if c is None else str(c) for c in row])
    return rows


def _rows_from_text_tables(pdf):
    """
    Strategy 2: pdfplumber text-alignment table detection.
    Uses vertical_strategy="text" + horizontal_strategy="text" so columns
    are inferred from text alignment rather than drawn lines - this is the
    primary path for borderless PDFs.
    """
    rows = []
    # pdfplumber >= 0.7 accepts these as the table_settings keys;
    # snap_tolerance tightens column grouping for narrow-column statements.
    tsp = {
        "vertical_strategy": "text",
        "horizontal_strategy": "text",
        "snap_tolerance": 3,
        "join_tolerance": 3,
        "edge_min_length": 3,
        "min_words_vertical": 3,
        "min_words_horizontal": 1,
        "intersection_tolerance": 3,
        "text_tolerance": 3,
        "text_x_tolerance": 3,
        "text_y_tolerance": 3,
    }
    for page in pdf.pages[:MAX_PDF_PAGES]:
        try:
            tables = page.extract_tables(table_settings=tsp) or []
        except Exception:
            # Strategy 2 failing is not fatal; strategy 3 will be tried.
            continue
        for table in tables:
            for row in table:
                rows.append(["" if c is None else str(c) for c in row])
    return rows


def _rows_from_words(pdf):
    """
    Strategy 3 for borderless layouts: group words into visual rows by
    y-position, then split each row into columns using x-gaps. Column
    boundaries are derived from the header row's word positions.
    Returns flat list of rows across pages, or [] if nothing usable.
    """
    rows = []
    for page in pdf.pages[:MAX_PDF_PAGES]:
        try:
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
        except Exception:
            continue
        if not words:
            continue
        # Group words by rounded top coordinate (words on one visual line).
        lines = {}
        for w in words:
            key = round(w["top"] / 3) * 3  # 3pt tolerance
            lines.setdefault(key, []).append(w)
        page_rows = []
        for key in sorted(lines):
            ws = sorted(lines[key], key=lambda w: w["x0"])
            page_rows.append([w["text"] for w in ws])
        # Find the header line among this page's rows.
        header_i = None
        for i, r in enumerate(page_rows):
            if _row_is_header_like(r):
                header_i = i
                break
        if header_i is None:
            continue
        header = page_rows[header_i]
        # Column boundaries: midpoints between the last word of column i and
        # the first word of column i+1 in the HEADER. Data words land in the
        # column whose range contains their x0. Header words can wrap, so we
        # cluster header words by gaps > ~2 characters.
        # Simpler robust approach: split every row (header included) by the
        # LARGEST gaps and let column_mapper find the header.
        rows.extend([" ".join(page_rows[header_i : header_i + 1]), *page_rows[header_i + 1 :]])
        break  # first page with a recognizable header defines the split style
    return rows


def _extract_rows(pdf):
    for name, fn in (("lines", _rows_from_line_tables), ("text", _rows_from_text_tables), ("words", _rows_from_words)):
        rows = fn(pdf)
        if not rows:
            continue
        # The header must be findable within the first 60 rows of output.
        header_idx, _ = column_mapper.find_header(rows)
        if header_idx is not None:
            # Need at least 3 data rows after the header.
            if sum(1 for r in rows[header_idx + 1 : header_idx + 30] if any(str(c).strip() for c in r)) >= 3:
                return rows, name
    return None, None


def read(file_bytes: bytes, password=None):
    """
    Returns (rows, meta) or raises IngestError subclasses. rows is the flat
    raw-row list across all pages; meta records the strategy used.

    Password errors are surfaced as PasswordRequired / WrongPassword whether
    they occur at open-time (most PDFs) or on first page access (some producers
    that defer decryption enforcement).
    """
    pdf = _open_pdf(file_bytes, password)
    try:
        # Scanned PDF = no text anywhere (image-only pages).
        # Pass `password` so page-level encryption errors become clean errors.
        text = _page_text(pdf, password=password)
        if not text.strip():
            raise ScannedPdfUnsupported(
                "This looks like a scanned PDF. Please download the text-based "
                "PDF/CSV/Excel version from your bank's net banking."
            )

        rows, strategy = _extract_rows(pdf)
        if rows is None:
            raise CorruptFile(
                "PDF text was found but no transaction table could be detected. "
                "Try the CSV/Excel export from your bank, or map the columns manually."
            )
        return rows, {"source_format": "pdf", "strategy": strategy}
    finally:
        pdf.close()
