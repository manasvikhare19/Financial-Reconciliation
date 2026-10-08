# PRD: Financial Reconciliation & Controls Dashboard

| | |
|---|---|
| **Author** | Manasvi Khare |
| **Status** | v1.0 shipped; v1.1 proposed |
| **Type** | Retrospective PRD, written after the build to document scope decisions, acceptance criteria and success metrics |
| **Baseline data** | `data/sample_*.csv` (480 bank records, 495 ledger records, synthetic with seeded anomalies) |

---

## 1. Problem

Finance teams reconcile bank statements against the general ledger every period. Done by hand in spreadsheets, it is slow, error-prone, and hard to defend in an audit. Three pain points:

1. **Finding breaks:** matching by eye or VLOOKUP misses duplicates, timing lags and small amount differences.
2. **Explaining breaks:** a mismatch is only useful if someone knows *why* it happened (typo, bank fee, deposit in transit), and that diagnosis is usually done from memory.
3. **Proving the work:** auditors need to see who ran what, on which files, with what result.

## 2. Users

| Persona | Job to be done | What they need from this product |
|---|---|---|
| **Accounts Payable/Receivable Analyst** (primary) | Close the month's reconciliation quickly | Fast matching, clear list of exceptions, a reason for each |
| **Financial Controller** | Sign off that cash is correctly stated | Balance bridge, exception exposure, attestation |
| **Internal / External Auditor** | Verify controls operated | Immutable run history, reproducible outputs, Excel package |

## 3. Goals and non-goals

**Goals**
- Reduce the analyst's work to *reviewing exceptions* rather than *finding* them.
- Attach a probable root cause to every exception.
- Produce an audit-ready record of every run.

**Non-goals (v1)**
- Posting correcting journal entries back to an ERP.
- Real-time or streaming bank feeds.
- Multi-currency conversion (only rounding/FX micro-variances are flagged).
- Multi-user authentication and role-based access.

## 4. User stories and prioritization (MoSCoW)

| ID | Priority | User story | Rationale for priority |
|---|---|---|---|
| US-1 | **Must** | As an analyst, I upload bank and ledger files (CSV/XLSX) so I don't re-key data. | Nothing works without ingestion |
| US-2 | **Must** | As an analyst, I want bad input rejected before matching (missing columns, null dates) so I don't reconcile garbage. | A wrong reconciliation is worse than none |
| US-3 | **Must** | As an analyst, I want transactions auto-matched on reference, amount and date. | Core value |
| US-4 | **Must** | As an analyst, I want unmatched and duplicate items classified (missing in ledger, missing in bank, duplicate, amount mismatch). | Defines what needs action |
| US-5 | **Must** | As an auditor, I want every run logged with inputs, timestamp and results, append-only. | Required for the product to be usable in a controlled environment |
| US-6 | **Should** | As an analyst, I want timing differences (1-5 days) matched automatically so clearing lag is not treated as an error. | Cuts false exceptions; needs a tolerance setting |
| US-7 | **Should** | As an analyst, I want each exception tagged with a probable root cause. | Largest time saver after matching |
| US-8 | **Should** | As a controller, I want KPIs (match rate, discrepancy rate, net variance, gross exposure) and a balance bridge. | Sign-off decision support |
| US-9 | **Should** | As an analyst, I want to filter, search and inspect exceptions side by side. | Speeds up review |
| US-10 | **Should** | As a controller, I want an Excel reconciliation package for sign-off. | Finance teams work in Excel |
| US-11 | **Could** | As an analyst, I want to run read-only SQL against run history for ad-hoc questions. | Power-user feature; low effort once SQLite exists |
| US-12 | **Won't (v1)** | Auto-post correcting entries to the ERP. | Needs approvals workflow and ERP integration |

## 5. Workflow

```
Upload files -> Validate (schema, nulls, balances) -> Match in ordered passes
   Pass 0 flag duplicates within each file (held out of matching)
   Pass 1 exact: reference + amount + date
   Pass 2 timing: reference + amount, date within tolerance window
   Pass 3 amount mismatch: reference matches, amount differs
   Pass 4-5 duplicates in bank / duplicates in ledger
   Pass 6 missing in ledger (bank-only)
   Pass 7 missing in bank (ledger-only)
-> Tag root cause -> Persist run + audit log -> Dashboard review -> Excel export
```

Design decision: matching runs in ordered passes, strictest rule first, so a record is matched by the most trustworthy rule available, and duplicates are held out before matching to avoid wrongly pairing them.

## 6. Acceptance criteria

Each criterion is written as Given/When/Then and mapped to the automated test that checks it.

