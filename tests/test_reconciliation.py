"""
Unit tests for core reconciliation engine matching algorithms and KPI calculations.
"""

from datetime import date
import pandas as pd
import pytest

from src.engine import ReconciliationEngine
from config import (
    STATUS_EXACT_MATCH,
    STATUS_TIMING_MATCH,
    STATUS_AMOUNT_MISMATCH,
    STATUS_DUPLICATE_BANK,
    STATUS_DUPLICATE_LEDGER,
    STATUS_MISSING_IN_LEDGER,
    STATUS_MISSING_IN_BANK
)


@pytest.fixture
def engine():
    return ReconciliationEngine(date_tolerance_days=5, amount_tolerance=0.01)


def test_exact_match(engine):
    """Verify transactions with identical Ref, Amount, and Date match cleanly."""
    bank_df = pd.DataFrame([{
        "transaction_id": "BNK-001",
        "date": date(2026, 9, 1),
        "amount": -1500.00,
        "reference_no": "INV-1001",
        "description": "AWS Payment"
    }])
    ledger_df = pd.DataFrame([{
        "transaction_id": "GL-001",
        "date": date(2026, 9, 1),
        "amount": -1500.00,
        "reference_no": "INV-1001",
        "description": "Cloud Hosting"
    }])

    results, kpis = engine.reconcile(bank_df, ledger_df)
    assert len(results) == 1
    assert results.iloc[0]["status"] == STATUS_EXACT_MATCH
    assert results.iloc[0]["variance"] == 0.0
    assert bool(results.iloc[0]["requires_action"]) is False
    assert kpis["match_rate_pct"] == 100.0
    assert kpis["net_reconciliation_variance"] == 0.0


def test_timing_difference_match(engine):
    """Verify transactions matching within date tolerance are flagged as timing difference."""
    bank_df = pd.DataFrame([{
        "transaction_id": "BNK-002",
        "date": date(2026, 9, 4),   # 3 days later
        "amount": 5000.00,
        "reference_no": "CUST-881",
        "description": "Wire receipt"
    }])
    ledger_df = pd.DataFrame([{
        "transaction_id": "GL-002",
        "date": date(2026, 9, 1),
        "amount": 5000.00,
        "reference_no": "CUST-881",
        "description": "AR receipt"
    }])

    results, kpis = engine.reconcile(bank_df, ledger_df)
    assert len(results) == 1
    assert results.iloc[0]["status"] == STATUS_TIMING_MATCH
    assert results.iloc[0]["date_diff_days"] == 3
    assert results.iloc[0]["variance"] == 0.0
    assert bool(results.iloc[0]["requires_action"]) is False
    assert "Timing Difference" in results.iloc[0]["root_cause"]


def test_amount_mismatch(engine):
    """Verify transactions with matching reference but different amounts are flagged with variance."""
    bank_df = pd.DataFrame([{
        "transaction_id": "BNK-003",
        "date": date(2026, 9, 5),
        "amount": -1450.00,
        "reference_no": "INV-300",
        "description": "Vendor Payment"
    }])
    ledger_df = pd.DataFrame([{
        "transaction_id": "GL-003",
        "date": date(2026, 9, 5),
        "amount": -1540.00,  # $90 transposition error
        "reference_no": "INV-300",
        "description": "Vendor Invoice"
    }])

    results, kpis = engine.reconcile(bank_df, ledger_df)
    assert len(results) == 1
    assert results.iloc[0]["status"] == STATUS_AMOUNT_MISMATCH
    assert results.iloc[0]["variance"] == 90.00
    assert bool(results.iloc[0]["requires_action"]) is True
    assert kpis["discrepancy_rate_pct"] == 100.0


def test_intra_dataset_duplicates(engine):
    """Verify duplicate ledger postings are flagged."""
    bank_df = pd.DataFrame([{
        "transaction_id": "BNK-004",
        "date": date(2026, 9, 10),
        "amount": -500.00,
        "reference_no": "DUP-REF-1",
        "description": "Check 101"
    }])
    # Two identical records in Ledger
    ledger_df = pd.DataFrame([
        {
            "transaction_id": "GL-004A",
            "date": date(2026, 9, 10),
            "amount": -500.00,
            "reference_no": "DUP-REF-1",
            "description": "Voucher 101"
        },
        {
            "transaction_id": "GL-004B",
            "date": date(2026, 9, 10),
            "amount": -500.00,
            "reference_no": "DUP-REF-1",
            "description": "Voucher 101 Duplicate"
        }
    ])

    results, kpis = engine.reconcile(bank_df, ledger_df)
    statuses = list(results["status"])
    assert STATUS_DUPLICATE_LEDGER in statuses
    assert kpis["status_breakdown"][STATUS_DUPLICATE_LEDGER]["count"] == 2


def test_missing_records(engine):
    """Verify transactions present in only one dataset are properly classified."""
    bank_df = pd.DataFrame([{
        "transaction_id": "BNK-FEE",
        "date": date(2026, 9, 15),
        "amount": -35.00,
        "reference_no": "FEE-01",
        "description": "Monthly Bank Service Fee"
    }])
    ledger_df = pd.DataFrame([{
        "transaction_id": "GL-CHK",
        "date": date(2026, 9, 29),
        "amount": -2500.00,
        "reference_no": "CHK-999",
        "description": "Outstanding Vendor Check"
    }])

    results, kpis = engine.reconcile(bank_df, ledger_df)
    statuses = set(results["status"])
    assert STATUS_MISSING_IN_LEDGER in statuses
    assert STATUS_MISSING_IN_BANK in statuses
    assert kpis["matched_count"] == 0
    assert kpis["exception_count"] == 2
