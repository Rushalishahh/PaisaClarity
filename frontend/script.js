const fileInput = document.getElementById("fileInput");
const uploadBtn = document.getElementById("uploadBtn");
const resultsDiv = document.getElementById("results");

const API_URL = "http://127.0.0.1:8000/upload-statement";

uploadBtn.addEventListener("click", async () => {
    const file = fileInput.files[0];

    if (!file) {
        alert("Please choose a CSV file first.");
        return;
    }

    resultsDiv.innerHTML = "<p>Analyzing your statement...</p>";

    try {
        const formData = new FormData();
        formData.append("file", file);

        const response = await fetch(API_URL, {
            method: "POST",
            body: formData,
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || "Something went wrong");
        }

        const data = await response.json();
        renderDashboard(data);

    } catch (error) {
        resultsDiv.innerHTML = `<p style="color: red;">Error: ${error.message}</p>`;
    }
});


function renderDashboard(data) {
    // Clear previous results
    resultsDiv.innerHTML = "";

    resultsDiv.appendChild(renderSavingsSummary(data.savings_summary));
    resultsDiv.appendChild(renderCategoryTotals(data.category_totals));
    resultsDiv.appendChild(renderForecast(data.forecast));
    resultsDiv.appendChild(renderAnomalies(data.anomalies));
    resultsDiv.appendChild(renderSuggestions(data.suggestions));
}


function renderSavingsSummary(summary) {
    const section = document.createElement("div");
    section.className = "card";

    section.innerHTML = `
        <h2>Savings Summary</h2>
        <div class="summary-grid">
            <div class="stat">
                <span class="stat-label">Total Income</span>
                <span class="stat-value">₹${summary.total_income.toLocaleString()}</span>
            </div>
            <div class="stat">
                <span class="stat-label">Total Spend</span>
                <span class="stat-value">₹${summary.total_spend.toLocaleString()}</span>
            </div>
            <div class="stat">
                <span class="stat-label">Total Saved</span>
                <span class="stat-value">₹${summary.total_saved.toLocaleString()}</span>
            </div>
            <div class="stat">
                <span class="stat-label">Savings Rate</span>
                <span class="stat-value">${summary.savings_rate_pct}%</span>
            </div>
        </div>
    `;

    return section;
}


function renderCategoryTotals(totals) {
    const section = document.createElement("div");
    section.className = "card";

    // Find the highest amount so we can scale bar widths proportionally
    const maxAmount = Math.max(...Object.values(totals));

    let rowsHtml = "";
    for (const [category, amount] of Object.entries(totals)) {
        const widthPct = (amount / maxAmount) * 100;
        rowsHtml += `
            <div class="category-row">
                <span class="category-name">${category}</span>
                <div class="bar-container">
                    <div class="bar" style="width: ${widthPct}%"></div>
                </div>
                <span class="category-amount">₹${amount.toLocaleString()}</span>
            </div>
        `;
    }

    section.innerHTML = `<h2>Spending by Category</h2>${rowsHtml}`;
    return section;
}


function renderForecast(forecast) {
    const section = document.createElement("div");
    section.className = "card";

    if (forecast.error) {
        section.innerHTML = `<h2>Next Month Forecast</h2><p>${forecast.error}</p>`;
        return section;
    }

    const trendText = forecast.trend_slope_per_month > 0
        ? `Your spending is trending up by ₹${forecast.trend_slope_per_month.toLocaleString()} per month.`
        : `Your spending is trending down by ₹${Math.abs(forecast.trend_slope_per_month).toLocaleString()} per month.`;

    const confidenceNote = forecast.low_confidence
        ? `<p class="low-confidence-note">⚠ Based on only ${forecast.based_on_months} months of data — forecast may not be reliable yet. More history will improve accuracy.</p>`
        : "";

    section.innerHTML = `
        <h2>Next Month Forecast</h2>
        <p class="forecast-amount">₹${forecast.predicted_next_month_spend.toLocaleString()}</p>
        <p>${trendText}</p>
        ${confidenceNote}
    `;
    return section;
}



function renderAnomalies(anomalies) {
    const section = document.createElement("div");
    section.className = "card";

    if (anomalies.length === 0) {
        section.innerHTML = `<h2>Spending Alerts</h2><p>No unusual spending detected.</p>`;
        return section;
    }

    let itemsHtml = "";
    for (const a of anomalies) {
        itemsHtml += `
            <div class="alert-item">
                <strong>${a.category}</strong> in ${a.month}: ₹${a.amount.toLocaleString()}
                (${a.pct_increase}% above average of ₹${a.average.toLocaleString()})
            </div>
        `;
    }

    section.innerHTML = `<h2>Spending Alerts</h2>${itemsHtml}`;
    return section;
}


function renderSuggestions(suggestions) {
    const section = document.createElement("div");
    section.className = "card";

    let itemsHtml = "";
    for (const s of suggestions) {
        itemsHtml += `<li>${s}</li>`;
    }

    section.innerHTML = `<h2>Suggestions</h2><ul class="suggestions-list">${itemsHtml}</ul>`;
    return section;
}