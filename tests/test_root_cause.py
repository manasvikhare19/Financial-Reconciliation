"""
Unit tests for automated root-cause analysis logic.
"""

from datetime import date
import pytest
from src.root_cause import is_transposition_error, classify_root_cause
from config import (
    RC_TRANSPOSITION,
    RC_BANK_FEE,
    RC_TIMING_LAG,
    RC_DUPLICATE_POSTING,
    RC_UNRECORDED_CASH,
    STATUS_AMOUNT_MISMATCH,
    STATUS_TIMING_MATCH,
    STATUS_DUPLICATE_LEDGER,
    STATUS_MISSING_IN_LEDGER
)


def test_is_transposition_error():
    """Verify accounting transposition detection using divisible-by-9 rule."""
    # 54 vs 45 -> diff = 9 (9/9 = 1) -> True
    assert is_transposition_error(54.0, 45.0) is True
    # 1540 vs 1450 -> diff = 90 (90/9 = 10) -> True
    assert is_transposition_error(1540.0, 1450.0) is True
    # 72 vs 27 -> diff = 45 (45/9 = 5) -> True
    assert is_transposition_error(72.0, 27.0) is True
    # Random non-transposition difference (e.g. 100 vs 93 -> diff 7)
    assert is_transposition_error(100.0, 93.0) is False
    # Zero difference
    assert is_transposition_error(100.0, 100.0) is False


def test_classify_root_cause_transposition():
    """Verify amount mismatch with transposition difference tags transposition error."""
    cause = classify_root_cause(
        status=STATUS_AMOUNT_MISMATCH,
        bank_amount=1540.0,
        ledger_amount=1450.0,
        bank_desc="Wire payment",
        ledger_desc="Invoice bill"
    )
    assert RC_TRANSPOSITION in cause


def test_classify_root_cause_fee():
    """Verify bank fee deduction keywords trigger fee root cause."""
    cause = classify_root_cause(
        status=STATUS_MISSING_IN_LEDGER,
        bank_amount=-35.0,
        bank_desc="MONTHLY WIRE SERVICE CHARGE"
    )
    assert RC_BANK_FEE in cause


def test_classify_root_cause_timing():
    """Verify timing match produces lag explanation."""
    cause = classify_root_cause(
        status=STATUS_TIMING_MATCH,
        days_difference=3
    )
    assert RC_TIMING_LAG in cause
    assert "3 days" in cause


def test_classify_root_cause_duplicate():
    """Verify duplicate ledger posting diagnosis."""
    cause = classify_root_cause(
        status=STATUS_DUPLICATE_LEDGER
    )
    assert RC_DUPLICATE_POSTING in cause
    assert "General Ledger" in cause
