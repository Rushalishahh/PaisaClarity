# PaisaClarity Frontend & User Experience Audit (Phase 11)

**Date**: 2026-11-12  
**Baseline**: Phase 10 (`9b04d98`)  
**Scope**: All pages, routes, navigation, forms, modals, tables, charts, exports, and accessibility flows.

---

## 1. Executive Summary

This audit evaluates the PaisaClarity React frontend (React 19 + Tailwind v4 + Vite) against real-world personal finance usability, data transparency, and accessibility standards. 

While the application features strong cryptographic security, strict backend session scoping, and robust domain models, the user interface exhibits opportunities for polish in five key areas:
1. **Missing Authoritative Financial Reporting**: Users currently lack a centralized Reports view with configurable date ranges, monthly income vs. expense summaries, and downloadable CSV/PDF export artifacts.
2. **Categorization Correction Transparency**: Manual category corrections currently create broad persistent merchant rules silently. Users must be given an explicit choice: *"Apply only to this transaction"* vs. *"Apply to future imports from this merchant"*.
3. **Financial Transparency & Labeling**: Actual spending, projected run-rates, confirmed bills, auto-detected subscriptions, verified accounts, and placeholder/unreconciled accounts need unambiguous visual distinction.
4. **Layout & Visual Consistency**: Container widths vary between pages (`max-w-5xl`, `max-w-6xl`, and `max-w-7xl`), causing horizontal layout shifting during navigation. Empty states, modal focus management, and loading skeletons need standardization.
5. **Accessibility & Form Semantics**: Missing `autocomplete` attributes, missing `aria-expanded` and `aria-haspopup` states on dropdowns/modals, and keyboard focus trap enhancements.

---

## 2. Prioritized Findings by Severity

### Critical & High Priority Findings

| ID | Component / Page | Issue Description | Impact | Remediation Plan |
|:---|:---|:---|:---|:---|
| **AUD-01** | **Reports (New)** | No centralized Financial Reports page exists. | Users cannot view comprehensive historical summaries across accounts, budgets, goals, and categories, nor can they export data. | Implement `/reports` route and backend endpoints (`/reports/summary`, `/reports/export/csv`, `/reports/export/pdf`) with date filtering and formula-injection defenses. |
| **AUD-02** | **Transactions** | Category correction silently creates persistent rules for all future imports. | Users correcting a one-off anomaly (e.g. buying a gift at a grocery store) unintentionally reclassify all future grocery purchases. | Update `CategoryCorrection` API schema and modal to include an explicit checkbox: *"Apply only to this transaction"* vs. *"Apply to future imports from this merchant"*. |
| **AUD-03** | **Forecast Presentation** | Forecasted end-of-month spend can be conflated with ground-truth actual spend. | Risk of user confusion between money already spent vs. projected run-rate. | Explicitly separate MTD Actual Spend, Confirmed Upcoming Dues, and Discretionary Forecast Pace with uncertainty bounds in UI cards. |
| **AUD-04** | **Exports** | No CSV/PDF financial export capability. | Users cannot export statements or summaries for tax filing, personal audits, or external spreadsheets. | Add sanitized CSV export (with formula injection escaping) and formatted PDF export using ReportLab. |
| **AUD-05** | **Navigation** | `AppShell` lacks navigation link to Reports. | Inability to access reports from persistent desktop sidebar or mobile drawer. | Add `/reports` to `NAV_ITEMS` in `AppShell.jsx` with an appropriate document/analytics icon. |

---

### Medium Priority Findings (Visual & UX Polish)

| ID | Component / Page | Issue Description | Remediation Plan |
|:---|:---|:---|:---|
| **AUD-06** | **AppShell & Layout** | Inconsistent page container widths (`max-w-5xl` in Dashboard, `max-w-6xl` in Budgets/Accounts, `max-w-7xl` in Transactions). | Standardize on responsive `max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8` across all authenticated views. |
| **AUD-07** | **Transactions** | No visual indicator showing whether a category was manual, rule-based, or default. | Display subtle tag/indicator (`User Override`, `Rule Matched`, `Default`) in the category cell. |
| **AUD-08** | **Recurring Payments** | Subscriptions pending review look identical to confirmed bills. | Distinct badge colors: Emerald for `Confirmed`, Amber for `Detected (Pending Review)`, Gray for `Paused`. |
| **AUD-09** | **Accounts** | Unreconciled accounts need stronger distinction from verified accounts. | Prominent informational badge and tooltip stating unreconciled balances are excluded from verified net worth. |
| **AUD-10** | **AI Copilot** | Forecast explanations from AI do not visually highlight uncertainty bounds. | Format uncertainty ranges as highlighted chips in the chat response. |
| **AUD-11** | **Modals & Dialogs** | Modals lack keyboard `Escape` key listeners and focus trapping. | Add global `keydown` event listener for `Escape` to close modals gracefully. |

---

### Low Priority / Accessibility Polish

| ID | Component / Page | Issue Description | Remediation Plan |
|:---|:---|:---|:---|
| **AUD-12** | **Auth Forms** | Login and Signup forms lack `autocomplete` attributes. | Add `autocomplete="username"`, `autocomplete="current-password"`, and `autocomplete="new-password"`. |
| **AUD-13** | **Tables** | Transaction table headers lack `aria-label` or sorting cues. | Add ARIA attributes for accessible screen reader navigation. |
| **AUD-14** | **Loading Skeletons** | Inconsistent loading state appearance across pages. | Use consistent `SkeletonCard` and pulsing placeholder rows. |

---

## 3. Implementation Roadmap

1. **Backend Reporting Engine (`backend/reporting_routes.py`)**:
   - Comprehensive summary calculations (`GET /reports/summary`).
   - Hardened CSV export (`GET /reports/export/csv`) with formula injection prevention (`'`, `=`, `+`, `-`, `@`, `\t`, `\r`).
   - Professional PDF export (`GET /reports/export/pdf`) utilizing ReportLab with Indian Rupee formatting.
2. **Categorization Correction UX (`backend/transaction_routes.py` & `Transactions.jsx`)**:
   - Add `apply_to_future: bool = False` to `CategoryCorrection`.
   - Update frontend category correction modal to offer explicit choice.
3. **Frontend Reports Page (`frontend-react/src/pages/Reports.jsx`)**:
   - Date range selector (Last 30 Days, This Month, Last Month, Last 90 Days, This Year, Custom Range).
   - Financial KPI cards, Category Breakdown chart, Cash Flow summary, Budget utilization, Goal progress.
   - One-click CSV and PDF download buttons.
4. **AppShell & Navigation Update**:
   - Add `/reports` to `AppShell.jsx` desktop sidebar and mobile drawer.
   - Standardize page container widths across all views.
5. **Data Transparency Badges**:
   - Categorization origin badges on transactions.
   - Verified vs Unreconciled badges on accounts.
   - Confirmed vs Detected badges on subscriptions.
   - Uncertainty bounds and methodology notes on forecasts.
6. **Automated Testing & End-to-End Verification**:
   - Unit tests for reports, exports, CSV sanitization, and category preferences.
   - Frontend unit tests and build verification.
   - End-to-end automated workflow verification.
