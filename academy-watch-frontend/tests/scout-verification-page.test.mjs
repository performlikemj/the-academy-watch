import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'

import { buildVerificationPayload, parseEvidenceUrls, describeVerificationStatus, canApply } from '../src/lib/scout-verification.js'

const pageFile = new URL('../src/pages/ScoutVerificationPage.jsx', import.meta.url)
const appFile = new URL('../src/App.jsx', import.meta.url)

test('buildVerificationPayload trims, validates, and dedupes evidence links', () => {
  const ok = buildVerificationPayload({ full_name: ' Alex Scout ', organization: 'Fixture Recruitment', role_title: 'Head of Recruitment', statement: 'I scout U21s in Kanto.', evidence_text: 'https://a.example/x\nhttps://a.example/x\n\nhttps://b.example/y' })
  assert.equal(ok.ok, true)
  assert.deepEqual(ok.payload, { full_name: 'Alex Scout', organization: 'Fixture Recruitment', role_title: 'Head of Recruitment', statement: 'I scout U21s in Kanto.', evidence_urls: ['https://a.example/x', 'https://b.example/y'] })

  const bad = buildVerificationPayload({ full_name: '', organization: 'X', role_title: 'Y', statement: 'Z', evidence_text: 'http://insecure.example' })
  assert.equal(bad.ok, false)
  assert.ok(bad.errors.some((e) => e.includes('Full name is required')))
  assert.ok(bad.errors.some((e) => e.includes('Not an https:// link')))
  assert.equal(buildVerificationPayload({ full_name: 'A', organization: 'B', role_title: 'C', statement: 'D', evidence_text: '' }).ok, false)
})

test('parseEvidenceUrls splits lines and ignores blanks', () => {
  assert.deepEqual(parseEvidenceUrls(' https://one.example \n\n https://two.example'), ['https://one.example', 'https://two.example'])
  assert.deepEqual(parseEvidenceUrls(''), [])
})

test('status copy and canApply follow the server states', () => {
  assert.equal(describeVerificationStatus(null).tone, 'none')
  assert.equal(describeVerificationStatus({ status: 'approved' }).tone, 'approved')
  assert.equal(describeVerificationStatus({ status: 'pending' }).tone, 'pending')
  assert.match(describeVerificationStatus({ status: 'rejected', review_notes: 'need a club page' }).body, /need a club page/)
  assert.equal(canApply(null), true)
  assert.equal(canApply({ status: 'pending' }), false)
  assert.equal(canApply({ status: 'approved' }), false)
  assert.equal(canApply({ status: 'rejected' }), true)
  assert.equal(canApply({ status: 'revoked' }), true)
})

test('the page uses the API methods and App routes /scout/verification', async () => {
  const page = await fs.readFile(pageFile, 'utf8')
  assert.ok(page.includes('APIService.getScoutVerification()'))
  assert.ok(page.includes('APIService.submitScoutVerification(built.payload)'))
  const app = await fs.readFile(appFile, 'utf8')
  assert.ok(app.includes('<Route path="/scout/verification" element={<ScoutVerificationPage />} />'))
  assert.ok(app.includes("import { ScoutVerificationPage } from '@/pages/ScoutVerificationPage'"))
})
