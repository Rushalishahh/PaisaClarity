import io
import json
import os
import pytest
from tests.test_ingest import read_fixture, MAX_FILE_BYTES

# The exact files a real user is offered in the UI (frontend-react/public/samples).
# If the ingest pipeline can't parse THESE, the demo flow is broken.
SAMPLES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "frontend-react", "public", "samples")
)


def read_sample(filename: str) -> bytes:
    with open(os.path.join(SAMPLES_DIR, filename), "rb") as f:
        return f.read()


@pytest.mark.parametrize(
    "filename",
    [
        "sample_statement.csv",
        "sample_statement_alt_format.csv",
        "sample_statement_alt_format_2.csv",
    ],
)
def test_upload_user_sample_files(client, auth_headers, filename):
    """Every user-facing sample file must upload end-to-end (parse + analyze)."""
    files = {"file": (filename, io.BytesIO(read_sample(filename)), "text/csv")}
    resp = client.post("/upload-statement", files=files, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ingest_report"]["rows_parsed"] > 0
    assert "savings_summary" in data


def test_upload_statement_success(client, auth_headers):
    file_bytes = read_fixture("layout1_original.csv")
    files = {"file": ("statement.csv", io.BytesIO(file_bytes), "text/csv")}

    response = client.post("/upload-statement", files=files, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "category_totals" in data
    assert "savings_summary" in data
    assert "ingest_report" in data
    assert data["ingest_report"]["rows_found"] > 0


def test_upload_statement_preview_success(client, auth_headers):
    file_bytes = read_fixture("layout1_original.csv")
    files = {"file": ("statement.csv", io.BytesIO(file_bytes), "text/csv")}

    response = client.post("/upload-statement/preview", files=files, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "preview_rows" in data
    assert "mapping_used" in data
    assert len(data["preview_rows"]) > 0
    assert data["total_rows"] > 0


def test_upload_statement_alt_layout_csv(client, auth_headers):
    file_bytes = read_fixture("layout3_debit_credit.csv")
    files = {"file": ("layout3.csv", io.BytesIO(file_bytes), "text/csv")}

    response = client.post("/upload-statement", files=files, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "category_totals" in data


def test_upload_statement_password_pdf_flow(client, auth_headers):
    pdf_bytes = read_fixture("statement_password.pdf", subfolder="pdf")

    # 1. Missing password -> 422 password_required
    files = {"file": ("statement_password.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    resp = client.post("/upload-statement", files=files, headers=auth_headers)
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "password_required"

    # 2. Wrong password -> 422 wrong_password
    files = {"file": ("statement_password.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    resp = client.post(
        "/upload-statement",
        files=files,
        data={"password": "wrongpassword"},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "wrong_password"

    # 3. Correct password -> 200
    files = {"file": ("statement_password.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    resp = client.post(
        "/upload-statement",
        files=files,
        data={"password": "acme123"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert "category_totals" in resp.json()


def test_upload_statement_scanned_pdf(client, auth_headers):
    pdf_bytes = read_fixture("statement_scanned.pdf", subfolder="pdf")
    files = {"file": ("scanned.pdf", io.BytesIO(pdf_bytes), "application/pdf")}

    resp = client.post("/upload-statement", files=files, headers=auth_headers)
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "scanned_pdf"


def test_upload_statement_mapping_flow(client, auth_headers):
    csv_content = b"ColA,ColB,ColC,ColD\n01/01/2026,Zomato,500.00,DR\n"

    # Without mapping -> 422 mapping_required
    files = {"file": ("unknown.csv", io.BytesIO(csv_content), "text/csv")}
    resp = client.post("/upload-statement", files=files, headers=auth_headers)
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "mapping_required"

    # With mapping -> 200
    mapping_str = json.dumps({"date": "ColA", "description": "ColB", "amount": "ColC", "type": "ColD"})
    files = {"file": ("unknown.csv", io.BytesIO(csv_content), "text/csv")}
    resp = client.post(
        "/upload-statement",
        files=files,
        data={"column_mapping": mapping_str},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert "category_totals" in resp.json()


def test_upload_statement_unsupported_format(client, auth_headers):
    fake_pdf_content = b"Date,Description,Amount\n2026-01-01,Test,100\n"
    files = {"file": ("fake.pdf", io.BytesIO(fake_pdf_content), "application/pdf")}

    resp = client.post("/upload-statement", files=files, headers=auth_headers)
    assert resp.status_code == 415
    assert resp.json()["detail"]["code"] == "unsupported_format"


def test_upload_statement_file_too_large(client, auth_headers):
    huge_bytes = b"X" * (MAX_FILE_BYTES + 1)
    files = {"file": ("huge.csv", io.BytesIO(huge_bytes), "text/csv")}

    resp = client.post("/upload-statement", files=files, headers=auth_headers)
    assert resp.status_code == 413
    assert resp.json()["detail"]["code"] == "file_too_large"


def test_upload_statement_unauthenticated(client):
    file_bytes = read_fixture("layout1_original.csv")
    files = {"file": ("statement.csv", io.BytesIO(file_bytes), "text/csv")}

    response = client.post("/upload-statement", files=files)
    assert response.status_code == 401


def test_preview_unauthenticated(client):
    file_bytes = read_fixture("layout1_original.csv")
    files = {"file": ("statement.csv", io.BytesIO(file_bytes), "text/csv")}

    response = client.post("/upload-statement/preview", files=files)
    assert response.status_code == 401
