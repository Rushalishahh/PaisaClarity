"""
Generate all Phase 1 test fixtures (ALL SYNTHETIC - no real customer data):

  backend/tests/fixtures/*.csv|xlsx
  frontend-react/public/samples/sample_statement*.csv  (user-facing samples)
  backend/tests/fixtures/pdf/*.pdf (bordered, borderless, multipage,
                                    password-protected, scanned)

Run from the repo root:
    backend\\venv\\Scripts\\python scripts\\make_test_fixtures.py
"""

import csv
import io
import os
import random
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(REPO, "backend")
FIXTURES = os.path.join(BACKEND, "tests", "fixtures")
PDF_FIXTURES = os.path.join(FIXTURES, "pdf")
SAMPLES = os.path.join(REPO, "frontend-react", "public", "samples")

random.seed(42)

# ------------------------------------------------------------------ helpers
MERCHANTS = [
    ("UPI-ZOMATO-{n}", "Food", 250, 900),
    ("UPI-SWIGGY-{n}", "Food", 200, 700),
    ("UPI-BIGBASKET-{n}", "Groceries", 600, 2500),
    ("UPI-DMART-{n}", "Groceries", 800, 3000),
    ("UPI-AMAZON-{n}", "Shopping", 300, 3500),
    ("UPI-FLIPKART-{n}", "Shopping", 500, 4000),
    ("UPI-MYNTRA-{n}", "Shopping", 700, 3000),
    ("POS PETROL PUMP {n}", "Transport", 500, 2500),
    ("UPI-UBER-{n}", "Transport", 120, 500),
    ("UPI-AIRTEL-{n}", "Bills", 399, 399),
    ("ACH DR NETFLIX", "Entertainment", 649, 649),
    ("ACH DR SPOTIFY", "Entertainment", 119, 119),
    ("UPI-ZEPTO-{n}", "Groceries", 150, 800),
]
RENT = ("NEFT RENT LANDLORD", 18000.0)
SALARY = "NEFT SALARY ACME CORP"


def _desc(template):
    return template.format(n=random.randint(100000, 999999)) if "{n}" in template else template


