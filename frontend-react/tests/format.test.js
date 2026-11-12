import test from 'node:test'
import assert from 'node:assert/strict'
import { formatINR, formatINRCompact } from '../src/utils/format.js'

test('formatINR formats currency with Indian rupee grouping', () => {
  assert.equal(formatINR(0), '₹0')
  assert.equal(formatINR(1000), '₹1,000')
  assert.equal(formatINR(100000), '₹1,00,000')
  assert.equal(formatINR(1234567), '₹12,34,567')
  assert.equal(formatINR(null), '—')
  assert.equal(formatINR(undefined), '—')
})

test('formatINRCompact formats compact abbreviations', () => {
  assert.equal(formatINRCompact(15000000), '₹1.5Cr')
  assert.equal(formatINRCompact(250000), '₹2.5L')
  assert.equal(formatINRCompact(5000), '₹5k')
  assert.equal(formatINRCompact(500), '₹500')
  assert.equal(formatINRCompact(null), '—')
  assert.equal(formatINRCompact(undefined), '—')
})

