"""
Database and Audit Logging Module.
Provides SQLite persistence for reconciliation runs, granular items, and immutable audit logs.
"""

from typing import List, Dict, Any, Optional
import sqlite3
import datetime
from pathlib import Path
import pandas as pd
from config import DATABASE_PATH


class DatabaseManager:
    def __init__(self, db_path: Path = DATABASE_PATH):
        self.db_path = db_path
        self._initialize_schema()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize_schema(self):
        """Creates tables and indexes if they do not exist."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 1. Reconciliation Runs Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS reconciliation_runs (
                run_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                executed_by TEXT NOT NULL,
                bank_filename TEXT,
                ledger_filename TEXT,
                total_bank_records INTEGER,
                total_ledger_records INTEGER,
                total_bank_amount REAL,
                total_ledger_amount REAL,
                net_variance REAL,
                match_rate_pct REAL,
                discrepancy_rate_pct REAL,
                date_tolerance_days INTEGER,
                amount_tolerance REAL,
                status TEXT
            )
            """)

            # 2. Granular Reconciliation Items Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS reconciliation_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                reconciliation_id TEXT,
                status TEXT NOT NULL,
                reference_no TEXT,
                bank_trx_id TEXT,
                ledger_trx_id TEXT,
                bank_date TEXT,
                ledger_date TEXT,
                date_diff_days INTEGER,
                bank_amount REAL,
                ledger_amount REAL,
                variance REAL,
                bank_description TEXT,
                ledger_description TEXT,
                root_cause TEXT,
                requires_action INTEGER,
                FOREIGN KEY (run_id) REFERENCES reconciliation_runs(run_id)
            )
            """)

            # 3. Immutable Audit Trail Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                run_id TEXT,
                action TEXT NOT NULL,
                actor TEXT NOT NULL,
                details TEXT
            )
            """)

            # Indexes for reporting performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_run_id ON reconciliation_items (run_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_status ON reconciliation_items (status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_run_id ON audit_logs (run_id)")

            conn.commit()

    def log_audit(self, action: str, actor: str = "System", run_id: Optional[str] = None, details: str = ""):
        """Appends an immutable entry to the audit log."""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO audit_logs (timestamp, run_id, action, actor, details)
            VALUES (?, ?, ?, ?, ?)
            """, (timestamp, run_id, action, actor, details))
            conn.commit()

    def save_run(
        self,
        run_id: str,
        kpis: Dict[str, Any],
        results_df: pd.DataFrame,
        bank_filename: str = "Bank_Statement",
        ledger_filename: str = "General_Ledger",
        executed_by: str = "Financial Controller",
        date_tolerance_days: int = 5,
        amount_tolerance: float = 0.01
    ):
        """Saves a reconciliation run, all line items, and audit entries."""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Insert Run
            cursor.execute("""
            INSERT OR REPLACE INTO reconciliation_runs (
                run_id, timestamp, executed_by, bank_filename, ledger_filename,
                total_bank_records, total_ledger_records, total_bank_amount, total_ledger_amount,
                net_variance, match_rate_pct, discrepancy_rate_pct,
                date_tolerance_days, amount_tolerance, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run_id,
                timestamp,
                executed_by,
                bank_filename,
                ledger_filename,
                kpis.get("total_bank_records", 0),
                kpis.get("total_ledger_records", 0),
                kpis.get("total_bank_amount", 0.0),
                kpis.get("total_ledger_amount", 0.0),
                kpis.get("net_reconciliation_variance", 0.0),
                kpis.get("match_rate_pct", 0.0),
                kpis.get("discrepancy_rate_pct", 0.0),
                date_tolerance_days,
                amount_tolerance,
                "COMPLETED"
            ))

            # Prepare items
            items_df = results_df.copy()
            items_df["run_id"] = run_id
            items_df["requires_action"] = items_df["requires_action"].astype(int)

            # Convert dates to string format for SQLite
            if "bank_date" in items_df.columns:
                items_df["bank_date"] = items_df["bank_date"].astype(str).replace({"None": None, "nan": None, "NaT": None})
            if "ledger_date" in items_df.columns:
                items_df["ledger_date"] = items_df["ledger_date"].astype(str).replace({"None": None, "nan": None, "NaT": None})

            records_to_insert = items_df[[
                "run_id", "reconciliation_id", "status", "reference_no",
                "bank_trx_id", "ledger_trx_id", "bank_date", "ledger_date",
                "date_diff_days", "bank_amount", "ledger_amount", "variance",
                "bank_description", "ledger_description", "root_cause", "requires_action"
            ]].to_dict(orient="records")

            cursor.executemany("""
            INSERT INTO reconciliation_items (
                run_id, reconciliation_id, status, reference_no,
                bank_trx_id, ledger_trx_id, bank_date, ledger_date,
                date_diff_days, bank_amount, ledger_amount, variance,
                bank_description, ledger_description, root_cause, requires_action
            ) VALUES (
                :run_id, :reconciliation_id, :status, :reference_no,
                :bank_trx_id, :ledger_trx_id, :bank_date, :ledger_date,
                :date_diff_days, :bank_amount, :ledger_amount, :variance,
                :bank_description, :ledger_description, :root_cause, :requires_action
            )
            """, records_to_insert)

            conn.commit()

        self.log_audit(
            action="RECONCILIATION_RUN_COMPLETED",
            actor=executed_by,
            run_id=run_id,
            details=f"Reconciled {kpis.get('total_bank_records')} bank and {kpis.get('total_ledger_records')} ledger rows. Net Variance: ${kpis.get('net_reconciliation_variance', 0.0):.2f}"
        )

    def get_runs(self) -> pd.DataFrame:
        """Returns all reconciliation runs sorted by timestamp desc."""
        with self.get_connection() as conn:
            return pd.read_sql_query("SELECT * FROM reconciliation_runs ORDER BY timestamp DESC", conn)

    def get_run_items(self, run_id: str) -> pd.DataFrame:
        """Returns all reconciliation items for a specific run."""
        with self.get_connection() as conn:
            return pd.read_sql_query(
                "SELECT * FROM reconciliation_items WHERE run_id = ? ORDER BY id ASC",
                conn,
                params=(run_id,)
            )

    def get_audit_trail(self, run_id: Optional[str] = None, limit: int = 100) -> pd.DataFrame:
        """Returns chronological audit events."""
        with self.get_connection() as conn:
            if run_id:
                return pd.read_sql_query(
                    "SELECT * FROM audit_logs WHERE run_id = ? ORDER BY log_id DESC LIMIT ?",
                    conn,
                    params=(run_id, limit)
                )
            else:
                return pd.read_sql_query(
                    "SELECT * FROM audit_logs ORDER BY log_id DESC LIMIT ?",
                    conn,
                    params=(limit,)
                )

    def get_top_exceptions(self, run_id: str, limit: int = 10) -> pd.DataFrame:
        """SQL query retrieving the top largest dollar discrepancies."""
        query = """
        SELECT
            reconciliation_id,
            status,
            reference_no,
            bank_amount,
            ledger_amount,
            variance,
            root_cause,
            bank_description,
            ledger_description
        FROM reconciliation_items
        WHERE run_id = ? AND requires_action = 1
        ORDER BY ABS(variance) DESC
        LIMIT ?
        """
        with self.get_connection() as conn:
            return pd.read_sql_query(query, conn, params=(run_id, limit))

    def execute_custom_query(self, sql_query: str) -> pd.DataFrame:
        """Executes read-only SQL query for custom data analytics."""
        # Restrict destructive operations for safety
        normalized = sql_query.strip().upper()
        if any(bad in normalized for bad in ["DROP", "DELETE", "TRUNCATE", "ALTER", "INSERT", "UPDATE"]):
            raise ValueError("Only read-only SELECT queries are permitted in this console.")

        with self.get_connection() as conn:
            return pd.read_sql_query(sql_query, conn)
