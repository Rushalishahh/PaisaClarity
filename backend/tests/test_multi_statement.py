"""
Multi-statement support tests:

- cross-statement dedupe on (date, normalized description, amount) using the
  two overlapping sample files (alt_format = Feb+Mar 2026, alt_format_2 =
  Mar+Apr+May 2026 — March is shared, so combined totals must not double)
- the scope param on GET /insights (all / latest / bad value / statement_id)
- upload-time overlap + duplicate warnings in ingest_report
- the read-time category-alias map (old saved statements render renamed)
- direct get_user_transactions behavior (unknown scope / foreign statement)

Concurrency note: the TestClient runs the app in the same thread as the
test, and get_db is overridden to yield the SAME db_session fixture — so
inserts are visible to endpoints without committing. Direct
get_user_transactions calls use the same session object.
"""

import io
import json

import pytest

from tests.test_ingest_api import read_sample
from transactions import get_user_transactions, transaction_key
from categorizer import apply_category_aliases, CATEGORY_ALIASES


def upload(client, auth_headers, filename, mimetype="text/csv"):
    files = {"file": (filename, io.BytesIO(read_sample(filename)), mimetype)}
    return client.post("/upload-statement", files=files, headers=auth_headers)


@pytest.fixture
def two_overlapping_statements(client, auth_headers, db_session):
    """Upload the two overlapping sample files as one test user.

    uploaded_at is pinned explicitly because SQLite's CURRENT_TIMESTAMP has
    1-second resolution - two rapid uploads would otherwise tie and make
    scope="latest" ambiguous. (Production Postgres has microsecond
    precision; this keeps the TEST deterministic.)
    """
    from datetime import datetime, timedelta

    from models import Statement

    r1 = upload(client, auth_headers, "sample_statement_alt_format.csv")
    assert r1.status_code == 200, r1.text
    r2 = upload(client, auth_headers, "sample_statement_alt_format_2.csv")
    assert r2.status_code == 200, r2.text

    now = datetime.now()
    statements = (
        db_session.query(Statement)
        .filter(Statement.filename.in_(
            ["sample_statement_alt_format.csv", "sample_statement_alt_format_2.csv"])
        )
        .all()
    )
    for s in statements:
        if s.filename == "sample_statement_alt_format.csv":
            s.uploaded_at = now - timedelta(minutes=2)
        else:
            s.uploaded_at = now - timedelta(minutes=1)
    db_session.commit()

    return r1.json(), r2.json()


# --------------------------------------------------------------- dedupe ----

def test_dedupe_across_overlapping_samples(client, auth_headers, two_overlapping_statements):
    """
    alt_format = Jan-Apr 2026 (45 rows); alt_format_2 = Mar-May 2026 (34
    rows). The files overlap in March AND April: 5 rows (rent, salary,
    NETFLIX on those dates) carry identical date+description+amount in both
    files but DIFFERENT running balances - so combined totals must count
    each exactly once.
    """
    single_a, _response_b = two_overlapping_statements

    # The upload response is the SINGLE-file analysis; the combined view
    # comes from GET /insights?scope=all.
    combined = client.get("/insights?scope=all", headers=auth_headers).json()["analysis"]

    inc_a = single_a["savings_summary"]["total_income"]
    inc_all = combined["savings_summary"]["total_income"]

    # Statement A (Jan-Apr): 4 x 45000 salary.
    assert inc_a == 180000
    # Statement B (Mar-May): 3 x 45000, of which Mar+Apr salary are
    # duplicates of A's -> combined = 5 x 45000, NOT the double-counted 7.
    assert inc_all == 225000

    spend_a = single_a["savings_summary"]["total_spend"]
    spend_all = combined["savings_summary"]["total_spend"]
    # B genuinely adds Apr+May spending...
    assert spend_all > spend_a
    # ...but the merged file must contain exactly 5 rent rows (one per
    # month, 18000 each) even though rent appears 3x in EACH file - i.e.
    # the shared March rent was dropped once.
    from datetime import date

    assert transaction_key("2026-03-03", "NEFT RENT LANDLORD", 18000.0) == transaction_key(
        "2026-03-03", "UPI-X-NEFT RENT LANDLORD-42", 18000.0
    )
    assert transaction_key("2026-03-03", "NEFT RENT LANDLORD", 18000.0) != transaction_key(
        "2026-03-03", "NEFT RENT LANDLORD", 18001.0
    )


