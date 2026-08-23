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

test('the club console gains an Introductions tab wired to the panel', async () => {
  const src = await fs.readFile(consoleFile, 'utf8')
  assert.ok(src.includes("import { ClubIntroductionsPanel } from '@/components/contact/ClubIntroductionsPanel'"))
  assert.ok(src.includes('<TabsTrigger value="introductions" className="py-2"><Send className="h-4 w-4" /> Introductions</TabsTrigger>'))
  assert.ok(src.includes('<TabsContent value="introductions"><ClubIntroductionsPanel programId={programId} onAccessDenied={onAccessDenied} /></TabsContent>'))
  assert.ok(src.includes("'sm:grid-cols-5 lg:min-w-[55rem]' : 'sm:grid-cols-4 lg:min-w-[44rem]'"))
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
