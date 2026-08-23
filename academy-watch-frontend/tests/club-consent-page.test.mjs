import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'

import { describeConsentDecision, describeConsentOutcome, INVALID_LINK_COPY } from '../src/lib/club-consent.js'

const pageFile = new URL('../src/pages/ClubConsentPage.jsx', import.meta.url)
const appFile = new URL('../src/App.jsx', import.meta.url)

test('describeConsentDecision words grant and decline from the API summary', () => {
  const grant = describeConsentDecision({ action: 'grant', player_reference: 'player profile 77', program_name: 'Club A', scout: { name: 'Alex Scout', organization: 'Fixture Recruitment' } })
  assert.equal(grant.title, 'Allow this introduction?')
  assert.equal(grant.confirmLabel, 'Allow introduction')
  assert.equal(grant.tone, 'grant')
  assert.match(grant.body, /Alex Scout \(Fixture Recruitment\) asked to contact player profile 77 at Club A/)

  const decline = describeConsentDecision({ action: 'decline' })
  assert.equal(decline.title, 'Decline this introduction?')
  assert.equal(decline.confirmLabel, 'Decline introduction')
  assert.equal(decline.tone, 'decline')
  assert.match(decline.body, /A verified scout asked to contact one of your players at your club/)
})

test('describeConsentOutcome and invalid copy are stable', () => {
  assert.equal(describeConsentOutcome('granted').title, 'Introduction allowed')
  assert.equal(describeConsentOutcome('declined').title, 'Introduction declined')
  assert.equal(describeConsentOutcome(undefined).title, 'Decision recorded')
  assert.equal(INVALID_LINK_COPY.title, 'This link is no longer valid')
})

test('the page calls the two consent API methods and App routes the email path to it', async () => {
  const page = await fs.readFile(pageFile, 'utf8')
  assert.ok(page.includes('APIService.getClubConsentSummary(token)'))
  assert.ok(page.includes('APIService.submitClubConsent(token)'))
  assert.ok(page.includes("useParams()"), 'token comes from the route param')
  const app = await fs.readFile(appFile, 'utf8')
  assert.ok(app.includes('<Route path="/contact/club-consent/:token" element={<ClubConsentPage />} />'))
  assert.ok(app.includes("import { ClubConsentPage } from '@/pages/ClubConsentPage'"))
})
