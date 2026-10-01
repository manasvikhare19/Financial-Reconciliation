"""
Validation and Integrity Engine.
Executes pre-reconciliation controls, data quality checks, and schema validation.
"""

from typing import Dict, Any, List, Tuple
import pandas as pd
from config import BANK_REQUIRED_COLUMNS, LEDGER_REQUIRED_COLUMNS


class ValidationResult:
    def __init__(self, dataset_name: str):
        self.dataset_name = dataset_name
        self.is_valid: bool = True
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.metrics: Dict[str, Any] = {}

    def add_error(self, message: str):
        self.errors.append(message)
        self.is_valid = False

    def add_warning(self, message: str):
        self.warnings.append(message)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dataset_name": self.dataset_name,
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "metrics": self.metrics
        }


def validate_financial_dataset(df: pd.DataFrame, dataset_type: str = "bank") -> ValidationResult:
    """
    Validates financial dataset against critical accounting controls and schema requirements.
    """
    result = ValidationResult(dataset_name=dataset_type.upper())
    required_cols = BANK_REQUIRED_COLUMNS if dataset_type.lower() == "bank" else LEDGER_REQUIRED_COLUMNS

    # 1. Schema Check
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        result.add_error(f"Missing mandatory columns: {', '.join(missing_cols)}")
        return result

    total_rows = len(df)
    result.metrics["total_records"] = total_rows

    if total_rows == 0:
        result.add_error("Dataset contains zero records.")
        return result

    # 2. Date Integrity Check
    null_dates = df["date"].isna().sum()
    if null_dates > 0:
        result.add_error(f"Found {null_dates} records with invalid or missing dates.")
    result.metrics["null_dates_count"] = int(null_dates)

    # 3. Amount Integrity Check
    null_amounts = df["amount"].isna().sum()
    if null_amounts > 0:
        result.add_error(f"Found {null_amounts} records with missing amounts.")

    zero_amounts = (df["amount"] == 0).sum()
    if zero_amounts > 0:
        result.add_warning(f"Found {zero_amounts} records with zero amounts ($0.00).")
    result.metrics["zero_amounts_count"] = int(zero_amounts)

    total_debits = df[df["amount"] < 0]["amount"].sum()
    total_credits = df[df["amount"] > 0]["amount"].sum()
    net_sum = df["amount"].sum()

    result.metrics["total_debits"] = round(float(total_debits), 2)
    result.metrics["total_credits"] = round(float(total_credits), 2)
    result.metrics["net_sum"] = round(float(net_sum), 2)

    # 4. Duplicate Transaction ID Check (Key Integrity)
    if "transaction_id" in df.columns:
        duplicate_ids = df[df.duplicated(subset=["transaction_id"], keep=False)]
        dup_count = len(duplicate_ids)
        if dup_count > 0:
            result.add_warning(
                f"Found {dup_count} records sharing duplicate transaction IDs. Will be evaluated in reconciliation engine."
            )
        result.metrics["duplicate_id_count"] = int(dup_count)

    # 5. Missing Reference Numbers Check
    blank_refs = (df["reference_no"] == "").sum()
    if blank_refs > 0:
        result.add_warning(f"Found {blank_refs} records without a reference/check/invoice number.")
    result.metrics["blank_reference_count"] = int(blank_refs)

    return result


def validate_both_datasets(bank_df: pd.DataFrame, ledger_df: pd.DataFrame) -> Tuple[ValidationResult, ValidationResult, bool]:
    """
    Validates both Bank and Ledger datasets and returns overall feasibility.
    """
    bank_val = validate_financial_dataset(bank_df, "bank")
    ledger_val = validate_financial_dataset(ledger_df, "ledger")
    can_proceed = bank_val.is_valid and ledger_val.is_valid
    return bank_val, ledger_val, can_proceed