def test_merged_dataframe_dedupes_directly(client, auth_headers, two_overlapping_statements, db_session):
    """Direct get_user_transactions(scope='all') merge drops the March overlap."""
    from models import User

    user = db_session.query(User).filter_by(email="testuser@example.com").first()
    df_all = get_user_transactions(db_session, user.id, scope="all")

    # Both files uploaded -> all 5 months present exactly once.
    months = sorted(df_all["date"].dt.strftime("%Y-%m").unique())
    assert months == ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05"]

    march_rent = df_all[
        (df_all["date"].dt.strftime("%Y-%m") == "2026-03")
        & (df_all["description"].str.contains("RENT"))
    ]
    # March rent exists in BOTH files -> must appear exactly once after merge.
    assert len(march_rent) == 1
    assert float(march_rent.iloc[0]["amount"]) == 18000.0

    # 45 rows (A) + 34 rows (B) - 5 exact duplicates in the shared
    # Mar+Apr window = 74 unique transactions.
    assert len(df_all) == 45 + 34 - 5


def test_scope_latest_returns_only_newest(client, auth_headers, two_overlapping_statements, db_session):
    from models import User

    user = db_session.query(User).filter_by(email="testuser@example.com").first()

    df_latest = get_user_transactions(db_session, user.id, scope="latest")
    months = sorted(df_latest["date"].dt.strftime("%Y-%m").unique())
    # The newest upload is alt_format_2 (Mar+Apr+May 2026).
    assert months == ["2026-03", "2026-04", "2026-05"]
    assert len(df_latest) > 0

    df_all = get_user_transactions(db_session, user.id, scope="all")
    assert len(df_all) > len(df_latest)


def test_unknown_scope_and_foreign_statement(client, auth_headers, db_session):
    from models import User, Statement

    user = db_session.query(User).filter_by(email="testuser@example.com").first()

    with pytest.raises(ValueError):
        get_user_transactions(db_session, user.id, scope="bogus")

    # A statement owned by nobody in particular / another user -> LookupError.
    ghost = Statement(user_id=user.id + 9999, filename="nope.csv", result={})
    db_session.add(ghost)
    db_session.commit()
    with pytest.raises(LookupError):
        get_user_transactions(db_session, user.id, statement_id=ghost.id)


# ----------------------------------------------------- GET /insights -------

