"""
Unit tests for data validation and schema integrity checks.
"""

from datetime import date
import pandas as pd
import pytest

from src.data_loader import clean_amount, map_columns
from src.validation import validate_financial_dataset, validate_both_datasets


def test_clean_amount_variations():
    """Verify clean_amount handles standard and accounting formats."""
    assert clean_amount(150.75) == 150.75
    assert clean_amount("150.75") == 150.75
    assert clean_amount("$1,234.56") == 1234.56
    assert clean_amount("($500.00)") == -500.00
    assert clean_amount("-250.50") == -250.50
    assert clean_amount("100.00 CR") == -100.00
    assert clean_amount(None) == 0.0
    assert clean_amount("") == 0.0


def test_map_columns_aliases():
    """Verify column aliases map to canonical field names."""
    raw_df = pd.DataFrame({
        "Trans Date": ["2026-09-01"],
        "Trx Amount": [100.0],
        "Voucher No": ["REF-001"],
        "Memo": ["Payment for cloud hosting"],
        "ID": ["BNK_001"]
    })
    mapped_df = map_columns(raw_df)
    assert "date" in mapped_df.columns
    assert "amount" in mapped_df.columns
    assert "reference_no" in mapped_df.columns
    assert "description" in mapped_df.columns
    assert "transaction_id" in mapped_df.columns


def test_validate_dataset_valid():
    """Verify valid dataset passes validation with no errors."""
    valid_df = pd.DataFrame({
        "transaction_id": ["TX-1", "TX-2"],
        "date": [date(2026, 9, 1), date(2026, 9, 2)],
        "amount": [100.0, -50.0],
        "reference_no": ["REF-1", "REF-2"],
        "description": ["Invoice 1", "Bill 2"]
    })
    res = validate_financial_dataset(valid_df, "bank")
    assert res.is_valid is True
    assert len(res.errors) == 0
    assert res.metrics["total_records"] == 2
    assert res.metrics["net_sum"] == 50.0


def test_validate_dataset_missing_columns():
    """Verify validation fails when mandatory columns are missing."""
    invalid_df = pd.DataFrame({
        "date": [date(2026, 9, 1)],
        "amount": [100.0]
    })
    res = validate_financial_dataset(invalid_df, "bank")
    assert res.is_valid is False
    assert any("Missing mandatory columns" in err for err in res.errors)


def test_validate_dataset_null_dates():
    """Verify validation detects missing or null dates."""
    df_null_date = pd.DataFrame({
        "transaction_id": ["TX-1"],
        "date": [None],
        "amount": [100.0],
        "reference_no": ["REF-1"],
        "description": ["Test"]
    })
    res = validate_financial_dataset(df_null_date, "ledger")
    assert res.is_valid is False
    assert any("invalid or missing dates" in err for err in res.errors)
