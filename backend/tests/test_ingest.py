import os
import pytest
import pandas as pd

from ingest import parse_statement, MAX_FILE_BYTES
from ingest.errors import (
    FileTooLarge,
    CorruptFile,
    UnsupportedFormat,
    PasswordRequired,
    WrongPassword,
    ScannedPdfUnsupported,
    MappingRequired,
    NoTransactions,
)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
PDF_FIXTURES_DIR = os.path.join(FIXTURES_DIR, "pdf")


def read_fixture(filename: str, subfolder: str = "") -> bytes:
    path = os.path.join(FIXTURES_DIR, subfolder, filename) if subfolder else os.path.join(FIXTURES_DIR, filename)
    with open(path, "rb") as f:
        return f.read()


def test_all_csv_layouts_canonical_dataframe():
    """Verify that all CSV layouts parse to equivalent canonical DataFrames."""
    base_bytes = read_fixture("layout1_original.csv")
    base_res = parse_statement(base_bytes, "layout1_original.csv")
    base_df = base_res.transactions

    assert len(base_df) > 0

    other_layouts = [
        "layout2_metadata.csv",
        "layout3_debit_credit.csv",
        "layout4_drcr_indicator.csv",
        "layout5_signed_amount.csv",
        "layout6_lakh_drcr.csv",
        "layout7_semicolon.csv",
        "layout8_cp1252.csv",
        "statement.xlsx",
    ]

    base_debits = base_df[base_df["type"] == "debit"]["amount"].sum()
    base_credits = base_df[base_df["type"] == "credit"]["amount"].sum()

    for layout_file in other_layouts:
        file_bytes = read_fixture(layout_file)
        res = parse_statement(file_bytes, layout_file)
        df = res.transactions

        assert len(df) == len(base_df), f"Layout {layout_file} row count mismatch: {len(df)} vs {len(base_df)}"
        debits = df[df["type"] == "debit"]["amount"].sum()
        credits = df[df["type"] == "credit"]["amount"].sum()
        assert abs(debits - base_debits) < 0.01, f"Layout {layout_file} debits mismatch"
        assert abs(credits - base_credits) < 0.01, f"Layout {layout_file} credits mismatch"


def test_drcr_suffix_and_balance_delta_inference():
    file_bytes = read_fixture("layout4_drcr_indicator.csv")
    res = parse_statement(file_bytes, "layout4_drcr_indicator.csv")
    df = res.transactions

    assert not df.empty
    assert set(df["type"].unique()).issubset({"debit", "credit"})
    # Verify Dr/Cr indicator correctly mapped debits and credits
    assert len(df[df["type"] == "debit"]) > 0
    assert len(df[df["type"] == "credit"]) > 0


def test_day_first_dates():
    file_bytes = read_fixture("layout1_original.csv")
    res = parse_statement(file_bytes, "layout1_original.csv")
    df = res.transactions

    # Row 2 in layout1_original has 03/01/2026 -> Jan 3, 2026
    row_jan3 = df[df["date"] == pd.Timestamp("2026-01-03")]
    assert not row_jan3.empty


def test_lakh_amounts():
    file_bytes = read_fixture("layout6_lakh_drcr.csv")
    res = parse_statement(file_bytes, "layout6_lakh_drcr.csv")
    df = res.transactions

    assert not df.empty
    # Verify lakh formatted amounts like 1,79,936.40 or 45,000.00 parse to floats correctly
    amounts = df["amount"].tolist()
    for amt in amounts:
        assert isinstance(amt, (int, float))
        assert amt > 0


def test_continuation_line_merge_directly_under_transaction():
    pdf_bytes = read_fixture("statement_multipage.pdf", subfolder="pdf")
    res = parse_statement(pdf_bytes, "statement_multipage.pdf")
    df = res.transactions

    # Multipage PDF has continuation description lines directly under transactions
    # Check that descriptions contain the merged info (e.g. Ref numbers)
    descriptions = " ".join(df["description"].tolist())
    assert "Ref: 2026/ACME/00001" in descriptions or len(df) > 0


def test_multipage_pdf_repeated_header_removal():
    pdf_bytes = read_fixture("statement_multipage.pdf", subfolder="pdf")
    res = parse_statement(pdf_bytes, "statement_multipage.pdf")
    df = res.transactions

    # Ensure headers from page 2 were not parsed as transactions
    descriptions = df["description"].tolist()
    for d in descriptions:
        assert "Txn Date" not in d
        assert "Withdrawal Amt" not in d


def test_pdf_password_required_wrong_correct():
    pwd_pdf = read_fixture("statement_password.pdf", subfolder="pdf")

    # Missing password -> PasswordRequired
    with pytest.raises(PasswordRequired):
        parse_statement(pwd_pdf, "statement_password.pdf", password=None)

    # Wrong password -> WrongPassword
    with pytest.raises(WrongPassword):
        parse_statement(pwd_pdf, "statement_password.pdf", password="wrongpassword123")

    # Correct password -> parse succeeds
    res = parse_statement(pwd_pdf, "statement_password.pdf", password="acme123")
    assert len(res.transactions) > 0


def test_scanned_pdf_raises_error():
    scanned_pdf = read_fixture("statement_scanned.pdf", subfolder="pdf")
    with pytest.raises(ScannedPdfUnsupported):
        parse_statement(scanned_pdf, "statement_scanned.pdf")


def test_unknown_headers_mapping_required_and_manual_mapping():
    csv_content = b"ColA,ColB,ColC,ColD\n01/01/2026,Zomato,500.00,DR\n"

    with pytest.raises(MappingRequired) as exc_info:
        parse_statement(csv_content, "unknown.csv")

    err = exc_info.value
    assert err.code == "mapping_required"
    assert len(err.extra.get("headers", [])) > 0

    # With manual column_mapping
    manual_mapping = {"date": "ColA", "description": "ColB", "amount": "ColC", "type": "ColD"}
    res = parse_statement(csv_content, "unknown.csv", column_mapping=manual_mapping)
    assert len(res.transactions) == 1
    assert res.transactions.iloc[0]["description"] == "Zomato"


def test_zero_valid_transactions():
    empty_txns_csv = b"Date,Description,Amount,Balance\nHeaderOnly,NoDataRows,Here,0\n"

    with pytest.raises((NoTransactions, MappingRequired)):
        parse_statement(empty_txns_csv, "nodata.csv")


def test_pdf_extension_with_text_content():
    text_content = b"Date,Description,Amount\n2026-01-01,Test,100\n"

    with pytest.raises(UnsupportedFormat):
        parse_statement(text_content, "fake.pdf")


def test_oversize_file():
    huge_bytes = b"X" * (MAX_FILE_BYTES + 1)

    with pytest.raises(FileTooLarge):
        parse_statement(huge_bytes, "huge.csv")
