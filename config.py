"""
Configuration module for Financial Reconciliation & Controls Dashboard.
Defines parameters, thresholds, paths, and business rules.
"""

from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
EXPORTS_DIR = BASE_DIR / "exports"
DATABASE_PATH = BASE_DIR / "reconciliation.db"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
EXPORTS_DIR.mkdir(exist_ok=True)

# Reconciliation Tolerances & Parameters
DEFAULT_DATE_TOLERANCE_DAYS = 5      # Maximum days window for clearing delays
DEFAULT_AMOUNT_TOLERANCE = 0.01       # Penny/cent rounding tolerance

# Required Columns for Datasets
BANK_REQUIRED_COLUMNS = [
    "transaction_id",
    "date",
    "amount",
    "reference_no",
    "description"
]

LEDGER_REQUIRED_COLUMNS = [
    "transaction_id",
    "date",
    "amount",
    "reference_no",
    "description"
]

# Classification Statuses
STATUS_EXACT_MATCH = "MATCHED_EXACT"
STATUS_TIMING_MATCH = "MATCHED_TIMING_DIFF"
STATUS_AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
STATUS_DUPLICATE_BANK = "DUPLICATE_BANK"
STATUS_DUPLICATE_LEDGER = "DUPLICATE_LEDGER"
STATUS_MISSING_IN_LEDGER = "MISSING_IN_LEDGER"   # Bank transaction not in Ledger
STATUS_MISSING_IN_BANK = "MISSING_IN_BANK"       # Ledger entry not in Bank

# Root Cause Categories
RC_TIMING_LAG = "Timing Difference (Transit Clearing)"
RC_BANK_FEE = "Bank Surcharge / Service Fee"
RC_TRANSPOSITION = "Transposition / Data Entry Typo"
RC_DUPLICATE_POSTING = "Duplicate Voucher / Batch Error"
RC_UNRECORDED_CASH = "Unrecorded Cash Flow / Direct Debit"
RC_ROUNDING_FX = "Rounding / FX Micro-Variance"
RC_PENDING_INVESTIGATION = "Unresolved / General Discrepancy"

# Root Cause Keywords for Fee Detection
FEE_KEYWORDS = [
    "FEE", "SERVICE CHARGE", "WIRE FEE", "ACH FEE", "OVERDRAFT",
    "COMMISSION", "MAINTENANCE", "MONTHLY CHARGE"
]
