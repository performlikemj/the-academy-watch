import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'

const appFile = new URL('../src/App.jsx', import.meta.url)
const scoutFile = new URL('../src/pages/ScoutPage.jsx', import.meta.url)

test('signed-in navigation links to /introductions', async () => {
  const src = await fs.readFile(appFile, 'utf8')
  assert.ok(src.includes("items.push({ path: '/introductions', label: 'Introductions', icon: Send })"))
  const navStart = src.indexOf("items.push({ path: '/scout/lists'")
  const settingsAt = src.indexOf("items.push({ path: '/settings'")
  const introAt = src.indexOf("items.push({ path: '/introductions'")
  assert.ok(navStart < introAt && introAt < settingsAt, 'Introductions sits between Lists and Settings for signed-in users')
  const importBlock = src.slice(0, src.indexOf("} from 'lucide-react'"))
  assert.match(importBlock, /\bSend\b/, 'Send icon must be imported from lucide-react')
})

test('the Scout Desk header links to introductions and verification', async () => {
  const src = await fs.readFile(scoutFile, 'utf8')
  assert.ok(src.includes('<Link to="/introductions" className="no-underline hover:no-underline">'))
  assert.ok(src.includes('<Link to="/scout/verification" className="no-underline hover:no-underline">'))
  assert.ok(src.includes('Get verified'))
})