| Story | Acceptance criterion | Test |
|---|---|---|
| US-2 | **Given** a file missing a required column, **when** validation runs, **then** it fails and names the missing column. | `test_validate_dataset_missing_columns` |
| US-2 | **Given** rows with null dates, **when** validation runs, **then** they are flagged. | `test_validate_dataset_null_dates` |
| US-1 | **Given** amounts written as `($1,200.00)` or `100.00 CR`, **when** loaded, **then** they parse to the correct signed number. | `test_clean_amount_variations` |
| US-1 | **Given** differently named columns (aliases), **when** loaded, **then** they map to the standard schema. | `test_map_columns_aliases` |
| US-3 | **Given** identical reference, amount and date, **when** reconciled, **then** status is `MATCHED_EXACT`. | `test_exact_match` |
| US-6 | **Given** identical reference and amount with clearing 1-5 days apart, **when** reconciled, **then** status is `MATCHED_TIMING_DIFF`. | `test_timing_difference_match` |
| US-4 | **Given** a matching reference with different amounts, **when** reconciled, **then** status is `AMOUNT_MISMATCH` with the variance recorded. | `test_amount_mismatch` |
| US-4 | **Given** the same reference and amount twice in one file, **when** reconciled, **then** both are flagged duplicate, not matched. | `test_intra_dataset_duplicates` |
| US-4 | **Given** a record present on only one side, **when** reconciled, **then** it is `MISSING_IN_LEDGER` or `MISSING_IN_BANK`. | `test_missing_records` |
| US-7 | **Given** a variance divisible by 9, **when** classified, **then** root cause is transposition/typo. | `test_is_transposition_error`, `test_classify_root_cause_transposition` |
| US-7 | **Given** a fee-pattern variance or fee keyword, **when** classified, **then** root cause is bank fee. | `test_classify_root_cause_fee` |
| US-7 | **Given** a timing or duplicate exception, **when** classified, **then** the matching root cause is assigned. | `test_classify_root_cause_timing`, `test_classify_root_cause_duplicate` |
| US-5 | **Given** a completed run, **when** saved, **then** it can be retrieved and an audit log entry exists. | `test_save_and_retrieve_run`, `test_audit_log_insertion` |
| US-11 | **Given** the SQL console, **when** a non-SELECT statement is submitted, **then** it is rejected. | `test_execute_custom_query_readonly` |
| US-10 | **Given** a completed run, **when** exported, **then** the workbook contains the Summary, Exceptions, Matches and Audit tabs. | `test_excel_generation_tabs_and_structure` |

**Not yet covered by a test:** US-8 (KPI math), US-9 (dashboard filters). Listed in the roadmap.

## 7. Success metrics

### Product KPIs (computed by the engine on every run)

| Metric | Definition | v1 baseline (sample data) |
|---|---|---|
| **Match rate** | matched items / total reconciled items | **75.93%** (410 of 540) |
| **Discrepancy rate** | exception items / total reconciled items | **24.07%** (130 of 540) |
| **Net reconciliation variance** | ledger total minus bank total | $538,293.65 |
| **Gross exception exposure** | sum of absolute variance across exceptions | $1,197,027.05 |

### Feature success metrics

| Feature | Metric | Baseline | Target for v1.1 |
|---|---|---|---|
| Root-cause tagging (US-7) | % of exceptions with a specific root cause (not "Unresolved") | 130 of 130 on the sample set* | Hold >= 90% on real, unseeded data |
| Timing-tolerance matching (US-6) | Timing matches as % of all matches | 60 of 410 (14.6%) | Track per run; investigate if it trends up |
| Exception workbench (US-9) | Time for a reviewer to clear one exception | Not measured | Establish baseline in user testing |
| Audit trail (US-5) | Runs with complete input/output record | 100% by design (every run writes a log) | 100% |

\* The sample data is synthetic and the anomalies were seeded to match the classification rules, so this figure shows the rules work as designed, not how they perform on real ledgers. The v1.1 target is the real test.

## 8. Roadmap (proposed)

| Horizon | Item | Why |
|---|---|---|
| **Now (v1.0, shipped)** | Ingestion, validation, multi-pass engine, root cause, dashboard, audit log, Excel package, 19 tests | Core loop complete |
| **Next (v1.1)** | Tests for KPI math and dashboard filters; run on a real anonymized dataset; add a "resolved / waived / escalated" status on each exception | Close test gaps and prove the root-cause rules beyond synthetic data |
| **Next (v1.1)** | Fuzzy reference matching (e.g., trailing characters, case) | Many real-world breaks are formatting differences |
| **Later (v2)** | Export of proposed correcting journal entries for review | First step toward the Won't item without ERP integration |
| **Later (v2)** | Multi-user roles (analyst / reviewer / auditor) | Needed for real segregation of duties |

Prioritization for v1.1 using RICE (estimates, to be validated with users):

| Item | Reach | Impact | Confidence | Effort (weeks) | Score |
|---|---|---|---|---|---|
| KPI and filter tests | 1 (all runs) | 1 | 0.9 | 0.5 | 1.8 |
| Resolve / waive / escalate status | 0.8 | 2 | 0.7 | 2 | 0.56 |
| Fuzzy reference matching | 0.6 | 2 | 0.5 | 2 | 0.30 |

Scale: Reach 0-1 (share of runs affected), Impact 0.25-3, Confidence 0-1, Effort in person-weeks.

## 9. Experiments to run once there are real users

Not yet run. These are the planned tests, so the metrics above can be moved.

| Hypothesis | Test | Success signal |
|---|---|---|
| A wider timing window (5 -> 7 days) reduces false exceptions without hiding real errors | Run both settings on the same dataset; have a reviewer audit a sample of the extra matches | Fewer exceptions and no wrongly accepted matches in the sample |
| Showing the root cause next to each exception speeds up review | Reviewers clear a fixed set of exceptions with and without the root-cause column | Lower time per exception |

## 10. Risks and open questions

- **Synthetic data.** Rules (divisible-by-9, fee patterns) are standard accounting heuristics but unproven on real ledgers.
- **False matches.** A wide timing window could pair unrelated items that share a reference. Mitigation: tolerance is a config value; matches are always reviewable.
- **Divisible-by-9 can produce false positives** for large variances that happen to be divisible by 9. Open question: add a magnitude or digit-pattern check.
- **Who is accountable for sign-off in the tool?** Attestation is a preview, not an authenticated approval.
