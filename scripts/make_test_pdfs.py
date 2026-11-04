"""
Generate backend/tests/fixtures/pdf/*.pdf test fixtures.

Produces five PDFs (all synthetic, no real customer data):
  statement_bordered.pdf    - single page, grid-line table (strategy 1)
  statement_borderless.pdf  - single page, no grid lines (strategy 2)
  statement_multipage.pdf   - two pages, repeated headers, multi-line descriptions
  statement_password.pdf    - password-protected with password "acme123" (pikepdf)
  statement_scanned.pdf     - image-only page, no text objects (triggers ScannedPdfUnsupported)

Run from the repo root:
    backend\\venv\\Scripts\\python scripts\\make_test_pdfs.py
"""

import io
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(REPO, "backend")
PDF_DIR = os.path.join(BACKEND, "tests", "fixtures", "pdf")
sys.path.insert(0, BACKEND)

os.makedirs(PDF_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Shared fixture data  (fully synthetic)
# ---------------------------------------------------------------------------

HEADER = [
    "Txn Date", "Value Date", "Description",
    "Ref No./Cheque No.", "Withdrawal Amt.", "Deposit Amt.", "Closing Balance",
]

# A handful of rows that the normalizer can parse cleanly.
DATA_ROWS = [
    ("03/01/2026", "03/01/2026", "NEFT RENT LANDLORD",      "", "18000.00", "",        "42000.00"),
    ("05/01/2026", "05/01/2026", "ACH DR NETFLIX",           "", "649.00",   "",        "41351.00"),
    ("05/01/2026", "05/01/2026", "UPI-SWIGGY-356787",        "", "311.61",   "",        "41039.39"),
    ("05/01/2026", "05/01/2026", "UPI-ZOMATO-872246",        "", "316.62",   "",        "40722.77"),
    ("05/01/2026", "05/01/2026", "UPI-BIGBASKET-210345",     "", "1452.00",  "",        "39270.77"),
    ("10/01/2026", "10/01/2026", "NEFT SALARY ACME CORP",    "", "",         "45000.00","84270.77"),
    ("15/01/2026", "15/01/2026", "POS PETROL PUMP 987654",   "", "1800.00",  "",        "82470.77"),
    ("15/01/2026", "15/01/2026", "UPI-UBER-654321",          "", "245.00",   "",        "82225.77"),
    ("15/01/2026", "15/01/2026", "UPI-AMAZON-112233",        "", "1250.00",  "",        "80975.77"),
    ("25/01/2026", "25/01/2026", "UPI-DMART-445566",         "", "2100.00",  "",        "78875.77"),
    ("25/01/2026", "25/01/2026", "UPI-AIRTEL-778899",        "", "399.00",   "",        "78476.77"),
    ("25/01/2026", "25/01/2026", "UPI-MYNTRA-334455",        "", "899.00",   "",        "77577.77"),
]

# Multi-line description rows: the continuation row has no date/amount.
# (Only for the multipage fixture to exercise multi-line narration handling.)
DATA_ROWS_MULTILINE = [
    ("03/01/2026", "03/01/2026", "NEFT RENT LANDLORD",               "", "18000.00", "",        "42000.00"),
    ("",           "",           "Ref: 2026/ACME/00001",              "", "",         "",        ""),  # continuation
    ("05/01/2026", "05/01/2026", "ACH DR NETFLIX",                    "", "649.00",   "",        "41351.00"),
    ("05/01/2026", "05/01/2026", "UPI-SWIGGY-356787",                 "", "311.61",   "",        "41039.39"),
    ("05/01/2026", "05/01/2026", "UPI-ZOMATO-872246",                 "", "316.62",   "",        "40722.77"),
    ("05/01/2026", "05/01/2026", "UPI-BIGBASKET-210345",              "", "1452.00",  "",        "39270.77"),
    ("10/01/2026", "10/01/2026", "NEFT SALARY ACME CORP",             "", "",         "45000.00","84270.77"),
    ("",           "",           "Feb payroll, EMP-007",              "", "",         "",        ""),  # continuation
]

FOOTER_ROWS_PAGE2 = [
    ("15/01/2026", "15/01/2026", "POS PETROL PUMP 987654",            "", "1800.00",  "",        "82470.77"),
    ("15/01/2026", "15/01/2026", "UPI-UBER-654321",                   "", "245.00",   "",        "82225.77"),
    ("15/01/2026", "15/01/2026", "UPI-AMAZON-112233",                 "", "1250.00",  "",        "80975.77"),
    ("25/01/2026", "25/01/2026", "UPI-DMART-445566",                  "", "2100.00",  "",        "78875.77"),
    ("25/01/2026", "25/01/2026", "UPI-AIRTEL-778899",                 "", "399.00",   "",        "78476.77"),
    ("25/01/2026", "25/01/2026", "UPI-MYNTRA-334455",                 "", "899.00",   "",        "77577.77"),
]

# ---------------------------------------------------------------------------
# PDF builders
# ---------------------------------------------------------------------------

def _table_style_bordered(colors):
    from reportlab.platypus import TableStyle
    return TableStyle([
        ("GRID",     (0, 0), (-1, -1), 0.4, colors.black),
        ("FONTNAME", (0, 0), (-1,  0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
    ])


def _table_style_borderless(colors):
    from reportlab.platypus import TableStyle
    return TableStyle([
        ("FONTNAME", (0, 0), (-1,  0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
    ])


COL_WIDTHS = [55, 55, 140, 65, 65, 65, 70]


def make_bordered(path):
    """Single-page bordered table — strategy 1 (line-based) should detect it."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Spacer, Table, Paragraph

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=30, bottomMargin=30,
                            leftMargin=30, rightMargin=20)
    story = [
        Paragraph("ACME BANK — Account Statement", None),
        Spacer(1, 8),
        Table([list(HEADER)] + [list(r) for r in DATA_ROWS],
              colWidths=COL_WIDTHS, repeatRows=1,
              style=_table_style_bordered(colors)),
    ]
    doc.build(story)
    with open(path, "wb") as f:
        f.write(buf.getvalue())
    print(f"  written: {os.path.relpath(path, REPO)}")


def make_borderless(path):
    """Single-page borderless table — no grid lines, so strategy 2 (text) handles it."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Spacer, Table, Paragraph

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=30, bottomMargin=30,
                            leftMargin=30, rightMargin=20)
    story = [
        Paragraph("ACME BANK — Account Statement", None),
        Spacer(1, 8),
        Table([list(HEADER)] + [list(r) for r in DATA_ROWS[:8]],
              colWidths=COL_WIDTHS, repeatRows=1,
              style=_table_style_borderless(colors)),
    ]
    doc.build(story)
    with open(path, "wb") as f:
        f.write(buf.getvalue())
    print(f"  written: {os.path.relpath(path, REPO)}")


def make_multipage(path):
    """
    Two-page PDF:
    - Page 1: bordered table with header + DATA_ROWS_MULTILINE (includes
      continuation rows and a repeated header row on the second page).
    - Page 2: the header row is repeated (as real bank PDFs do) then
      FOOTER_ROWS_PAGE2 rows.
    Tests: repeated-header dropping, multi-line narration stitching, page stitching.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Spacer, Table, Paragraph, PageBreak

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=30, bottomMargin=30,
                            leftMargin=30, rightMargin=20)
    style = _table_style_bordered(colors)

    p1_rows = [list(HEADER)] + [list(r) for r in DATA_ROWS_MULTILINE]
    # Page 2 repeats the header (as pdfplumber sees it after page break).
    p2_rows = [list(HEADER)] + [list(r) for r in FOOTER_ROWS_PAGE2]

    story = [
        Paragraph("ACME BANK — Account Statement (Page 1 of 2)", None),
        Spacer(1, 8),
        Table(p1_rows, colWidths=COL_WIDTHS, style=style),
        PageBreak(),
        Paragraph("ACME BANK — Account Statement (Page 2 of 2)", None),
        Spacer(1, 8),
        Table(p2_rows, colWidths=COL_WIDTHS, style=style),
    ]
    doc.build(story)
    with open(path, "wb") as f:
        f.write(buf.getvalue())
    print(f"  written: {os.path.relpath(path, REPO)}")


def make_password(path, password="acme123"):
    """
    Password-protected PDF.  Requires pikepdf (listed in requirements-dev.txt).
    Writes an unprotected tmp file first, then re-saves with encryption.
    If pikepdf is not installed, writes an empty file with a warning.
    """
    tmp = path + ".tmp"
    make_bordered(tmp)
    try:
        import pikepdf
        with pikepdf.open(tmp) as pdf:
            pdf.save(path, encryption=pikepdf.Encryption(
                user=password, owner=password, R=4,
            ))
        os.remove(tmp)
        print(f"  written (password={password!r}): {os.path.relpath(path, REPO)}")
    except ImportError:
        os.remove(tmp)
        # Write a zero-byte placeholder so the fixture path exists.
        open(path, "wb").write(b"")
        print(f"  WARNING: pikepdf not installed — {os.path.relpath(path, REPO)} is empty; "
              "install pikepdf to generate a real password-protected fixture.")


def make_scanned(path):
    """
    Image-only PDF: one page with drawn rectangles, zero text objects.
    pdfplumber.extract_text() returns '' -> ScannedPdfUnsupported is raised.
    """
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.lib.pagesizes import A4

    buf = io.BytesIO()
    c = Canvas(buf, pagesize=A4)
    # Draw shapes that look like a table scan; do NOT add any text.
    w, h = A4
    c.setStrokeColorRGB(0.3, 0.3, 0.3)
    c.setFillColorRGB(0.95, 0.95, 0.95)
    c.rect(40, h - 120, w - 80, 90, fill=1)   # header band
    c.setFillColorRGB(1, 1, 1)
    for y in range(int(h) - 200, 100, -30):
        c.rect(40, y, w - 80, 28, fill=1)
    c.showPage()
    c.save()
    with open(path, "wb") as f:
        f.write(buf.getvalue())
    print(f"  written (image-only / scanned): {os.path.relpath(path, REPO)}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    print("Generating PDF fixtures ...")
    make_bordered(  os.path.join(PDF_DIR, "statement_bordered.pdf"))
    make_borderless(os.path.join(PDF_DIR, "statement_borderless.pdf"))
    make_multipage( os.path.join(PDF_DIR, "statement_multipage.pdf"))
    make_password(  os.path.join(PDF_DIR, "statement_password.pdf"))
    make_scanned(   os.path.join(PDF_DIR, "statement_scanned.pdf"))
    print("Done.")


if __name__ == "__main__":
    main()
