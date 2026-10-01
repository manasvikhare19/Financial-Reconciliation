"""
Unit tests for Excel report generation.
"""

from datetime import date
import pandas as pd
import openpyxl
from io import BytesIO

from src.excel_exporter import create_reconciliation_excel_bytes


def test_excel_generation_tabs_and_structure():
    """Verify generated Excel workbook has all 4 sheets and non-empty content."""
    kpis = {
        "total_bank_records": 5,
        "total_ledger_records": 5,
        "total_bank_amount": 1000.0,
        "total_ledger_amount": 950.0,
        "net_reconciliation_variance": 50.0,
        "gross_exception_variance": 50.0,
        "total_reconciled_items": 5,
        "matched_count": 4,
        "exception_count": 1,
        "match_rate_pct": 80.0,
        "discrepancy_rate_pct": 20.0,
        "status_breakdown": {
            "MATCHED_EXACT": {"count": 4, "variance": 0.0},
            "AMOUNT_MISMATCH": {"count": 1, "variance": 50.0}
        }
    }

    results_df = pd.DataFrame([
        {
            "reconciliation_id": "REC_000001",
            "status": "MATCHED_EXACT",
            "reference_no": "REF-1",
            "bank_trx_id": "B-1",
            "ledger_trx_id": "L-1",
            "bank_date": date(2026, 9, 1),
            "ledger_date": date(2026, 9, 1),
            "date_diff_days": 0,
            "bank_amount": 200.0,
            "ledger_amount": 200.0,
            "variance": 0.0,
            "bank_description": "Clean Payment",
            "ledger_description": "Clean Payment",
            "root_cause": "Clean Match",
            "requires_action": False
        },
        {
            "reconciliation_id": "REC_000002",
            "status": "AMOUNT_MISMATCH",
            "reference_no": "REF-2",
            "bank_trx_id": "B-2",
            "ledger_trx_id": "L-2",
            "bank_date": date(2026, 9, 2),
            "ledger_date": date(2026, 9, 2),
            "date_diff_days": 0,
            "bank_amount": 250.0,
            "ledger_amount": 200.0,
            "variance": 50.0,
            "bank_description": "Mismatch",
            "ledger_description": "Mismatch",
            "root_cause": "Transposition / Typo Error",
            "requires_action": True
        }
    ])

    audit_df = pd.DataFrame([
        {
            "log_id": 1,
            "timestamp": "2026-10-01 12:00:00",
            "run_id": "RUN_001",
            "action": "RUN_EXECUTED",
            "actor": "Controller",
            "details": "Automated run test"
        }
    ])

    excel_bytes = create_reconciliation_excel_bytes("RUN_001", kpis, results_df, audit_df)
    assert len(excel_bytes) > 0

    wb = openpyxl.load_workbook(BytesIO(excel_bytes))
    sheet_names = wb.sheetnames
    assert "Executive Summary" in sheet_names
    assert "Exceptions & Discrepancies" in sheet_names
    assert "Matched Records" in sheet_names
    assert "Audit Trail Log" in sheet_names
