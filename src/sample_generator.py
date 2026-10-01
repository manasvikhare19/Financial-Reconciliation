"""
Sample Financial Data Generator.
Produces realistic Bank Statements and General Ledger datasets containing controlled anomalies:
- Exact matches
- Timing clearance delays
- Amount mismatches (transposition typos, fee deductions)
- Intra-dataset duplicates
- Unrecorded direct debits (Missing in Ledger)
- Outstanding checks / deposits in transit (Missing in Bank)
"""

from typing import Tuple
from datetime import date, timedelta
import random
import pandas as pd
from config import DATA_DIR


def generate_sample_datasets(
    n_base: int = 500,
    seed: int = 42
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Generates realistic corporate banking and general ledger data.
    """
    random.seed(seed)

    base_date = date(2026, 9, 1)

    vendors = [
        ("AWS CLOUD SERVICES", "CLOUD_INFRA", -4250.00, -12500.00),
        ("MICROSOFT ENTERPRISE", "SOFTWARE_LIC", -1800.00, -7500.00),
        ("OFFICE DEPOT SUPPLIES", "OFFICE_EXP", -150.00, -1200.00),
        ("CUSHMAN WAKEFIELD LEASE", "RENT_EXP", -14500.00, -14500.00),
        ("ADP TOTALSOURCE PAYROLL", "PAYROLL_EXP", -85000.00, -115000.00),
        ("CONEDISON ELECTRIC", "UTILITIES", -850.00, -3200.00),
        ("FEDEX FREIGHT CORP", "LOGISTICS", -320.00, -2100.00),
        ("DELOITTE ADVISORY", "CONSULTING", -8000.00, -25000.00),
    ]

    customers = [
        ("GLOBAL TECH CORP - INV 9021", "AR_COLLECTION", 15000.00, 85000.00),
        ("APEX STRATEGIES - INV 8412", "AR_COLLECTION", 5400.00, 32000.00),
        ("NEXUS HEALTHCARE - INV 7731", "AR_COLLECTION", 12000.00, 48000.00),
        ("HORIZON RETAIL - INV 6519", "AR_COLLECTION", 3500.00, 19500.00),
        ("VANGUARD LOGISTICS - INV 5190", "AR_COLLECTION", 8200.00, 44000.00),
    ]

    bank_records = []
    ledger_records = []

    bank_id_seq = 10001
    ledger_id_seq = 50001
    ref_seq = 1001

    # 1. GENERATE BASE TRANSACTIONS (~70% EXACT MATCHES)
    n_exact = int(n_base * 0.70)
    for _ in range(n_exact):
        day_offset = random.randint(0, 27)
        trx_date = base_date + timedelta(days=day_offset)
        ref_no = f"REF-{ref_seq}"
        ref_seq += 1

        is_customer = random.random() < 0.45
        if is_customer:
            desc, cat, min_amt, max_amt = random.choice(customers)
            amt = round(random.uniform(min_amt, max_amt), 2)
        else:
            desc, cat, min_amt, max_amt = random.choice(vendors)
            amt = round(random.uniform(min_amt, max_amt), 2)

        bank_records.append({
            "transaction_id": f"BNK-{bank_id_seq}",
            "date": trx_date,
            "amount": amt,
            "reference_no": ref_no,
            "description": f"BANK WIRE/ACH: {desc}"
        })
        bank_id_seq += 1

        ledger_records.append({
            "transaction_id": f"GL-{ledger_id_seq}",
            "date": trx_date,
            "amount": amt,
            "reference_no": ref_no,
            "description": f"GL POSTING: {desc} ({cat})"
        })
        ledger_id_seq += 1

    # 2. GENERATE TIMING DIFFERENCES (~12%)
    n_timing = int(n_base * 0.12)
    for _ in range(n_timing):
        day_offset = random.randint(0, 24)
        ledger_date = base_date + timedelta(days=day_offset)
        # Bank clears 1 to 4 days later
        clearing_delay = random.randint(1, 4)
        bank_date = ledger_date + timedelta(days=clearing_delay)

        ref_no = f"REF-{ref_seq}"
        ref_seq += 1

        is_customer = random.random() < 0.35
        desc, cat, min_amt, max_amt = random.choice(customers if is_customer else vendors)
        amt = round(random.uniform(min_amt, max_amt), 2)

        bank_records.append({
            "transaction_id": f"BNK-{bank_id_seq}",
            "date": bank_date,
            "amount": amt,
            "reference_no": ref_no,
            "description": f"CLEARED CHECK/ACH: {desc}"
        })
        bank_id_seq += 1

        ledger_records.append({
            "transaction_id": f"GL-{ledger_id_seq}",
            "date": ledger_date,
            "amount": amt,
            "reference_no": ref_no,
            "description": f"ISSUED PAYMENT: {desc} ({cat})"
        })
        ledger_id_seq += 1

    # 3. GENERATE AMOUNT MISMATCHES (~5%)
    # Including transposition errors and fee deductions
    n_mismatch = int(n_base * 0.05)
    for i in range(n_mismatch):
        day_offset = random.randint(0, 26)
        trx_date = base_date + timedelta(days=day_offset)
        ref_no = f"REF-{ref_seq}"
        ref_seq += 1

        desc, cat, min_amt, max_amt = random.choice(vendors)

        if i % 2 == 0:
            # Transposition error (e.g., $1,450 vs $1,540 -> diff 90, divisible by 9)
            base_val = 1450.00 + (i * 100)
            ledger_amt = -base_val
            # Transpose tens and hundreds digit
            bank_amt = -(base_val + 90.00)
            b_desc = f"ACH DEBIT: {desc}"
            l_desc = f"GL INVOICE: {desc}"
        else:
            # Wire fee deduction ($25 or $30 deducted from customer payment or added to vendor wire)
            fee = 25.00
            ledger_amt = round(random.uniform(2000.00, 8000.00), 2)
            bank_amt = round(ledger_amt - fee, 2)
            b_desc = f"WIRE INCOMING LESS SERVICE FEE: {desc}"
            l_desc = f"AR RECEIVABLE FULL: {desc}"

        bank_records.append({
            "transaction_id": f"BNK-{bank_id_seq}",
            "date": trx_date,
            "amount": bank_amt,
            "reference_no": ref_no,
            "description": b_desc
        })
        bank_id_seq += 1

        ledger_records.append({
            "transaction_id": f"GL-{ledger_id_seq}",
            "date": trx_date,
            "amount": ledger_amt,
            "reference_no": ref_no,
            "description": l_desc
        })
        ledger_id_seq += 1

    # 4. GENERATE DUPLICATE ENTRIES (~4%)
    n_dups = int(n_base * 0.04)
    for _ in range(n_dups):
        day_offset = random.randint(0, 25)
        trx_date = base_date + timedelta(days=day_offset)
        ref_no = f"REF-{ref_seq}"
        ref_seq += 1

        desc, cat, min_amt, max_amt = random.choice(vendors)
        amt = round(random.uniform(min_amt, max_amt), 2)

        # Duplicate voucher in General Ledger (accidental double entry)
        bank_records.append({
            "transaction_id": f"BNK-{bank_id_seq}",
            "date": trx_date,
            "amount": amt,
            "reference_no": ref_no,
            "description": f"ACH DISBURSEMENT: {desc}"
        })
        bank_id_seq += 1

        ledger_records.append({
            "transaction_id": f"GL-{ledger_id_seq}",
            "date": trx_date,
            "amount": amt,
            "reference_no": ref_no,
            "description": f"GL POSTING: {desc} (ORIGINAL ENTRY)"
        })
        ledger_id_seq += 1

        # Duplicate entry
        ledger_records.append({
            "transaction_id": f"GL-{ledger_id_seq}",
            "date": trx_date,
            "amount": amt,
            "reference_no": ref_no,
            "description": f"GL POSTING: {desc} (ACCIDENTAL DUPLICATE POST)"
        })
        ledger_id_seq += 1

    # 5. GENERATE MISSING IN LEDGER (~5%)
    # Bank charges, unrecorded direct debits, tax withholdings
    n_missing_ledger = int(n_base * 0.05)
    for i in range(n_missing_ledger):
        day_offset = random.randint(1, 28)
        trx_date = base_date + timedelta(days=day_offset)
        ref_no = f"BNK-DIR-{ref_seq}"
        ref_seq += 1

        if i % 2 == 0:
            amt = -round(random.choice([15.00, 25.00, 35.00, 50.00, 125.00]), 2)
            desc = "MONTHLY BANK SERVICE CHARGE & MAINTENANCE FEE"
        else:
            amt = -round(random.uniform(250.00, 1800.00), 2)
            desc = "AUTOMATIC DIRECT DEBIT - STATE TAX WITHHOLDING / UTILITY"

        bank_records.append({
            "transaction_id": f"BNK-{bank_id_seq}",
            "date": trx_date,
            "amount": amt,
            "reference_no": ref_no,
            "description": desc
        })
        bank_id_seq += 1

    # 6. GENERATE MISSING IN BANK (~4%)
    # Outstanding checks, deposits in transit recorded in GL near month-end
    n_missing_bank = int(n_base * 0.04)
    for _ in range(n_missing_bank):
        day_offset = random.randint(25, 29)
        trx_date = base_date + timedelta(days=day_offset)
        ref_no = f"CHK-OUT-{ref_seq}"
        ref_seq += 1

        desc, cat, min_amt, max_amt = random.choice(vendors)
        amt = round(random.uniform(min_amt, max_amt), 2)

        ledger_records.append({
            "transaction_id": f"GL-{ledger_id_seq}",
            "date": trx_date,
            "amount": amt,
            "reference_no": ref_no,
            "description": f"OUTSTANDING CHECK MAILED: {desc}"
        })
        ledger_id_seq += 1

    # Shuffle datasets to simulate realistic unsorted files
    random.shuffle(bank_records)
    random.shuffle(ledger_records)

    bank_df = pd.DataFrame(bank_records)
    ledger_df = pd.DataFrame(ledger_records)

    return bank_df, ledger_df


def save_sample_files():
    """Generates and writes CSV and Excel demo files to the data/ directory."""
    DATA_DIR.mkdir(exist_ok=True)
    bank_df, ledger_df = generate_sample_datasets(n_base=500, seed=42)

    bank_csv_path = DATA_DIR / "sample_bank_transactions.csv"
    ledger_csv_path = DATA_DIR / "sample_general_ledger.csv"
    bank_xlsx_path = DATA_DIR / "sample_bank_transactions.xlsx"
    ledger_xlsx_path = DATA_DIR / "sample_general_ledger.xlsx"

    bank_df.to_csv(bank_csv_path, index=False)
    ledger_df.to_csv(ledger_csv_path, index=False)
    bank_df.to_excel(bank_xlsx_path, index=False)
    ledger_df.to_excel(ledger_xlsx_path, index=False)

    print(f"Generated {len(bank_df)} Bank records -> {bank_csv_path}")
    print(f"Generated {len(ledger_df)} General Ledger records -> {ledger_csv_path}")


if __name__ == "__main__":
    save_sample_files()
