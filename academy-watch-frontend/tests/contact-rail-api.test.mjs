import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'

const apiFile = new URL('../src/lib/api.js', import.meta.url)

const EXPECTED = [
  ['getScoutVerification', "'/scout/verification'"],
  ['submitScoutVerification', "'/scout/verification'"],
  ['createContactRequest', "'/contact/requests'"],
  ['listContactRequests', '`/contact/requests?${query}`'],
  ['acceptContactRequest', '/accept`'],
  ['declineContactRequest', '/decline`'],
  ['withdrawContactRequest', '/withdraw`'],
  ['setClubConsent', '/club-consent`'],
  ['getContactMessages', '/messages?${query}`'],
  ['sendContactMessage', '/messages`'],
  ['reportContactOutcome', '/outcome`'],
  ['getClubConsentSummary', '`/contact/club-consent/${encodeURIComponent(token)}`'],
  ['submitClubConsent', '`/contact/club-consent/${encodeURIComponent(token)}`'],
]

// One method's source: from its `static async <name>(` up to the next `static async ` (or EOF).
// No whitespace-sensitive brace pattern: a method body end is "the next method starts".
function methodBody(src, name) {
  const start = src.indexOf(`static async ${name}(`)
  if (start === -1) return null
  const next = src.indexOf('static async ', start + 1)
  return src.slice(start, next === -1 ? src.length : next)
}

test('APIService exposes every user-level contact-rail method with its endpoint', async () => {
  const src = await fs.readFile(apiFile, 'utf8')
  for (const [name, endpoint] of EXPECTED) {
    const body = methodBody(src, name)
    assert.ok(body, `APIService.${name} must exist`)
    assert.ok(body.includes(endpoint), `APIService.${name} must call ${endpoint}`)
  }
})

test('createContactRequest sends player_api_id, message and permission_attestation', async () => {
  const src = await fs.readFile(apiFile, 'utf8')
  const body = methodBody(src, 'createContactRequest')
  assert.ok(body, 'APIService.createContactRequest must exist')
  assert.match(body, /JSON\.stringify\(\{ player_api_id, message, permission_attestation \}\)/)
})

test('the admin contact methods still exist and still require the admin key', async () => {
  const src = await fs.readFile(apiFile, 'utf8')
  assert.match(methodBody(src, 'adminListContactRequests') || '', /\{ admin: true \}/)
  assert.match(methodBody(src, 'adminGetContactRequest') || '', /\{ admin: true \}/)
})