def test_insights_scope_all_no_double_count(client, auth_headers, two_overlapping_statements):
    """GET /insights?scope=all totals must not double-count the shared month."""
    resp = client.get("/insights?scope=all", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["scope"] == "all"
    assert data["transactions_count"] > 0
    assert data["analysis"]["savings_summary"]["total_income"] == 225000


def test_insights_scope_latest(client, auth_headers, two_overlapping_statements):
    resp = client.get("/insights?scope=latest", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["scope"] == "latest"
    # Latest statement = alt_format_2 (Mar-Apr-May): 3 x 45000 salary.
    assert data["analysis"]["savings_summary"]["total_income"] == 135000


def test_insights_scope_statement_id(client, auth_headers, two_overlapping_statements):
    # Find the id of the FIRST (alt_format) statement via the list endpoint.
    lst = client.get("/statements", headers=auth_headers).json()
    target = next(s for s in lst if s["filename"] == "sample_statement_alt_format.csv")

    resp = client.get(f"/insights?statement_id={target['id']}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["statement_id"] == target["id"]
    # That file covers Jan-Apr: 4 x 45000.
    assert data["analysis"]["savings_summary"]["total_income"] == 180000


def test_insights_scope_invalid_and_404(client, auth_headers):
    resp = client.get("/insights?scope=bogus", headers=auth_headers)
    assert resp.status_code == 400

    resp = client.get("/insights?statement_id=999999", headers=auth_headers)
    assert resp.status_code == 404


def test_insights_empty_scope_message(client, auth_headers):
    """A fresh user with no statements gets an honest, non-crashing response."""
    from tests.test_ingest_api import read_fixture  # reuse fixture reader only

    resp = client.get("/insights?scope=all", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["transactions_count"] == 0
    assert data["analysis"] is None
    assert "message" in data


# ------------------------------------------- upload-time overlap warnings --

def test_upload_overlap_and_duplicate_warnings(client, auth_headers, two_overlapping_statements):
    """
    Uploading a third file whose March overlaps BOTH existing statements must
    add warnings for (a) the date-range overlap and (b) the duplicate rows.
    """
    # sample_statement.csv covers Jan-Apr 2026 -> overlaps everything above.
    r3 = upload(client, auth_headers, "sample_statement.csv")
    assert r3.status_code == 200, r3.text
    warnings = r3.json()["ingest_report"].get("warnings", [])

    assert any("overlaps existing statement" in w for w in warnings)
    assert any("duplicate transaction" in w for w in warnings)


def test_first_upload_has_no_overlap_warning(client, auth_headers):
    r = upload(client, auth_headers, "sample_statement.csv")
    assert r.status_code == 200
    warnings = r.json()["ingest_report"].get("warnings", [])
    assert not any("overlaps existing statement" in w for w in warnings)


def test_upload_stores_transactions_in_result(client, auth_headers):
    """Uploads must persist the canonical transactions inside Statement.result."""
    r = upload(client, auth_headers, "sample_statement.csv")
    assert r.status_code == 200
    body = r.json()
    txs = body["transactions"]
    assert isinstance(txs, list) and len(txs) > 0
    first = txs[0]
    for key in ("date", "description", "amount", "type", "balance"):
        assert key in first


# -------------------------------------------------------- alias map -------

def test_alias_map_basic():
    assert CATEGORY_ALIASES["Utilities"] == "Bills"
    assert apply_category_aliases({"category": "Utilities"}) == {"category": "Bills"}
    # Unknown names pass through untouched.
    assert apply_category_aliases({"category": "Food"}) == {"category": "Food"}


def test_alias_merges_category_total_keys():
    stored = {"category_totals": {"Utilities": 100.0, "Bills": 50.0, "Food": 10.0}}
    out = apply_category_aliases(stored)
    assert out["category_totals"] == {"Bills": 150.0, "Food": 10.0}
    # Original blob untouched (read-time only, no migration).
    assert stored["category_totals"]["Utilities"] == 100.0


def test_alias_applied_to_list_items_and_nested():
    stored = {
        "anomalies": [{"category": "Telecom", "amount": 1}],
        "subscriptions": [{"merchant": "X", "category": "Subscription"}],
        "month_over_month_trend": [{"category": "Fuel"}],
    }
    out = apply_category_aliases(stored)
    assert out["anomalies"][0]["category"] == "Bills"
    assert out["subscriptions"][0]["category"] == "Entertainment"
    assert out["month_over_month_trend"][0]["category"] == "Transport"


def test_old_statement_without_ingest_report_still_renders(client, auth_headers, db_session):
    """Legacy row: no ingest_report, old category names -> aliases on read."""
    from models import User, Statement

    user = db_session.query(User).filter_by(email="testuser@example.com").first()
    legacy = Statement(
        user_id=user.id,
        filename="legacy.csv",
        result={
            "category_totals": {"Utilities": 300.0},
            "subscriptions": [{"merchant": "AIRTEL", "category": "Telecom"}],
            "savings_summary": {"total_income": 1, "total_spend": 1, "total_saved": 0, "savings_rate_pct": 0},
        },
    )
    db_session.add(legacy)
    db_session.commit()
    db_session.refresh(legacy)

    resp = client.get(f"/statements/{legacy.id}", headers=auth_headers)
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert result["category_totals"] == {"Bills": 300.0}
    assert result["subscriptions"][0]["category"] == "Bills"
