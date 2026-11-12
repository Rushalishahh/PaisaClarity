# Spending Forecasting Evaluation & Uncertainty Modeling (Phase 10)

This document presents the chronological backtesting benchmark, model comparison, uncertainty estimation, and Copilot integration for PaisaClarity spending forecasts.

---

## 1. Executive Summary

A common failure mode of naive monthly spending forecasts is severe distortion caused by one-off outlier shocks (e.g. medical emergencies, electronics purchases) and failure to account for fixed upcoming commitments. 

In Phase 10, PaisaClarity evaluated five forecasting methods across a 24-month chronological synthetic timeline and implemented an outlier-resistant **Hybrid Run-Rate Engine**:
- **Month-to-Date (MTD) Base**: Ground-truth cumulative expenses incurred so far.
- **Confirmed Recurring Commitments**: Upcoming bills, EMIs, and subscriptions due before month end.
- **IQR-Cleaned Discretionary Pace**: Interquartile range outlier filtering on daily spend history to project remaining days.
- **95% Confidence Uncertainty Interval**: $\pm 1.96 \times \sigma_{\text{daily}} \times \sqrt{\text{days\_remaining}}$.
- **Explainability**: Clear breakdowns delivered directly to users and the AI Copilot.

---

## 2. Chronological Backtesting Results

The benchmark was executed via `backend/eval_forecasting.py` over 24 synthetic months containing base discretionary spend, recurring bills, seasonal spikes (Diwali / year-end travel), and random outlier shocks. Forecasting checkpoints were taken on **Day 10, Day 15, and Day 20** of each month (54 evaluation points).

### Benchmark Comparison Table

| Model Architecture | MAE (₹) | WAPE (%) | Forecast Bias (₹) | Description |
| :--- | :---: | :---: | :---: | :--- |
| **Linear Regression** | ₹21,787.69 | 30.16% | +₹1,893.89 | OLS trend fit on chronological completed monthly totals. |
| **Rolling 3-Month Average** | ₹20,487.07 | 28.36% | -₹3,542.68 | Moving average of the 3 most recent completed months. |
| **Rolling 6-Month Average** | ₹18,492.91 | 25.60% | -₹5,150.45 | Moving average of the 6 most recent completed months. |
| **Seasonal Naive (Lag-12)** | ₹16,908.88 | 23.41% | -₹4,100.09 | Historical total from the same calendar month of previous year. |
| **Hybrid Run-Rate (Outlier-Filtered)** | **₹10,693.01** | **14.80%** | **-₹7,293.12** | **MTD + Recurring Commitments + IQR-filtered discretionary pace.** |

### Key Takeaways:
1. **50.9% Error Reduction**: The Hybrid Run-Rate model reduced Mean Absolute Error from ₹21,787.69 (Linear Regression) down to ₹10,693.01.
2. **WAPE under 15%**: Weighted Absolute Percentage Error dropped to 14.80%, beating the best classical rolling model (23.41%).

---

## 3. Edge-Case Evaluations

### 3.1 Outlier Shock Resilience (Day 12 Single-Day ₹80,000 Spike)
- **Scenario**: Day 1-11 discretionary spend ~₹800/day. On Day 12, a one-time ₹80,000 laptop purchase occurs.
- **Naive Run-Rate Forecast**: ₹229,916.67 (extrapolates the ₹80,000 across all remaining days).
- **Hybrid Forecast (IQR-Filtered)**: ₹109,545.45 (identifies the ₹80,000 as a one-time spike, applies ₹900/day pace for remaining 19 days).
- **Uncertainty Range**: ₹108,375.27 to ₹110,715.64.
- **Distortion Prevented**: **₹120,371.21**.

### 3.2 Sparse History (New User with 1 Completed Month)
- **Scenario**: User has only 1 historical month and 5 days elapsed in the current month.
- **Engine Behavior**:
  - Automatically assigns confidence level: `"low"`.
  - Calculates wide uncertainty interval: `₹39,535.33 - ₹40,864.67`.
  - Generates transparent explanation: *"Forecast for February based on ₹4,500.00 spent MTD (5/28 days), ₹15,000.00 in confirmed upcoming recurring commitments, and an estimated daily discretionary pace of ₹900.00/day for the remaining 23 days."*

---

## 4. AI Copilot Integration

The `get_spending_forecast` tool and `MockLLMProvider` synthesize predictions in structured, explainable natural language:

> *"Forecast for March 2026: Projected month-end total is ₹90,725.00 (expected range: ₹88,450.00 - ₹93,000.00). This accounts for ₹59,200.00 spent MTD, ₹10,000.00 in confirmed recurring commitments, and ₹21,525.00 in projected discretionary burn. Projection derived via Hybrid Run-Rate with Outlier-Resistant Discretionary Burn + Confirmed Recurring Bills."*
