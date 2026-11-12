# PaisaClarity 3–5 Minute Product Walkthrough & Demo Script

**Target Audience**: Technical Recruiters, Engineering Leaders, Portfolio Reviewers  
**Data Policy**: 100% Synthetic Demo Data Only (Zero real financial data)  
**Total Runtime**: ~3.5 Minutes  

---

## Demo Overview & Persona
- **Demo User**: Jane Doe (`jane.doe@example.com`)
- **Starting State**: Clean account with one primary savings account (`HDFC Salary Account` with ₹50,000 opening balance).
- **Goal**: Showcase statement parsing, verified account balances, budget alerts, financial reporting, and the AI Copilot.

---

## Detailed Step-by-Step Script

### Scene 1: Introduction & Landing Page (0:00 – 0:30)
- **Visual**: Navigate to `http://localhost:5173` (or production landing page).
- **Spoken Narration**:
  > *"Welcome to PaisaClarity — a privacy-first personal finance assistant built with FastAPI, React 19, and PostgreSQL. PaisaClarity solves a real problem: personal finance apps often leak privacy by storing raw banking statements or giving opaque financial advice. PaisaClarity processes statements in-memory, normalizes transactions into double-entry ledgers with exact Decimal arithmetic, and pairs it with an AI Copilot that uses deterministic tool calling rather than mathematical hallucinations."*
- **Action**: Click **"Sign In"** and log in with demo credentials.

---

### Scene 2: Verified Accounts & In-Memory Statement Ingestion (0:30 – 1:15)
- **Visual**: Dashboard loads showing initial financial summary cards.
- **Action**: Navigate to `/accounts`. Show verified vs unreconciled balances.
- **Spoken Narration**:
  > *"Here in the Financial Accounts view, you see our verified accounts. PaisaClarity separates verified bank accounts from unassigned imported accounts so unreconciled data never silently distorts your true net worth. Let's upload a bank statement."*
- **Action**: Navigate to `/statements`, select synthetic statement file `sample_hdfc_statement.csv`, select `HDFC Salary Account`, and click **"Upload Statement"**.
- **Visual**: Statement parsed in-memory in under 300ms. Ingest summary appears showing categorized rows.
- **Spoken Narration**:
  > *"Notice how fast that parsed. The statement was processed entirely in server memory without writing raw bank documents to host disk. Transactions are normalized into debit, credit, and transfer classifications, and automatically assigned to categories with Indian banking rules."*

---

### Scene 3: Transaction Explorer & Inter-Account Transfers (1:15 – 1:50)
- **Visual**: Navigate to `/transactions`.
- **Action**: Filter by category `Groceries` or search for `Swiggy`.
- **Spoken Narration**:
  > *"On the Transactions page, all records use standard two-decimal precision. Notice this transfer between checking and savings: PaisaClarity explicitly tracks inter-account transfers and excludes them from spending totals, eliminating the double-counting bug common in naive trackers."*

---

### Scene 4: Budgets, Recurring Payments & Smart Alerts (1:50 – 2:30)
- **Visual**: Navigate to `/budgets` and then `/alerts`.
- **Action**: Point out the progress bar for `Dining & Food` showing 85% utilization (triggering an alert badge).
- **Spoken Narration**:
  > *"In our Budget engine, category allocations and total monthly limits are monitored continuously. When spending crosses our 80% warning threshold, a financial alert is generated immediately. The Recurring Payments module also auto-detects subscription cadences — like Netflix and Spotify — forecasting upcoming bills before they hit."*

---

### Scene 5: Executive Financial Reports & Export (2:30 – 3:00)
- **Visual**: Navigate to `/reports`.
- **Action**: Switch preset to "This Month", review the cash flow distribution chart, then click **"Export CSV"** and **"Download PDF Report"**.
- **Spoken Narration**:
  > *"The Reports view delivers executive-grade cash flow analytics. We can export transaction ledgers to CSV — with built-in formula injection defenses — or generate a polished PDF report summarizing income, expenditure, and savings rate."*

---

### Scene 6: Secure AI Financial Copilot (3:00 – 3:45)
- **Visual**: Navigate to `/copilot`.
- **Action**: Click starter prompt pill: *"How much did I spend and earn recently? What is my savings rate?"*
- **Spoken Narration**:
  > *"Finally, here is the PaisaClarity AI Copilot. Unlike generic chatbots that guess numbers, PaisaClarity uses strict deterministic tool calling. When I ask about my spending and savings rate, the LLM calls our verified backend tools with server-enforced user boundaries. The model never sees other users' data, cannot execute arbitrary code or SQL, and bases every figure on exact database aggregates."*
- **Visual**: Copilot displays a structured markdown answer citing exact totals and savings percentage.
- **Wrap-up**:
  > *"That is PaisaClarity: production-hardened, mathematically exact, and private by design. Full technical documentation, PostgreSQL test results, and browser test suites are available in our GitHub repository."*
