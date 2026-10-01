"""
Financial Reconciliation & Controls Dashboard.
Streamlit application providing automated matching, discrepancy classification,
root-cause diagnostics, SQL query workbench, and multi-tab Excel reporting.
"""

import io
from datetime import datetime
import pandas as pd
import numpy as np
import altair as alt
import streamlit as st

from config import (
    DATA_DIR,
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
from src.data_loader import load_dataset
from src.validation import validate_both_datasets
from src.engine import ReconciliationEngine
from src.database import DatabaseManager
from src.excel_exporter import create_reconciliation_excel_bytes


# Page Configuration
st.set_page_config(
    page_title="Financial Reconciliation & Controls",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Corporate CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.1rem;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.0rem;
        color: #4B5563;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 16px;
        text-align: center;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .metric-value {
        font-size: 1.8rem;
        font-weight: bold;
        color: #0F172A;
    }
    .metric-label {
        font-size: 0.85rem;
        font-weight: 600;
        color: #64748B;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .badge-matched {
        background-color: #DEF7EC;
        color: #03543F;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.8rem;
    }
    .badge-exception {
        background-color: #FDE8E8;
        color: #9B1C1C;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.8rem;
    }
</style>
""", unsafe_allow_html=True)

# Initialize Database Manager
db = DatabaseManager()

# Header Banner
st.markdown('<div class="main-header">⚖️ Financial Reconciliation & Controls Dashboard</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-header">Multi-Pass Transaction Matching • Anomaly Detection • Root-Cause Analytics • Internal Controls Audit Trail</div>',
    unsafe_allow_html=True
)

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuration & Controls")

    data_source = st.radio(
        "Select Data Source:",
        ["Sample Realistic Datasets (500 Records)", "Upload Custom Files (CSV/Excel)"]
    )

    bank_file = None
    ledger_file = None

    if data_source == "Upload Custom Files (CSV/Excel)":
        st.subheader("📁 Upload Files")
        bank_file = st.file_uploader("Upload Bank Statement (CSV/XLSX)", type=["csv", "xlsx", "xls"])
        ledger_file = st.file_uploader("Upload General Ledger (CSV/XLSX)", type=["csv", "xlsx", "xls"])
    else:
        st.info("Using embedded pre-validated enterprise datasets with realistic timing, typos, duplicate entries, and fee deductions.")

    st.subheader("🎯 Matching Parameters")
    date_tolerance = st.slider(
        "Date Tolerance Window (Days)",
        min_value=0,
        max_value=14,
        value=DEFAULT_DATE_TOLERANCE_DAYS,
        help="Allowed days between ledger posting and bank clearing to account for transit/clearing delay."
    )

    amount_tolerance = st.number_input(
        "Amount Rounding Tolerance ($)",
        min_value=0.00,
        max_value=1.00,
        value=DEFAULT_AMOUNT_TOLERANCE,
        step=0.01,
        help="Tolerance threshold for micro-rounding / penny discrepancies."
    )

    auditor_name = st.text_input("Auditor / Controller Name", value="Senior Financial Controller")

    run_pipeline = st.button("🚀 Run Reconciliation Pipeline", type="primary", use_container_width=True)


# Initialize session state for persistent results
if "reconciliation_run" not in st.session_state:
    st.session_state["reconciliation_run"] = None


# Load Data Logic
def get_datasets():
    if data_source == "Upload Custom Files (CSV/Excel)":
        if bank_file is not None and ledger_file is not None:
            b_df = load_dataset(bank_file, "bank")
            l_df = load_dataset(ledger_file, "ledger")
            return b_df, l_df, bank_file.name, ledger_file.name
        else:
            return None, None, None, None
    else:
        bank_path = DATA_DIR / "sample_bank_transactions.csv"
        ledger_path = DATA_DIR / "sample_general_ledger.csv"
        if not bank_path.exists() or not ledger_path.exists():
            from src.sample_generator import save_sample_files
            save_sample_files()
        b_df = load_dataset(str(bank_path), "bank")
        l_df = load_dataset(str(ledger_path), "ledger")
        return b_df, l_df, "sample_bank_transactions.csv", "sample_general_ledger.csv"


# Execution Trigger
if run_pipeline or st.session_state["reconciliation_run"] is None:
    b_df, l_df, b_name, l_name = get_datasets()

    if b_df is not None and l_df is not None:
        # Pre-reconciliation validation check
        b_val, l_val, can_proceed = validate_both_datasets(b_df, l_df)

        if not can_proceed:
            st.error("Validation failed! Please fix the errors below before reconciling.")
            for err in b_val.errors + l_val.errors:
                st.error(f"❌ {err}")
        else:
            # Execute Reconciliation
            engine = ReconciliationEngine(
                date_tolerance_days=date_tolerance,
                amount_tolerance=amount_tolerance
            )
            results_df, kpis = engine.reconcile(b_df, l_df)

            run_id = f"REC-RUN-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

            # Save to Database
            db.save_run(
                run_id=run_id,
                kpis=kpis,
                results_df=results_df,
                bank_filename=b_name,
                ledger_filename=l_name,
                executed_by=auditor_name,
                date_tolerance_days=date_tolerance,
                amount_tolerance=amount_tolerance
            )

            st.session_state["reconciliation_run"] = {
                "run_id": run_id,
                "kpis": kpis,
                "results_df": results_df,
                "bank_df": b_df,
                "ledger_df": l_df,
                "b_val": b_val,
                "l_val": l_val,
                "bank_name": b_name,
                "ledger_name": l_name
            }
            st.success(f"✅ Reconciliation completed successfully! Run ID: `{run_id}`")
    else:
        st.warning("Please upload both Bank Statement and General Ledger files to execute reconciliation.")


# Render Dashboard if Run Exists
active_run = st.session_state["reconciliation_run"]

if active_run:
    kpis = active_run["kpis"]
    results_df = active_run["results_df"]
    run_id = active_run["run_id"]

    # Top KPI Summary Cards
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Match Rate</div>
            <div class="metric-value" style="color: #059669;">{kpis['match_rate_pct']:.1f}%</div>
            <span style="font-size: 0.8rem; color: #64748B;">{kpis['matched_count']} / {kpis['total_reconciled_items']} Items</span>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Discrepancy Rate</div>
            <div class="metric-value" style="color: #DC2626;">{kpis['discrepancy_rate_pct']:.1f}%</div>
            <span style="font-size: 0.8rem; color: #64748B;">{kpis['exception_count']} Unreconciled Breaks</span>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Net Variance</div>
            <div class="metric-value" style="color: {'#DC2626' if kpis['net_reconciliation_variance'] != 0 else '#059669'};">
                ${kpis['net_reconciliation_variance']:,.2f}
            </div>
            <span style="font-size: 0.8rem; color: #64748B;">Bank vs. GL Total Balance</span>
        </div>
        """, unsafe_allow_html=True)
    with col4:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Gross Exception Exposure</div>
            <div class="metric-value" style="color: #D97706;">${kpis['gross_exception_variance']:,.2f}</div>
            <span style="font-size: 0.8rem; color: #64748B;">Sum of Absolute Variances</span>
        </div>
        """, unsafe_allow_html=True)
    with col5:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Total Volume Processed</div>
            <div class="metric-value" style="color: #2563EB;">{kpis['total_bank_records'] + kpis['total_ledger_records']}</div>
            <span style="font-size: 0.8rem; color: #64748B;">Bank: {kpis['total_bank_records']} | GL: {kpis['total_ledger_records']}</span>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Main Tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Executive Overview",
        "🔍 Exceptions & Discrepancies",
        "🧠 Root-Cause Diagnostics",
        "💾 SQL Queries & Audit Trail",
        "📥 Export Center"
    ])

    # -------------------------------------------------------------
    # TAB 1: EXECUTIVE OVERVIEW
    # -------------------------------------------------------------
    with tab1:
        st.subheader("Financial Summary & Control Certification")

        col_t1, col_t2 = st.columns([1, 1])

        with col_t1:
            st.markdown("#### Balance Reconciliation Bridge")
            bridge_data = pd.DataFrame([
                {"Metric": "Bank Statement Balance", "Amount ($)": f"${kpis['total_bank_amount']:,.2f}"},
                {"Metric": "General Ledger Balance", "Amount ($)": f"${kpis['total_ledger_amount']:,.2f}"},
                {"Metric": "Net Unreconciled Variance", "Amount ($)": f"${kpis['net_reconciliation_variance']:,.2f}"},
                {"Metric": "Absolute Exception Volume", "Amount ($)": f"${kpis['gross_exception_variance']:,.2f}"},
                {"Metric": "Clean Matched Amount", "Amount ($)": f"${kpis['matched_amount']:,.2f}"},
            ])
            st.table(bridge_data)

            st.markdown("#### Pre-Reconciliation Validation Status")
            b_val = active_run["b_val"]
            l_val = active_run["l_val"]

            val_col1, val_col2 = st.columns(2)
            with val_col1:
                st.markdown(f"**Bank Dataset:** {'🟢 Passed' if b_val.is_valid else '🔴 Failed'}")
                st.caption(f"Records: {b_val.metrics.get('total_records', 0)} | Debits: ${b_val.metrics.get('total_debits', 0):,.2f} | Credits: ${b_val.metrics.get('total_credits', 0):,.2f}")
            with val_col2:
                st.markdown(f"**General Ledger:** {'🟢 Passed' if l_val.is_valid else '🔴 Failed'}")
                st.caption(f"Records: {l_val.metrics.get('total_records', 0)} | Debits: ${l_val.metrics.get('total_debits', 0):,.2f} | Credits: ${l_val.metrics.get('total_credits', 0):,.2f}")

        with col_t2:
            st.markdown("#### Status Category Distribution")
            status_df = pd.DataFrame([
                {"Status": k.replace("_", " "), "Count": v["count"], "Variance": v["variance"]}
                for k, v in kpis["status_breakdown"].items()
                if v["count"] > 0
            ])

            if not status_df.empty:
                chart = alt.Chart(status_df).mark_bar(cornerRadius=4).encode(
                    x=alt.X("Count:Q", title="Number of Items"),
                    y=alt.Y("Status:N", sort="-x", title=""),
                    color=alt.Color("Status:N", legend=None, scale=alt.Scale(scheme="category10")),
                    tooltip=["Status", "Count", alt.Tooltip("Variance:Q", format="$,.2f")]
                ).properties(height=260)
                st.altair_chart(chart, use_container_width=True)

        st.markdown("---")
        st.markdown("#### 📜 Formal Control Attestation & Sign-Off")
        attest_col1, attest_col2, attest_col3 = st.columns(3)
        with attest_col1:
            st.success("**Prepared By:**\n\nSenior Financial Analyst (Automated Pipeline)\n\n*Status: Verified*")
        with attest_col2:
            st.info(f"**Reconciled & Reviewed By:**\n\n{auditor_name}\n\n*Attestation Date: {datetime.now().strftime('%Y-%m-%d')}*")
        with attest_col3:
            st.warning("**Internal Audit Sign-Off:**\n\nCorporate Compliance Committee\n\n*Status: Pending Final Sign-Off*")

    # -------------------------------------------------------------
    # TAB 2: EXCEPTIONS & DISCREPANCIES
    # -------------------------------------------------------------
    with tab2:
        st.subheader("Reconciliation Exception Workbench")
        st.caption("Drill down into amount mismatches, unrecorded cash flows, duplicate postings, and missing records.")

        exceptions_df = results_df[results_df["requires_action"] == True].copy()

        # Filters
        f_col1, f_col2, f_col3 = st.columns([1, 1, 1])
        with f_col1:
            available_statuses = sorted(list(exceptions_df["status"].unique()))
            selected_statuses = st.multiselect("Filter by Exception Status", options=available_statuses, default=available_statuses)
        with f_col2:
            search_query = st.text_input("Search Reference No / Description", placeholder="e.g. REF-1050, AWS, FEE...")
        with f_col3:
            min_variance = st.number_input("Minimum Absolute Variance ($)", min_value=0.0, value=0.0, step=10.0)

        # Apply Filters
        filtered_df = exceptions_df[exceptions_df["status"].isin(selected_statuses)]
        if min_variance > 0:
            filtered_df = filtered_df[filtered_df["variance"].abs() >= min_variance]
        if search_query:
            q = search_query.strip().upper()
            filtered_df = filtered_df[
                filtered_df["reference_no"].str.upper().str.contains(q) |
                filtered_df["bank_description"].str.upper().str.contains(q) |
                filtered_df["ledger_description"].str.upper().str.contains(q)
            ]

        st.markdown(f"**Showing {len(filtered_df)} of {len(exceptions_df)} Unreconciled Exceptions**")

        display_cols = [
            "reconciliation_id", "status", "reference_no", "bank_amount",
            "ledger_amount", "variance", "root_cause", "bank_date", "ledger_date", "bank_description"
        ]

        # Format dataframe for display
        view_df = filtered_df[display_cols].copy()
        st.dataframe(
            view_df.style.format({
                "bank_amount": "${:,.2f}",
                "ledger_amount": "${:,.2f}",
                "variance": "${:,.2f}"
            }),
            use_container_width=True,
            height=380
        )

        # Item Detail Inspector
        st.markdown("#### 🔎 Exception Record Inspector")
        if not filtered_df.empty:
            selected_rec_id = st.selectbox(
                "Select a Reconciliation ID to inspect full transaction details:",
                options=filtered_df["reconciliation_id"].tolist()
            )
            item_row = filtered_df[filtered_df["reconciliation_id"] == selected_rec_id].iloc[0]

            detail_col1, detail_col2 = st.columns(2)
            with detail_col1:
                st.markdown("##### 🏦 Bank Statement Record")
                st.write(f"**Trx ID:** {item_row.get('bank_trx_id', 'N/A')}")
                st.write(f"**Date:** {item_row.get('bank_date', 'N/A')}")
                st.write(f"**Amount:** ${item_row.get('bank_amount', 0.0):,.2f}")
                st.write(f"**Description:** {item_row.get('bank_description', 'N/A')}")
            with detail_col2:
                st.markdown("##### 📖 General Ledger Record")
                st.write(f"**Trx ID:** {item_row.get('ledger_trx_id', 'N/A')}")
                st.write(f"**Date:** {item_row.get('ledger_date', 'N/A')}")
                st.write(f"**Amount:** ${item_row.get('ledger_amount', 0.0):,.2f}")
                st.write(f"**Description:** {item_row.get('ledger_description', 'N/A')}")

            st.info(f"**Root-Cause Diagnosis:** {item_row.get('root_cause', '')} | **Variance:** ${item_row.get('variance', 0.0):,.2f}")

    # -------------------------------------------------------------
    # TAB 3: ROOT-CAUSE DIAGNOSTICS & TRENDS
    # -------------------------------------------------------------
    with tab3:
        st.subheader("Root-Cause Diagnostic & Anomaly Breakdown")
        st.caption("Automated classification of timing differences, transposition typos, fee deductions, and missing entries.")

        col_rc1, col_rc2 = st.columns(2)

        with col_rc1:
            st.markdown("#### Primary Root Cause Categories")
            rc_counts = results_df["root_cause"].apply(lambda x: x.split("(")[0].strip()).value_counts().reset_index()
            rc_counts.columns = ["Root Cause Category", "Frequency"]

            pie_chart = alt.Chart(rc_counts).mark_arc(innerRadius=45).encode(
                theta=alt.Theta("Frequency:Q"),
                color=alt.Color("Root Cause Category:N", scale=alt.Scale(scheme="tableau10")),
                tooltip=["Root Cause Category", "Frequency"]
            ).properties(height=320)
            st.altair_chart(pie_chart, use_container_width=True)

        with col_rc2:
            st.markdown("#### Bank Clearing Transit Timing Delay")
            timing_items = results_df[results_df["status"] == STATUS_TIMING_MATCH]
            if not timing_items.empty and "date_diff_days" in timing_items.columns:
                timing_dist = timing_items["date_diff_days"].value_counts().reset_index()
                timing_dist.columns = ["Days to Clear", "Number of Payments"]

                bar_chart = alt.Chart(timing_dist).mark_bar(color="#3B82F6").encode(
                    x=alt.X("Days to Clear:O", title="Clearing Lag (Days)"),
                    y=alt.Y("Number of Payments:Q", title="Volume of Transactions"),
                    tooltip=["Days to Clear", "Number of Payments"]
                ).properties(height=320)
                st.altair_chart(bar_chart, use_container_width=True)
            else:
                st.info("No timing differences recorded.")

        st.markdown("---")
        st.markdown("#### ⚡ Control Anomaly Deep-Dives")
        col_an1, col_an2 = st.columns(2)
        with col_an1:
            st.markdown("##### 🔀 Transposition & Data Entry Typos (Divisible by 9)")
            transpo_df = results_df[results_df["root_cause"].str.contains("Transposition", na=False)]
            if not transpo_df.empty:
                st.dataframe(
                    transpo_df[["reconciliation_id", "reference_no", "bank_amount", "ledger_amount", "variance"]].style.format({
                        "bank_amount": "${:,.2f}",
                        "ledger_amount": "${:,.2f}",
                        "variance": "${:,.2f}"
                    }),
                    use_container_width=True
                )
            else:
                st.write("No transposition errors detected.")

        with col_an2:
            st.markdown("##### 💳 Unrecorded Bank Surcharges & Direct Debits")
            fee_df = results_df[results_df["root_cause"].str.contains("Fee|Direct debit|Unrecorded", na=False)]
            if not fee_df.empty:
                st.dataframe(
                    fee_df[["reconciliation_id", "bank_description", "bank_amount", "root_cause"]].head(8).style.format({
                        "bank_amount": "${:,.2f}"
                    }),
                    use_container_width=True
                )
            else:
                st.write("No unrecorded charges detected.")

    # -------------------------------------------------------------
    # TAB 4: SQL ANALYTICS & AUDIT TRAIL
    # -------------------------------------------------------------
    with tab4:
        st.subheader("SQL Analytics & Controls Audit Trail")
        st.caption("Interact directly with the reconciliation SQLite database using SQL queries and review immutable audit records.")

        tab4_a, tab4_b, tab4_c = st.tabs([
            "📋 Canned SQL Controller Reports",
            "💻 Live SQL Query Console",
            "🛡️ Immutable Audit Trail"
        ])

        with tab4_a:
            report_option = st.selectbox(
                "Choose Analytical SQL Report:",
                [
                    "Top 10 Largest Variance Breaks",
                    "Duplicate Postings in Ledger",
                    "Daily Variance Aggregation",
                    "Reconciliation Runs History"
                ]
            )

            if report_option == "Top 10 Largest Variance Breaks":
                sql_q = f"""
                SELECT reconciliation_id, status, reference_no, bank_amount, ledger_amount, variance, root_cause
                FROM reconciliation_items
                WHERE run_id = '{run_id}' AND requires_action = 1
                ORDER BY ABS(variance) DESC
                LIMIT 10;
                """
            elif report_option == "Duplicate Postings in Ledger":
                sql_q = f"""
                SELECT reconciliation_id, status, reference_no, ledger_trx_id, ledger_amount, ledger_description
                FROM reconciliation_items
                WHERE run_id = '{run_id}' AND status = 'DUPLICATE_LEDGER';
                """
            elif report_option == "Daily Variance Aggregation":
                sql_q = f"""
                SELECT COALESCE(bank_date, ledger_date) AS trx_date,
                       COUNT(*) AS total_items,
                       ROUND(SUM(variance), 2) AS daily_net_variance,
                       ROUND(SUM(ABS(variance)), 2) AS daily_gross_exposure
                FROM reconciliation_items
                WHERE run_id = '{run_id}'
                GROUP BY COALESCE(bank_date, ledger_date)
                ORDER BY trx_date;
                """
            else:
                sql_q = "SELECT * FROM reconciliation_runs ORDER BY timestamp DESC LIMIT 10;"

            st.code(sql_q, language="sql")
            report_res = db.execute_custom_query(sql_q)
            st.dataframe(report_res, use_container_width=True)

        with tab4_b:
            st.markdown("#### Live SQLite Query Console")
            st.caption("Tables available: `reconciliation_runs`, `reconciliation_items`, `audit_logs`")
            default_query = f"SELECT status, COUNT(*) as count, ROUND(SUM(variance), 2) as total_variance FROM reconciliation_items WHERE run_id = '{run_id}' GROUP BY status;"
            user_sql = st.text_area("Write SQL Query (SELECT only):", value=default_query, height=100)

            if st.button("Execute Query"):
                try:
                    query_df = db.execute_custom_query(user_sql)
                    st.success(f"Returned {len(query_df)} rows")
                    st.dataframe(query_df, use_container_width=True)
                except Exception as e:
                    st.error(f"SQL Error: {str(e)}")

        with tab4_c:
            st.markdown("#### Chronological Audit Trail Log")
            st.caption("Immutable system log of user executions, pipeline runs, and integrity validations.")
            audit_records = db.get_audit_trail(limit=50)
            st.dataframe(audit_records, use_container_width=True)

    # -------------------------------------------------------------
    # TAB 5: EXPORT CENTER
    # -------------------------------------------------------------
    with tab5:
        st.subheader("Financial Reporting & Export Center")
        st.caption("Generate signed reconciliation certificates and export packages for internal audit and external review.")

        exp_col1, exp_col2 = st.columns(2)

        with exp_col1:
            st.markdown("#### 📑 Multi-Tab Formatted Excel Package")
            st.write("Generates an executive-ready workbook containing:")
            st.markdown("""
            - **Executive Summary:** Sign-off attestation, balance bridge, KPI metrics.
            - **Exceptions & Discrepancies:** Color-coded schedules with root-cause tags.
            - **Matched Records:** Clean verified transaction ledger.
            - **Audit Trail Log:** Immutable execution history.
            """)

            audit_df = db.get_audit_trail(run_id=run_id)
            excel_bytes = create_reconciliation_excel_bytes(run_id, kpis, results_df, audit_df)

            st.download_button(
                label="📥 Download Excel Reconciliation Package (.xlsx)",
                data=excel_bytes,
                file_name=f"Financial_Reconciliation_Package_{run_id}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True
            )

        with exp_col2:
            st.markdown("#### 📄 Raw Reconciled Data Exports")
            st.write("Export CSV data for downstream ERP or BI pipelines:")

            csv_all = results_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download All Reconciled Records (CSV)",
                data=csv_all,
                file_name=f"all_reconciled_items_{run_id}.csv",
                mime="text/csv",
                use_container_width=True
            )

            exceptions_csv = results_df[results_df["requires_action"] == True].to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Exceptions & Discrepancies Only (CSV)",
                data=exceptions_csv,
                file_name=f"exceptions_only_{run_id}.csv",
                mime="text/csv",
                use_container_width=True
            )
