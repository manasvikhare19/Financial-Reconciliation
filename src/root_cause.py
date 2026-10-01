"""
Root-Cause Analysis Engine.
Automatically categorizes financial discrepancies and control breaks based on accounting heuristics.
"""

from typing import Optional
from datetime import date
from config import (
    RC_TIMING_LAG,
    RC_BANK_FEE,
    RC_TRANSPOSITION,
    RC_DUPLICATE_POSTING,
    RC_UNRECORDED_CASH,
    RC_ROUNDING_FX,
    RC_PENDING_INVESTIGATION,
    FEE_KEYWORDS,
    STATUS_EXACT_MATCH,
    STATUS_TIMING_MATCH,
    STATUS_AMOUNT_MISMATCH,
    STATUS_DUPLICATE_BANK,
    STATUS_DUPLICATE_LEDGER,
    STATUS_MISSING_IN_LEDGER,
    STATUS_MISSING_IN_BANK
)


def is_transposition_error(amt1: float, amt2: float) -> bool:
    """
    Accounting heuristic: If the difference between two amounts is divisible by 9,
    it strongly indicates an inverted digit or transposition error (e.g., $45 vs $54, $189 vs $198).
    """
    diff = round(abs(amt1 - amt2), 2)
    if diff <= 0:
        return False
    # Check cents in integer arithmetic to avoid floating point precision issues
    cents_diff = int(round(diff * 100))
    return cents_diff % 9 == 0


def has_fee_keyword(desc: str) -> bool:
    """Checks if description contains fee-related terminology."""
    if not desc:
        return False
    desc_upper = str(desc).upper()
    return any(keyword in desc_upper for keyword in FEE_KEYWORDS)


def classify_root_cause(
    status: str,
    bank_amount: Optional[float] = None,
    ledger_amount: Optional[float] = None,
    bank_date: Optional[date] = None,
    ledger_date: Optional[date] = None,
    bank_desc: str = "",
    ledger_desc: str = "",
    days_difference: int = 0
) -> str:
    """
    Determines the root cause of a reconciliation item or discrepancy.
    """
    if status == STATUS_EXACT_MATCH:
        return "Clean Match (No Discrepancy)"

    if status == STATUS_TIMING_MATCH:
        return f"{RC_TIMING_LAG} ({days_difference} days clearing delay)"

    if status in (STATUS_DUPLICATE_BANK, STATUS_DUPLICATE_LEDGER):
        source = "Bank Statement" if status == STATUS_DUPLICATE_BANK else "General Ledger"
        return f"{RC_DUPLICATE_POSTING} ({source})"

    if status == STATUS_AMOUNT_MISMATCH:
        b_amt = bank_amount if bank_amount is not None else 0.0
        l_amt = ledger_amount if ledger_amount is not None else 0.0
        diff = round(abs(b_amt - l_amt), 2)

        # Micro-rounding / penny variance
        if diff <= 0.05:
            return f"{RC_ROUNDING_FX} (${diff:.2f} variance)"

        # Check for fee deduction embedded in transaction
        if has_fee_keyword(bank_desc) or diff in [15.0, 20.0, 25.0, 30.0, 35.0, 45.0, 50.0]:
            return f"{RC_BANK_FEE} (Deducted ${diff:.2f})"

        # Check for transposition error (divisible by 9 rule)
        if is_transposition_error(b_amt, l_amt):
            return f"{RC_TRANSPOSITION} (Diff: ${diff:.2f}, Divisible by 9)"

        return f"{RC_PENDING_INVESTIGATION} (Amount mismatch of ${diff:.2f})"

    if status == STATUS_MISSING_IN_LEDGER:
        # Bank item not in GL
        if has_fee_keyword(bank_desc):
            return f"{RC_BANK_FEE} (Direct Bank Assessment)"
        return f"{RC_UNRECORDED_CASH} (Direct debit/deposit not posted to GL)"

    if status == STATUS_MISSING_IN_BANK:
        # Ledger item not in Bank
        return "Outstanding Check / Deposit In Transit (Pending Bank Clearance)"

    return RC_PENDING_INVESTIGATION
