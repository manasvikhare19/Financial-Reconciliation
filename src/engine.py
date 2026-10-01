"""
Reconciliation Engine.
Executes multi-pass matching, anomaly detection, discrepancy calculation, and controls classification.
"""

from typing import Dict, Any, List, Tuple
from datetime import date
import pandas as pd
import numpy as np

from config import (
    DEFAULT_DATE_TOLERANCE_DAYS,
    DEFAULT_AMOUNT_TOLERANCE,
    STATUS_EXACT_MATCH,
    STATUS_TIMING_MATCH,
    STATUS_AMOUNT_MISMATCH,
    STATUS_DUPLICATE_BANK,
    STATUS_DUPLICATE_LEDGER,
    STATUS_MISSING_IN_LEDGER,
    STATUS_MISSING_IN_BANK
)
from src.root_cause import classify_root_cause


class ReconciliationEngine:
    def __init__(
        self,
        date_tolerance_days: int = DEFAULT_DATE_TOLERANCE_DAYS,
        amount_tolerance: float = DEFAULT_AMOUNT_TOLERANCE
    ):
        self.date_tolerance_days = date_tolerance_days
        self.amount_tolerance = amount_tolerance

    def reconcile(
        self,
        bank_df: pd.DataFrame,
        ledger_df: pd.DataFrame
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Executes multi-pass reconciliation between Bank transactions and General Ledger.
        Returns:
            - reconciled_items_df: DataFrame containing all reconciled and exception rows.
            - summary_kpis: Dictionary of reconciliation metrics and discrepancy rates.
        """
        b_df = bank_df.copy()
        l_df = ledger_df.copy()

        # Add index trackers
        b_df["_bank_idx"] = b_df.index
        l_df["_ledger_idx"] = l_df.index

        b_matched_indices = set()
        l_matched_indices = set()
        reconciled_rows = []

        # =====================================================================
        # PASS 0: Intra-dataset Duplicate Flagging
        # Detect records with identical reference and amount within each dataset
        # =====================================================================
        b_dups = b_df[b_df["reference_no"] != ""].duplicated(subset=["reference_no", "amount"], keep=False)
        b_dup_indices = set(b_df[b_df["reference_no"] != ""][b_dups].index)

        l_dups = l_df[l_df["reference_no"] != ""].duplicated(subset=["reference_no", "amount"], keep=False)
        l_dup_indices = set(l_df[l_df["reference_no"] != ""][l_dups].index)

        # =====================================================================
        # PASS 1: Exact Match (Reference No + Exact Amount + Exact Date)
        # Only evaluate non-duplicate records first
        # =====================================================================
        for b_idx, b_row in b_df.iterrows():
            if b_idx in b_matched_indices or b_idx in b_dup_indices:
                continue
            ref = b_row["reference_no"]
            amt = b_row["amount"]
            dt = b_row["date"]

            if not ref:
                continue

            # Candidate in ledger
            candidates = l_df[
                (~l_df.index.isin(l_matched_indices)) &
                (~l_df.index.isin(l_dup_indices)) &
                (l_df["reference_no"] == ref) &
                (np.isclose(l_df["amount"], amt, atol=self.amount_tolerance)) &
                (l_df["date"] == dt)
            ]

            if not candidates.empty:
                l_idx = candidates.index[0]
                l_row = candidates.loc[l_idx]

                b_matched_indices.add(b_idx)
                l_matched_indices.add(l_idx)

                reconciled_rows.append({
                    "reconciliation_id": f"REC_{len(reconciled_rows)+1:06d}",
                    "status": STATUS_EXACT_MATCH,
                    "reference_no": ref,
                    "bank_trx_id": b_row.get("transaction_id", ""),
                    "ledger_trx_id": l_row.get("transaction_id", ""),
                    "bank_date": b_row["date"],
                    "ledger_date": l_row["date"],
                    "date_diff_days": 0,
                    "bank_amount": round(float(amt), 2),
                    "ledger_amount": round(float(l_row["amount"]), 2),
                    "variance": 0.0,
                    "bank_description": b_row.get("description", ""),
                    "ledger_description": l_row.get("description", ""),
                    "root_cause": classify_root_cause(STATUS_EXACT_MATCH),
                    "requires_action": False
                })

        # =====================================================================
        # PASS 2: Date-Tolerant Timing Match (Reference + Amount + Date Window)
        # Captures transit delays between issuance and bank clearing
        # =====================================================================
        for b_idx, b_row in b_df.iterrows():
            if b_idx in b_matched_indices or b_idx in b_dup_indices:
                continue
            ref = b_row["reference_no"]
            amt = b_row["amount"]
            b_dt = b_row["date"]

            if not ref or pd.isna(b_dt):
                continue

            candidates = l_df[
                (~l_df.index.isin(l_matched_indices)) &
                (~l_df.index.isin(l_dup_indices)) &
                (l_df["reference_no"] == ref) &
                (np.isclose(l_df["amount"], amt, atol=self.amount_tolerance))
            ]

            if not candidates.empty:
                # Find candidate with closest date within tolerance
                valid_candidates = []
                for l_idx, l_row in candidates.iterrows():
                    l_dt = l_row["date"]
                    if pd.notna(l_dt):
                        days_diff = abs((b_dt - l_dt).days)
                        if days_diff <= self.date_tolerance_days:
                            valid_candidates.append((days_diff, l_idx, l_row))

                if valid_candidates:
                    valid_candidates.sort(key=lambda x: x[0])
                    days_diff, l_idx, l_row = valid_candidates[0]

                    b_matched_indices.add(b_idx)
                    l_matched_indices.add(l_idx)

                    reconciled_rows.append({
                        "reconciliation_id": f"REC_{len(reconciled_rows)+1:06d}",
                        "status": STATUS_TIMING_MATCH,
                        "reference_no": ref,
                        "bank_trx_id": b_row.get("transaction_id", ""),
                        "ledger_trx_id": l_row.get("transaction_id", ""),
                        "bank_date": b_dt,
                        "ledger_date": l_row["date"],
                        "date_diff_days": days_diff,
                        "bank_amount": round(float(amt), 2),
                        "ledger_amount": round(float(l_row["amount"]), 2),
                        "variance": 0.0,
                        "bank_description": b_row.get("description", ""),
                        "ledger_description": l_row.get("description", ""),
                        "root_cause": classify_root_cause(
                            STATUS_TIMING_MATCH,
                            days_difference=days_diff
                        ),
                        "requires_action": False
                    })

        # =====================================================================
        # PASS 3: Amount Mismatch (Reference Match, but Amount Differs)
        # =====================================================================
        for b_idx, b_row in b_df.iterrows():
            if b_idx in b_matched_indices or b_idx in b_dup_indices:
                continue
            ref = b_row["reference_no"]
            b_amt = b_row["amount"]
            b_dt = b_row["date"]

            if not ref:
                continue

            candidates = l_df[
                (~l_df.index.isin(l_matched_indices)) &
                (~l_df.index.isin(l_dup_indices)) &
                (l_df["reference_no"] == ref)
            ]

            if not candidates.empty:
                # Find candidate with closest date within tolerance
                for l_idx, l_row in candidates.iterrows():
                    l_dt = l_row["date"]
                    days_diff = abs((b_dt - l_dt).days) if (pd.notna(b_dt) and pd.notna(l_dt)) else 999
                    if days_diff <= self.date_tolerance_days:
                        l_amt = l_row["amount"]
                        variance = round(float(b_amt - l_amt), 2)

                        b_matched_indices.add(b_idx)
                        l_matched_indices.add(l_idx)

                        root_cause = classify_root_cause(
                            STATUS_AMOUNT_MISMATCH,
                            bank_amount=b_amt,
                            ledger_amount=l_amt,
                            bank_date=b_dt,
                            ledger_date=l_dt,
                            bank_desc=b_row.get("description", ""),
                            ledger_desc=l_row.get("description", ""),
                            days_difference=days_diff
                        )

                        reconciled_rows.append({
                            "reconciliation_id": f"REC_{len(reconciled_rows)+1:06d}",
                            "status": STATUS_AMOUNT_MISMATCH,
                            "reference_no": ref,
                            "bank_trx_id": b_row.get("transaction_id", ""),
                            "ledger_trx_id": l_row.get("transaction_id", ""),
                            "bank_date": b_dt,
                            "ledger_date": l_dt,
                            "date_diff_days": days_diff,
                            "bank_amount": round(float(b_amt), 2),
                            "ledger_amount": round(float(l_amt), 2),
                            "variance": variance,
                            "bank_description": b_row.get("description", ""),
                            "ledger_description": l_row.get("description", ""),
                            "root_cause": root_cause,
                            "requires_action": True
                        })
                        break

        # =====================================================================
        # PASS 4: Handle Duplicates in Bank
        # =====================================================================
        for b_idx in b_dup_indices:
            if b_idx in b_matched_indices:
                continue
            b_row = b_df.loc[b_idx]
            b_matched_indices.add(b_idx)
            reconciled_rows.append({
                "reconciliation_id": f"REC_{len(reconciled_rows)+1:06d}",
                "status": STATUS_DUPLICATE_BANK,
                "reference_no": b_row.get("reference_no", ""),
                "bank_trx_id": b_row.get("transaction_id", ""),
                "ledger_trx_id": None,
                "bank_date": b_row.get("date"),
                "ledger_date": None,
                "date_diff_days": None,
                "bank_amount": round(float(b_row["amount"]), 2),
                "ledger_amount": 0.0,
                "variance": round(float(b_row["amount"]), 2),
                "bank_description": b_row.get("description", ""),
                "ledger_description": "",
                "root_cause": classify_root_cause(STATUS_DUPLICATE_BANK),
                "requires_action": True
            })

        # =====================================================================
        # PASS 5: Handle Duplicates in Ledger
        # =====================================================================
        for l_idx in l_dup_indices:
            if l_idx in l_matched_indices:
                continue
            l_row = l_df.loc[l_idx]
            l_matched_indices.add(l_idx)
            reconciled_rows.append({
                "reconciliation_id": f"REC_{len(reconciled_rows)+1:06d}",
                "status": STATUS_DUPLICATE_LEDGER,
                "reference_no": l_row.get("reference_no", ""),
                "bank_trx_id": None,
                "ledger_trx_id": l_row.get("transaction_id", ""),
                "bank_date": None,
                "ledger_date": l_row.get("date"),
                "date_diff_days": None,
                "bank_amount": 0.0,
                "ledger_amount": round(float(l_row["amount"]), 2),
                "variance": round(float(-l_row["amount"]), 2),
                "bank_description": "",
                "ledger_description": l_row.get("description", ""),
                "root_cause": classify_root_cause(STATUS_DUPLICATE_LEDGER),
                "requires_action": True
            })

        # =====================================================================
        # PASS 6: Unmatched Bank Transactions (Missing in Ledger)
        # =====================================================================
        for b_idx, b_row in b_df.iterrows():
            if b_idx in b_matched_indices:
                continue
            b_matched_indices.add(b_idx)
            b_amt = round(float(b_row["amount"]), 2)
            reconciled_rows.append({
                "reconciliation_id": f"REC_{len(reconciled_rows)+1:06d}",
                "status": STATUS_MISSING_IN_LEDGER,
                "reference_no": b_row.get("reference_no", ""),
                "bank_trx_id": b_row.get("transaction_id", ""),
                "ledger_trx_id": None,
                "bank_date": b_row.get("date"),
                "ledger_date": None,
                "date_diff_days": None,
                "bank_amount": b_amt,
                "ledger_amount": 0.0,
                "variance": b_amt,
                "bank_description": b_row.get("description", ""),
                "ledger_description": "",
                "root_cause": classify_root_cause(
                    STATUS_MISSING_IN_LEDGER,
                    bank_amount=b_amt,
                    bank_desc=b_row.get("description", "")
                ),
                "requires_action": True
            })

        # =====================================================================
        # PASS 7: Unmatched Ledger Transactions (Missing in Bank)
        # =====================================================================
        for l_idx, l_row in l_df.iterrows():
            if l_idx in l_matched_indices:
                continue
            l_matched_indices.add(l_idx)
            l_amt = round(float(l_row["amount"]), 2)
            reconciled_rows.append({
                "reconciliation_id": f"REC_{len(reconciled_rows)+1:06d}",
                "status": STATUS_MISSING_IN_BANK,
                "reference_no": l_row.get("reference_no", ""),
                "bank_trx_id": None,
                "ledger_trx_id": l_row.get("transaction_id", ""),
                "bank_date": None,
                "ledger_date": l_row.get("date"),
                "date_diff_days": None,
                "bank_amount": 0.0,
                "ledger_amount": l_amt,
                "variance": round(-l_amt, 2),
                "bank_description": "",
                "ledger_description": l_row.get("description", ""),
                "root_cause": classify_root_cause(
                    STATUS_MISSING_IN_BANK,
                    ledger_amount=l_amt,
                    ledger_desc=l_row.get("description", "")
                ),
                "requires_action": True
            })

        # Convert to DataFrame
        results_df = pd.DataFrame(reconciled_rows)

        # Calculate Totals and KPIs
        kpis = self._calculate_kpis(b_df, l_df, results_df)

        return results_df, kpis

    def _calculate_kpis(
        self,
        b_df: pd.DataFrame,
        l_df: pd.DataFrame,
        results_df: pd.DataFrame
    ) -> Dict[str, Any]:
        """Calculates executive KPI metrics, discrepancy rates, and volume statistics."""
        total_bank_records = len(b_df)
        total_ledger_records = len(l_df)
        total_bank_amount = round(float(b_df["amount"].sum()), 2)
        total_ledger_amount = round(float(l_df["amount"].sum()), 2)
        net_reconciliation_variance = round(total_bank_amount - total_ledger_amount, 2)

        matched_mask = results_df["status"].isin([STATUS_EXACT_MATCH, STATUS_TIMING_MATCH])
        matched_count = int(matched_mask.sum())
        matched_bank_val = round(float(results_df[matched_mask]["bank_amount"].sum()), 2)

        exception_mask = ~matched_mask
        exception_count = int(exception_mask.sum())
        exception_variance_gross = round(float(results_df[exception_mask]["variance"].abs().sum()), 2)

        total_unique_items = len(results_df)

        match_rate_count = round((matched_count / total_unique_items * 100), 2) if total_unique_items > 0 else 0.0
        discrepancy_rate_count = round((exception_count / total_unique_items * 100), 2) if total_unique_items > 0 else 0.0

        # Status Breakdown Table
        status_counts = results_df["status"].value_counts().to_dict()
        status_variances = results_df.groupby("status")["variance"].sum().round(2).to_dict()

        return {
            "total_bank_records": total_bank_records,
            "total_ledger_records": total_ledger_records,
            "total_bank_amount": total_bank_amount,
            "total_ledger_amount": total_ledger_amount,
            "net_reconciliation_variance": net_reconciliation_variance,
            "gross_exception_variance": exception_variance_gross,
            "total_reconciled_items": total_unique_items,
            "matched_count": matched_count,
            "matched_amount": matched_bank_val,
            "exception_count": exception_count,
            "match_rate_pct": match_rate_count,
            "discrepancy_rate_pct": discrepancy_rate_count,
            "status_breakdown": {
                status: {
                    "count": int(status_counts.get(status, 0)),
                    "variance": float(status_variances.get(status, 0.0))
                }
                for status in [
                    STATUS_EXACT_MATCH,
                    STATUS_TIMING_MATCH,
                    STATUS_AMOUNT_MISMATCH,
                    STATUS_DUPLICATE_BANK,
                    STATUS_DUPLICATE_LEDGER,
                    STATUS_MISSING_IN_LEDGER,
                    STATUS_MISSING_IN_BANK
                ]
            }
        }
