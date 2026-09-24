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
  const src = await fs.readFile(consoleFile, 'utf8')
  const shell = await fs.readFile(new URL('../src/pages/club-console/ClubHome.jsx', import.meta.url), 'utf8')
  assert.ok(src.includes('introductions: contactRail === true ? <ClubIntroductionsPanel'))
  assert.ok(shell.includes("['Scouts', Send, 'introductions']"))
  assert.ok(shell.includes('{panels[view]}'))
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