def gen_transactions(start=(2026, 1, 1), months=4, with_balance=True, salary=45000.0):
    """A generator for realistic monthly flows: salary credit, rent, subs,
    merchants, one deliberate anomaly in month 2 (huge Flipkart order)."""
    from datetime import date, timedelta

    d = date(*start)
    end = date(start[0] + (start[1] - 1 + months) // 12, (start[1] - 1 + months) % 12 + 1, 1)
    rows = []
    balance = 60000.0
    if with_balance:
        rows.append(("opening", d, "OPENING BALANCE", "", 0.0, None, balance))
    anomaly_added = False
    month_i = 0
    while d < end:
        if d.day == 1:
            month_i += 1
        # Salary on the 10th, rent on the 3rd
        if d.day == 10:
            rows.append(("txn", d, SALARY, "", salary, "credit", None))
        if d.day == 3:
            rows.append(("txn", d, RENT[0], "", RENT[1], "debit", None))
        if d.day in (5, 15, 25):
            for template, _cat, lo, hi in random.sample(MERCHANTS, 3):
                rows.append(("txn", d, _desc(template), "", round(random.uniform(lo, hi), 2), "debit", None))
        # The anomaly: month 2 has a giant Flipkart order
        if month_i == 2 and d.day == 18 and not anomaly_added:
            rows.append(("txn", d, "UPI-FLIPKART-BIGSALE", "", 24500.00, "debit", None))
            anomaly_added = True
        d += timedelta(days=1)
    # Running balance + closing balance line
    out = []
    bal = balance
    for kind, d, desc, ref, amount, side, _ in rows:
        if kind == "opening":
            out.append((d, desc, ref, "", "", amount))
            continue
        bal = bal + amount if side == "credit" else bal - amount
        out.append((
            d.strftime("%d/%m/%Y"), desc, ref,
            f"{amount:.2f}" if side == "debit" else "",
            f"{amount:.2f}" if side == "credit" else "",
            f"{bal:.2f}",
        ))
    out.append((out[-1][0], "CLOSING BALANCE THIS PERIOD", "", "", "", f"{bal:.2f}"))
    return out


def write_csv(path, header, rows, delimiter=",", encoding="utf-8"):
    with open(path, "w", newline="", encoding=encoding) as f:
        w = csv.writer(f, delimiter=delimiter)
        w.writerow(header)
        w.writerows(rows)


def main():
    os.makedirs(FIXTURES, exist_ok=True)
    os.makedirs(PDF_FIXTURES, exist_ok=True)
    os.makedirs(SAMPLES, exist_ok=True)
    txns = gen_transactions()

    # ---- Layout 1: the original format (same header the app had) --------
    write_csv(
        os.path.join(FIXTURES, "layout1_original.csv"),
        ["Txn Date", "Value Date", "Description", "Ref No./Cheque No.", "Withdrawal Amt.", "Deposit Amt.", "Closing Balance"],
        [(t[0], t[0], t[1], t[2], t[3], t[4], t[5]) for t in txns],
    )

    # ---- Layout 2: metadata lines above + totals below -------------------
    header2 = ["Sr No", "Narration", "Chq./Ref.No.", "Value Dt", "Withdrawal Amt.", "Deposit Amt.", "Closing Balance"]
    rows2 = []
    with open(os.path.join(FIXTURES, "layout2_metadata.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        for line in [
            "ACME BANK, Marathahalli Branch",
            "Account No: XXXXXXX1234",
            "Name: TEST USER",
            "Address: 12th Main, Bengaluru 560037",
            "Statement period: 01/01/2026 to 01/05/2026",
            "Account type: Savings",
            "IFSC: ACME0001234",
            "Branch code: 1234",
            "Currency: INR",
            "Generated on: 05/05/2026",
        ]:
            w.writerow([line])
        w.writerow(header2)
        for i, t in enumerate(txns[1:-1], 1):  # skip opening/closing balance lines
            w.writerow([i, t[1], t[2], t[0], t[3], t[4], t[5]])
        w.writerow(["", "Total", "", "", "88,441.00", "1,79,936.40", ""])
        w.writerow(["", "Legends: UPI-Unified Payments Interface", "", "", "", "", ""])

    # ---- Layout 3: Date/Particulars/Debit/Credit/Balance -----------------
    write_csv(
        os.path.join(FIXTURES, "layout3_debit_credit.csv"),
        ["Date", "Particulars", "Debit", "Credit", "Balance"],
        [(t[0], t[1], t[3], t[4], t[5]) for t in txns],  # 5 cells: separate debit + credit cols
    )

    # ---- Layout 4: unsigned Amount + Dr/Cr indicator ---------------------
    rows4 = []
    for t in txns[1:-1]:
        amount = t[3] or t[4]
        side = "Dr" if t[3] else "Cr"
        rows4.append((t[0], t[1], f"{amount} {side}", t[5]))
    write_csv(
        os.path.join(FIXTURES, "layout4_drcr_indicator.csv"),
        ["Date", "Description", "Amount", "Balance"],
        rows4,
    )

    # ---- Layout 5: signed amount only ------------------------------------
    rows5 = []
    for t in txns[1:-1]:
        amount = float(t[3] or t[4])
        signed = -amount if t[3] else amount
        rows5.append((t[0], t[1], f"{signed:.2f}", t[5]))
    write_csv(
        os.path.join(FIXTURES, "layout5_signed_amount.csv"),
        ["Date", "Description", "Amount", "Balance"],
        rows5,
    )

    # ---- Layout 6: lakh-style commas + Dr/Cr suffixes --------------------
    def lakh(x):
        """
        Format x as an Indian lakh-grouped string.
        Rules: last 3 digits before the decimal form the first group,
        then groups of 2 from right to left.
        E.g. 1299.50 -> '1,299.50'  (< 10000, no extra group)
             179936.40 -> '1,79,936.40'
             1800000 -> '18,00,000.00'
        """
        # Format to 2 decimal places without any thousand separators first.
        s = f"{x:.2f}"
        integer_part, decimal_part = s.split(".")
        n = len(integer_part)
        if n <= 3:
            # No grouping needed for 3 or fewer digits.
            return integer_part + "." + decimal_part
        # Last 3 digits are always the rightmost group.
        groups = [integer_part[-3:]]
        rest = integer_part[:-3]
        # Remaining digits group in pairs from the right.
        while rest:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        return ",".join(groups) + "." + decimal_part

    rows6 = []
    for t in txns[1:-1]:
        amount = t[3] or t[4]
        side = " Dr" if t[3] else " Cr"
        rows6.append((t[0], t[1], f"{lakh(float(amount))}{side}", lakh(float(t[5]))))
    write_csv(
        os.path.join(FIXTURES, "layout6_lakh_drcr.csv"),
        ["Txn Date", "Narration", "Transaction Amount (INR)", "Closing Balance"],
        rows6,
    )

    # ---- Semicolon + cp1252 variants --------------------------------------
    write_csv(
        os.path.join(FIXTURES, "layout7_semicolon.csv"),
        ["Date", "Description", "Debit", "Credit", "Balance"],
        [(t[0], t[1], t[3], t[4], t[5]) for t in txns],
        delimiter=";",
    )
    rows8 = [(t[0], t[1], t[3], t[4], t[5]) for t in txns]
    with open(os.path.join(FIXTURES, "layout8_cp1252.csv"), "w", newline="", encoding="cp1252") as f:
        w = csv.writer(f)
        w.writerow(["Date", "Description", "Debit", "Credit", "Balance"])
        w.writerows(rows8[:-1])
        w.writerow([rows8[-1][0], "Café Claude – closing", "", "", rows8[-1][4]])

    # ---- xlsx --------------------------------------------------------------
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Statement"
    ws.append(["Account Summary", "", "", "", "", "", ""])
    ws.append(["Balance as on 01/05/2026:", 74559.4])
    ws.append([])
    ws.append(["Txn Date", "Value Date", "Description", "Ref No./Cheque No.", "Withdrawal Amt.", "Deposit Amt.", "Closing Balance"])
    for t in txns:
        ws.append([t[0], t[0], t[1], t[2], t[3] or None, t[4] or None, t[5]])
    wb.save(os.path.join(FIXTURES, "statement.xlsx"))

    # ---- User-facing samples (frontend/public/samples) ---------------------
    # sample_statement.csv: original format, Jan-Apr 2026
    write_csv(
        os.path.join(SAMPLES, "sample_statement.csv"),
        ["Txn Date", "Value Date", "Description", "Ref No./Cheque No.", "Withdrawal Amt.", "Deposit Amt.", "Closing Balance"],
        [(t[0], t[0], t[1], t[2], t[3], t[4], t[5]) for t in txns],
    )
    # alt format: Narration / Debit / Credit layout (same period)
    write_csv(
        os.path.join(SAMPLES, "sample_statement_alt_format.csv"),
        ["Date", "Narration", "Debit", "Credit", "Balance"],
        [(t[0], t[1], t[3], t[4], t[5]) for t in txns],
    )
    # overlapping by one month (Feb-Apr) for dedupe testing
    txns2 = gen_transactions(start=(2026, 3, 1), months=3)
    write_csv(
        os.path.join(SAMPLES, "sample_statement_alt_format_2.csv"),
        ["Date", "Narration", "Debit", "Credit", "Balance"],
        [(t[0], t[1], t[3], t[4], t[5]) for t in txns2],
    )

    # ---- PDFs (reportlab) --------------------------------------------------
    sys.path.insert(0, BACKEND)
    _make_pdfs(txns)

    print("fixtures written:")
    for root in (FIXTURES, PDF_FIXTURES, SAMPLES):
        for fn in sorted(os.listdir(root)):
            print("  ", os.path.relpath(os.path.join(root, fn), REPO))


# ------------------------------------------------------------------- PDFs
def _make_pdfs(txns):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from reportlab.lib.units import mm

    HEADER = ["Txn Date", "Value Date", "Description", "Ref No./Cheque No.", "Withdrawal Amt.", "Deposit Amt.", "Closing Balance"]
    data_rows = [(t[0], t[0], t[1], t[2], t[3], t[4], t[5]) for t in txns[1:-1]]

    def bordered_pdf(path, pages):
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=30, bottomMargin=30)
        story = []
        for i, rows in enumerate(pages):
            story.append(Paragraph(f"ACME BANK - Statement (page {i + 1})", None))
            story.append(Spacer(1, 10))
            t = Table([HEADER] + rows, colWidths=[58, 58, 150, 70, 70, 65, 75], repeatRows=1)
            t.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.4, colors.black),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
            ]))
            story.append(t)
            if i < len(pages) - 1:
                story.append(PageBreak())
        doc.build(story)
        open(path, "wb").write(buf.getvalue())

    def borderless_pdf(path):
        # No grid lines: pdfplumber's default (lines) strategy finds nothing,
        # so the reader must fall back to the text strategy / words strategy.
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=30, bottomMargin=30)
        story = [Paragraph("ACME BANK - Statement", None), Spacer(1, 10)]
        t = Table([HEADER] + data_rows[:8], colWidths=[58, 58, 150, 70, 70, 65, 75])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(t)
        doc.build(story)
        open(path, "wb").write(buf.getvalue())

    def multipage_pdf(path):
        half = len(data_rows) // 2
        bordered_pdf(path, [data_rows[:half], data_rows[half:]])

    def password_pdf(path):
        # reportlab cannot encrypt directly; use pikepdf if available,
        # otherwise skip with a note (test skips if fixture missing).
        bordered_pdf(path + ".tmp", [data_rows[:5]])
        try:
            import pikepdf
            with pikepdf.open(path + ".tmp") as pdf:
                pdf.save(path, encryption=pikepdf.Encryption(user="acme123", owner="acme123"))
            os.remove(path + ".tmp")
        except ImportError:
            os.remove(path + ".tmp")
            open(path, "wb").write(b"")

    def scanned_pdf(path):
        # An "image-only" PDF: one page with graphics but no text objects,
        # so pdfplumber extracts no text (the scanned-PDF case).
        from reportlab.pdfgen.canvas import Canvas
        buf = io.BytesIO()
        c = Canvas(buf, pagesize=A4)
        c.rect(50, 400, 400, 300)  # a "scanned page" placeholder, no text
        c.rect(60, 100, 200, 150)
        c.showPage()
        c.save()
        open(path, "wb").write(buf.getvalue())

    bordered_pdf(os.path.join(PDF_FIXTURES, "statement_bordered.pdf"), [data_rows])
    borderless_pdf(os.path.join(PDF_FIXTURES, "statement_borderless.pdf"))
    multipage_pdf(os.path.join(PDF_FIXTURES, "statement_multipage.pdf"))
    password_pdf(os.path.join(PDF_FIXTURES, "statement_password.pdf"))
    scanned_pdf(os.path.join(PDF_FIXTURES, "statement_scanned.pdf"))


if __name__ == "__main__":
    main()
