"""
Unit tests for database persistence, SQL queries, and audit logging.
"""

from datetime import date
import pandas as pd
import pytest
import tempfile
from pathlib import Path

from src.database import DatabaseManager


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_path = Path(f.name)
    db = DatabaseManager(db_path=temp_path)
    yield db
    try:
        temp_path.unlink()
    except Exception:
        pass


def test_audit_log_insertion(temp_db):
    """Verify audit logs are recorded and retrievable."""
    temp_db.log_audit(action="USER_LOGIN", actor="Auditor", details="Logged in for review")
    temp_db.log_audit(action="RECONCILE_EXECUTE", actor="Controller", run_id="RUN_001", details="Manual run")

    logs = temp_db.get_audit_trail()
    assert len(logs) == 2
    actions = list(logs["action"])
    assert "RECONCILE_EXECUTE" in actions
    assert "USER_LOGIN" in actions


def test_save_and_retrieve_run(temp_db):
    """Verify saving run details and items persists in SQLite and is queryable."""
    run_id = "RUN_TEST_001"
    kpis = {
        "total_bank_records": 10,
        "total_ledger_records": 10,
        "total_bank_amount": 1000.0,
        "total_ledger_amount": 1000.0,
        "net_reconciliation_variance": 0.0,
        "match_rate_pct": 100.0,
        "discrepancy_rate_pct": 0.0
    }
    results_df = pd.DataFrame([{
        "reconciliation_id": "REC_000001",
        "status": "MATCHED_EXACT",
        "reference_no": "REF-100",
        "bank_trx_id": "BNK-1",
        "ledger_trx_id": "GL-1",
        "bank_date": "2026-09-01",
        "ledger_date": "2026-09-01",
        "date_diff_days": 0,
        "bank_amount": 100.0,
        "ledger_amount": 100.0,
        "variance": 0.0,
        "bank_description": "Test",
        "ledger_description": "Test",
        "root_cause": "Clean Match",
        "requires_action": False
    }])

    temp_db.save_run(run_id, kpis, results_df)

    runs = temp_db.get_runs()
    assert len(runs) == 1
    assert runs.iloc[0]["run_id"] == run_id

    items = temp_db.get_run_items(run_id)
    assert len(items) == 1
    assert items.iloc[0]["reference_no"] == "REF-100"


def test_execute_custom_query_readonly(temp_db):
    """Verify read-only query execution works and destructive queries are blocked."""
    temp_db.log_audit(action="TEST_ACTION", actor="System")
    df = temp_db.execute_custom_query("SELECT count(*) as count FROM audit_logs")
    assert df.iloc[0]["count"] == 1

    # Disallow destructive statements
    with pytest.raises(ValueError):
        temp_db.execute_custom_query("DELETE FROM audit_logs")
