import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'

const here = `file://${process.cwd()}/`
const pick = (env, rel) => (process.env[env] ? new URL(process.env[env], here) : new URL(rel, import.meta.url))
const appFile = pick('APP_SRC', '../src/App.jsx')
const scoutFile = pick('SCOUT_SRC', '../src/pages/ScoutPage.jsx')
const consoleFile = pick('CONSOLE_SRC', '../src/pages/MyClubConsole.jsx')
const introFile = pick('INTRO_SRC', '../src/pages/IntroductionsPage.jsx')
const deskNavFile = pick('DESK_NAV_SRC', '../src/components/scout/ScoutDesk.jsx')

test('signed-in navigation links to /introductions', async () => {
  const src = await fs.readFile(appFile, 'utf8')
  assert.ok(src.includes("items.push({ path: '/introductions', label: 'Introductions', icon: Send })"))
  const navStart = src.indexOf("{ path: '/scout/lists'")
  const settingsAt = src.indexOf("{ path: '/settings'")
  const introAt = src.indexOf("items.push({ path: '/introductions'")
  assert.ok(navStart < introAt && introAt < settingsAt, 'Introductions sits between Lists and Settings for signed-in users')
  const importBlock = src.slice(0, src.indexOf("} from 'lucide-react'"))
  assert.match(importBlock, /\bSend\b/, 'Send icon must be imported from lucide-react')
})

test('the scout desk links to introductions and verification from its own nav', async () => {
  // The desk's sub-nav (shown on every desk page) carries the links; the Discover header no longer repeats them.
  const nav = await fs.readFile(deskNavFile, 'utf8')
  assert.ok(nav.includes("{ to: '/introductions', label: 'Introductions', contactRailOnly: true }"))
  assert.ok(nav.includes("{ to: '/scout/verification', label: 'Verification' }"))
  // The verification status / prompt stays in the Discover header.
  const src = await fs.readFile(scoutFile, 'utf8')
  assert.ok(src.includes('<Link to="/scout/verification" className="no-underline hover:no-underline">'))
  assert.ok(src.includes('Get verified'))
})

test('contact entry points are gated on the /api/features contact_rail flag', async () => {
  const app = await fs.readFile(appFile, 'utf8')
  assert.ok(app.includes("import { useContactRail } from '@/hooks/useContactRail.js'"), 'App imports the hook')
  assert.ok(app.includes("if (contactRail === true) items.push({ path: '/introductions', label: 'Introductions', icon: Send })"), 'nav item behind the flag')
  assert.ok(app.includes('}, [adminUnlocked, contactRail, isJournalist, isCurator, playerProfiles])'), 'nav memo re-computes when the flag answers')
  const scout = await fs.readFile(scoutFile, 'utf8')
  assert.ok(scout.includes("const offer = contactRail === true ? deskIntroduction(player, { signedIn: Boolean(auth?.token) }) : null"), 'Introduce button behind the flag')
  assert.ok(scout.includes("const chips = DESK_CHIPS.filter((chip) => !chip.contactRailOnly || contactRail === true)"), 'the "Open to an introduction" filter is behind the flag')
  const nav = await fs.readFile(deskNavFile, 'utf8')
  assert.ok(nav.includes('const links = DESK_LINKS.filter((link) => !link.contactRailOnly || contactRail === true)'), 'the Introductions desk link is behind the flag')
  // Club panel: behaviour, not source shape. Only contact_rail === true shows the panel; off or
  // still-unknown shows the unavailable state — for managers (access null) and for staff roles
  // holding the contact capability alike.
  const { introductionsPanelState } = await import('../src/lib/staff-access.js')
  const withContact = { role: 'owner', verified: true, capabilities: ['contact'] }
  for (const access of [null, withContact]) {
    assert.equal(introductionsPanelState(access, true), 'panel', 'club panel shown when the flag is on')
    assert.equal(introductionsPanelState(access, false), 'unavailable', 'club panel behind the flag')
    assert.equal(introductionsPanelState(access, null), 'unavailable', 'flag not answered yet = not shown')
  }
  const consoleSrc = await fs.readFile(consoleFile, 'utf8')
  assert.ok(consoleSrc.includes('useContactRail()'), 'console reads the contact rail flag')
  assert.ok(consoleSrc.includes('introductionsPanelState(access, contactRail)'), 'club panel decided by the flag')
  assert.ok(consoleSrc.includes('Scout introductions are not enabled for this club.'), 'club shows unavailable state when disabled')
  const intro = await fs.readFile(introFile, 'utf8')
  assert.ok(intro.includes('if (contactRail === false) {'), 'the introductions page shows an unavailable card when the flag is off')
})
