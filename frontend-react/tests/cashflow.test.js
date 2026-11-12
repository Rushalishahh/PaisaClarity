import test from 'node:test'
import assert from 'node:assert/strict'

function computeCashFlowMetrics(income, expenses) {
  const inc = Number(income) || 0
  const exp = Number(expenses) || 0
  const net = inc - exp
  const savingsRate = inc > 0 ? Math.round(((net / inc) * 100) * 100) / 100 : 0
  return { net, savingsRate }
}

test('computeCashFlowMetrics calculates positive cash flow and savings rate', () => {
  const { net, savingsRate } = computeCashFlowMetrics(100000, 40000)
  assert.equal(net, 60000)
  assert.equal(savingsRate, 60)
})

test('computeCashFlowMetrics handles zero income gracefully', () => {
  const { net, savingsRate } = computeCashFlowMetrics(0, 5000)
  assert.equal(net, -5000)
  assert.equal(savingsRate, 0)
})

test('computeCashFlowMetrics handles negative cash flow', () => {
  const { net, savingsRate } = computeCashFlowMetrics(50000, 60000)
  assert.equal(net, -10000)
  assert.equal(savingsRate, -20)
})

