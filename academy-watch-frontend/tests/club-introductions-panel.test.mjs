import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'

const panelFile = new URL('../src/components/contact/ClubIntroductionsPanel.jsx', import.meta.url)
const consoleFile = new URL('../src/pages/MyClubConsole.jsx', import.meta.url)

test('the panel lists the club box, decides consent through APIService, and mounts the thread', async () => {
  const src = await fs.readFile(panelFile, 'utf8')
  assert.ok(src.includes("APIService.listContactRequests({ box: 'club', limit, offset })"))
  assert.ok(src.includes('fetchAllRequests('), 'the club box is paged through, not cut at the first page')
  assert.ok(src.includes('APIService.setClubConsent(request.id, { action })'))
  assert.ok(src.includes("decide(request, 'grant')"))
  assert.ok(src.includes("decide(request, 'decline')"))
  assert.ok(src.includes('<ContactThread request={selected} onRequestChange={applyUpdate} canReportOutcome={false} />'))
  assert.ok(src.includes('data-testid="club-introductions-panel"'))
})

test('the club console keeps Introductions reachable through the Scouts rail', async () => {
  const { clubViewAllowed, introductionsPanelState } = await import('../src/lib/staff-access.js')
  const withContact = { role: 'manager', verified: true, capabilities: ['players.view', 'contact'] }
  const coach = { role: 'coach', verified: false, capabilities: ['players.view', 'matches.view', 'feedback'] }

  // Staff access dark (access === null): exactly the pre-existing behaviour — Scouts is always
  // reachable and the panel shows whenever the contact rail is on.
  assert.equal(clubViewAllowed(null).introductions, true)
  assert.equal(introductionsPanelState(null, true), 'panel')
  // Staff access on: reachable for roles holding the contact capability, hidden for the others.
  assert.equal(clubViewAllowed(withContact, true).introductions, true)
  assert.equal(introductionsPanelState(withContact, true), 'panel')
  assert.equal(clubViewAllowed(coach, true).introductions, false)
  assert.equal(introductionsPanelState(coach, true), 'hidden')

  // Wiring: the console renders the panel from that decision and the shell keeps the Scouts rail entry.
  const src = await fs.readFile(consoleFile, 'utf8')
  const shell = await fs.readFile(new URL('../src/pages/club-console/ClubHome.jsx', import.meta.url), 'utf8')
  assert.ok(src.includes('panel: <ClubIntroductionsPanel'), 'the introductions panel is still mounted by the console')
  assert.ok(src.includes('[introductionsPanelState(access, contactRail)]'), 'and chosen by the shared decision')
  assert.ok(shell.includes("['Scouts', Send, 'introductions']"))
  assert.ok(shell.includes('clubViewAllowed(access, staffAccessEnabled)'))
  assert.ok(shell.includes('panels[view]'))
})

test('the club panel mounts the thread without the outcome form (clubs cannot report outcomes)', async () => {
  const src = await fs.readFile(panelFile, 'utf8')
  assert.ok(src.includes('<ContactThread request={selected} onRequestChange={applyUpdate} canReportOutcome={false} />'))
})

test('consent controls show only while the request can still change', async () => {
  const src = await fs.readFile(panelFile, 'utf8')
  assert.ok(src.includes('const pending = canDecideConsent(request)'), 'Allow/Decline gated on canDecideConsent')
  assert.ok(src.includes("if (status === 'closed') return 'No longer needed'"), 'a moot pending consent is labelled, not actionable')
})
