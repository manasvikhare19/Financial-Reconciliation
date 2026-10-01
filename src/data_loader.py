"""
Data Ingestion and Normalization Module.
Loads CSV or Excel datasets (Bank Statements, General Ledger) and standardizes schemas.
"""

from typing import Union, IO
import re
import pandas as pd
from config import BANK_REQUIRED_COLUMNS, LEDGER_REQUIRED_COLUMNS


# Common column aliases for financial datasets
COLUMN_ALIASES = {
    "transaction_id": [
        "transaction_id", "trx_id", "tran_id", "trans_id",
        "tx_id", "entry_id", "journal_id", "id"
    ],
    "date": [
        "date", "transaction_date", "trans_date", "trx_date",
        "posting_date", "post_date", "value_date", "effective_date"
    ],
    "amount": [
        "amount", "net_amount", "trx_amount", "transaction_amount",
        "total_amount", "balance_effect", "amt"
    ],
    "reference_no": [
        "reference_no", "reference", "ref_no", "ref", "check_no",
        "cheque_no", "invoice_no", "inv_no", "doc_no", "document_no",
        "voucher_no", "voucher_id", "voucher"
    ],
    "description": [
        "description", "desc", "memo", "details", "narrative",
        "particulars", "transaction_details", "line_description"
    ]
}


def clean_amount(val) -> float:
    """
    Cleans amount values, converting accounting formats like ($1,234.56) or 1,234.56 CR into negative/positive floats.
    """
    if pd.isna(val):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)

    s = str(val).strip()
    # Check for parentheses indicating negative amount: (100.50) -> -100.50
    is_negative = False
    if s.startswith("(") and s.endswith(")"):
        is_negative = True
        s = s[1:-1]
    elif s.endswith("CR") or s.endswith("cr"):
        is_negative = True
        s = s[:-2]
    elif s.startswith("-"):
        is_negative = True
        s = s[1:]

    # Remove currency symbols, commas, spaces
    s = re.sub(r"[^\d.]", "", s)
    if not s:
        return 0.0

    num = float(s)
    return -num if is_negative else num


def map_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Maps varied column names in the source dataset to standard canonical names.
    """
    col_map = {}
    normalized_cols = {re.sub(r"[\s_]+", "_", str(c).strip().lower()): c for c in df.columns}

    for canonical, aliases in COLUMN_ALIASES.items():
        matched_col = None
        for alias in aliases:
            if alias in normalized_cols:
                matched_col = normalized_cols[alias]
                break
        if matched_col:
            col_map[matched_col] = canonical

    df = df.rename(columns=col_map)
    return df


def load_dataset(file_source: Union[str, IO], dataset_type: str = "bank") -> pd.DataFrame:
    """
    Loads financial dataset from a file path or file-like buffer (CSV or Excel).
    Normalizes columns, formats dates, and sanitizes amounts.
    """
    if hasattr(file_source, "name"):
        filename = file_source.name.lower()
    else:
        filename = str(file_source).lower()

    if filename.endswith(".xlsx") or filename.endswith(".xls"):
        df = pd.read_excel(file_source)
    else:
        # Default to CSV with standard encoding detection fallback
        try:
            df = pd.read_csv(file_source)
        except UnicodeDecodeError:
            df = pd.read_csv(file_source, encoding="latin1")

    # Map column headers
    df = map_columns(df)

    # Standardize types
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date

    if "amount" in df.columns:
        df["amount"] = df["amount"].apply(clean_amount).round(2)

    if "reference_no" in df.columns:
        df["reference_no"] = (
            df["reference_no"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
        )
    else:
        df["reference_no"] = ""

    if "transaction_id" in df.columns:
        df["transaction_id"] = (
            df["transaction_id"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
        )
    else:
        df["transaction_id"] = [f"{dataset_type.upper()}_{i+1:05d}" for i in range(len(df))]

    if "description" in df.columns:
        df["description"] = df["description"].fillna("").astype(str).str.strip()
    else:
        df["description"] = ""

    # Add source origin tag
    df["source_dataset"] = dataset_type.upper()

    return df
