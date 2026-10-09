/*
Shared currency formatting for every displayed rupee amount
(Dashboard, History, Investments, and Recharts tooltips/axes).

  formatINR(1234567)    -> "₹12,35,567"   (Indian digit grouping)
  formatINRCompact(1.2e7) -> "₹1.2Cr"     (axis ticks: k = thousand, L = lakh, Cr = crore)

The Intl.NumberFormat instances are created once at module level because
Recharts calls tickFormatter for every tick on every render.
*/

// maximumFractionDigits: 0 — analysis amounts are whole rupees.
const inrFull = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
})

function formatINR(amount) {
  if (amount === null || amount === undefined) return "—"
  return inrFull.format(Number(amount))
}

/* Compact Indian numbering for chart axes: 1,50,000 -> "₹1.5L",
   2,30,00,000 -> "₹2.3Cr". Below one lakh, falls back to k / plain rupees. */
function formatINRCompact(amount) {
  if (amount === null || amount === undefined) return "—"
  const n = Number(amount)
  const sign = n < 0 ? "−" : ""
  const abs = Math.abs(n)
  // toFixed(2) then Number() strips trailing zeros: 1.50 -> 1.5
  const trim = (x) => Number(x.toFixed(2)).toString()
  if (abs >= 1e7) return `${sign}₹${trim(abs / 1e7)}Cr`
  if (abs >= 1e5) return `${sign}₹${trim(abs / 1e5)}L`
  if (abs >= 1000) return `${sign}₹${trim(abs / 1000)}k`
  return `${sign}₹${Math.round(abs)}`
}

export { formatINR, formatINRCompact }
