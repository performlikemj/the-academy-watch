import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'

const here = `file://${process.cwd()}/`
const pick = (env, rel) => (process.env[env] ? new URL(process.env[env], here) : new URL(rel, import.meta.url))
const appFile = pick('APP_SRC', '../src/App.jsx')
const scoutFile = pick('SCOUT_SRC', '../src/pages/ScoutPage.jsx')
const consoleFile = pick('CONSOLE_SRC', '../src/pages/MyClubConsole.jsx')
const introFile = pick('INTRO_SRC', '../src/pages/IntroductionsPage.jsx')

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

test('contact entry points are gated on the /api/features contact_rail flag', async () => {
  const app = await fs.readFile(appFile, 'utf8')
  assert.ok(app.includes("import { useContactRail } from '@/hooks/useContactRail.js'"), 'App imports the hook')
  assert.ok(app.includes("if (contactRail === true) items.push({ path: '/introductions', label: 'Introductions', icon: Send })"), 'nav item behind the flag')
  assert.ok(app.includes('}, [adminUnlocked, contactRail, isJournalist, isCurator, token])'), 'nav memo re-computes when the flag answers')
  const scout = await fs.readFile(scoutFile, 'utf8')
  assert.ok(scout.includes('{contactRail === true && player.contactable ? ('), 'Introduce button behind the flag')
  const guard = scout.indexOf('{contactRail === true ? (')
  const link = scout.indexOf('<Link to="/introductions"')
  assert.ok(guard !== -1 && link !== -1 && guard < link, 'the Introductions header button is behind the flag')
  const consoleSrc = await fs.readFile(consoleFile, 'utf8')
  assert.ok(consoleSrc.includes('{contactRail === true ? <TabsTrigger value="introductions"'), 'club tab trigger behind the flag')
  assert.ok(consoleSrc.includes('{contactRail === true ? <TabsContent value="introductions">'), 'club tab content behind the flag')
  const intro = await fs.readFile(introFile, 'utf8')
  assert.ok(intro.includes('if (contactRail === false) {'), 'the introductions page shows an unavailable card when the flag is off')
})
