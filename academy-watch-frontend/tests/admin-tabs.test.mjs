import test from 'node:test'
import assert from 'node:assert/strict'

import { resolveAdminTab, getAdminTabs } from '../src/lib/admin-tabs.js'

test('resolveAdminTab returns tab query when valid', () => {
  const searchParams = new URLSearchParams('tab=tools')
  assert.equal(resolveAdminTab({ searchParams }), 'tools')
})

test('resolveAdminTab falls back to provided default when query missing', () => {
  const searchParams = new URLSearchParams('')
  assert.equal(resolveAdminTab({ searchParams, defaultTab: 'loans' }), 'loans')
})

test('resolveAdminTab ignores unknown tab values', () => {
  const searchParams = new URLSearchParams('tab=players')
  assert.equal(resolveAdminTab({ searchParams, defaultTab: 'newsletters' }), 'newsletters')
})

test('resolveAdminTab handles invalid default by returning newsletters', () => {
  const searchParams = new URLSearchParams('')
  assert.equal(resolveAdminTab({ searchParams, defaultTab: 'not-a-tab' }), 'newsletters')
})

test('resolveAdminTab honors forced tab and ignores query', () => {
  const searchParams = new URLSearchParams('tab=tools')
  assert.equal(resolveAdminTab({ searchParams, defaultTab: 'loans', forcedTab: 'newsletters' }), 'newsletters')
})

test('resolveAdminTab drops tools when sandbox is excluded', () => {
  const searchParams = new URLSearchParams('tab=tools')
  const allowedTabs = getAdminTabs({ includeSandbox: false })
  assert.equal(resolveAdminTab({ searchParams, defaultTab: 'loans', allowedTabs }), 'loans')
})

test('getAdminTabs omits tools when includeSandbox is false', () => {
  const tabs = getAdminTabs({ includeSandbox: false })
  assert.deepEqual(tabs, ['newsletters', 'loans', 'settings'])
})
