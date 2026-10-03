import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { viewerStateWrite } from '../src/lib/player-card.js'

// Viewer change = fresh screen. The pages that hold viewer-bound state (drafts,
// dialogs, watch marks, pending requests) are split into a thin exported
// wrapper and a body keyed on player + viewer, so React remounts the body on
// logout, login or an account switch. These tests fail if state is added to a
// wrapper — i.e. outside the keyed boundary.

const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf8')
const between = (source, start, end) => {
  const from = source.indexOf(start)
  const to = source.indexOf(end, from)
  assert.ok(from >= 0 && to > from, `${start} … ${end}`)
  return source.slice(from, to)
}
const STATEFUL = /\buse(State|Reducer|Ref|Effect|LayoutEffect|Memo|Callback|ViewerState|ScopedShowcase|SeasonTotalsRead|PlayerReadView)\(/g

test('PlayerPage: the exported wrapper holds no state and keys the body on player + viewer', () => {
  const wrapper = between(read('../src/pages/PlayerPage.jsx'), 'export function PlayerPage() {', 'function PlayerPageBody() {')
  assert.deepEqual(wrapper.match(STATEFUL), null)
  assert.match(wrapper, /const viewer = useViewerKey\(\)/)
  assert.match(wrapper, /<PlayerPageBody key=\{`\$\{playerId\}:\$\{viewer\}`\} \/>/)
})

test('ScoutPage: the exported wrapper holds no state and keys the desk on the viewer', () => {
  const wrapper = between(read('../src/pages/ScoutPage.jsx'), 'export function ScoutPage() {', 'function ScoutDeskBody() {')
  assert.deepEqual(wrapper.match(STATEFUL), null)
  assert.match(wrapper, /const viewer = useViewerKey\(\)/)
  assert.match(wrapper, /<ScoutDeskBody key=\{viewer\} \/>/)
})

test('WatchlistPage: the exported wrapper holds no state and keys the watchlist on the viewer', () => {
  const source = read('../src/pages/WatchlistPage.jsx')
  const wrapper = between(source, 'export function WatchlistPage() {', 'function WatchlistBody() {')
  assert.deepEqual(wrapper.match(STATEFUL), null)
  assert.match(wrapper, /const viewer = useViewerKey\(\)/)
  assert.match(wrapper, /<WatchlistBody key=\{viewer\} \/>/)
  // The scout's entries (with their private notes) and an open introduction form are viewer state.
  assert.match(source, /const \[entries, setEntries\] = useViewerState\(viewer, NO_ENTRIES\)/)
  assert.match(source, /const \[introducePlayer, setIntroducePlayer\] = useViewerState\(viewer, null\)/)
  assert.match(source, /const saveCsv = useGuarded\(life, saveWatchlistCsv\)/)
})

// Every surface that renders private contact data (threads, messages, requests) or a
// scout's own notes is a viewer-keyed boundary: IntroductionsPage, ContactThread,
// ClubIntroductionsPanel, WatchlistPage and ListsPage.
test('IntroductionsPage: the exported wrapper holds no state and keys the page on the viewer', () => {
  const source = read('../src/pages/IntroductionsPage.jsx')
  const wrapper = between(source, 'export function IntroductionsPage() {', 'function IntroductionsBody() {')
  assert.deepEqual(wrapper.match(STATEFUL), null)
  assert.match(wrapper, /const viewer = useViewerKey\(\)/)
  assert.match(wrapper, /<IntroductionsBody key=\{viewer\} \/>/)
  // Both boxes are viewer state: a list loaded for one account is unreadable by the next.
  assert.match(source, /const \[requests, setRequests\] = useViewerState\(viewer, NO_REQUESTS\)/)
  assert.equal(source.split('<IntroductionsBody').length - 1, 1)
})

test('ContactThread: keyed on viewer + request, so one account\'s thread never renders for another', () => {
  const source = read('../src/components/contact/ContactThread.jsx')
  const wrapper = between(source, 'export function ContactThread(props) {', 'function ContactThreadBody({')
  assert.deepEqual(wrapper.match(STATEFUL), null)
  assert.match(wrapper, /const viewer = useViewerKey\(\)/)
  assert.match(wrapper, /<ContactThreadBody key=\{`\$\{viewer\}:\$\{props\.request\?\.id \?\? ''\}`\} \{\.\.\.props\} \/>/)
})

test('ClubIntroductionsPanel and ListsPage: keyed on the viewer', () => {
  const panel = between(read('../src/components/contact/ClubIntroductionsPanel.jsx'), 'export function ClubIntroductionsPanel(props) {', 'function ClubIntroductionsPanelBody({')
  assert.deepEqual(panel.match(STATEFUL), null)
  assert.match(panel, /<ClubIntroductionsPanelBody key=\{viewer\} \{\.\.\.props\} \/>/)
  const lists = between(read('../src/pages/ListsPage.jsx'), 'export function ListsPage() {', 'function ListsBody() {')
  assert.deepEqual(lists.match(STATEFUL), null)
  assert.match(lists, /<ListsBody key=\{viewer\} \/>/)
})

test('ShowcaseSection: the exported wrapper holds no state and keys the manage section on player + viewer', () => {
  const source = read('../src/components/ShowcaseSection.jsx')
  const wrapper = between(source, 'export function ShowcaseSection(props) {', 'function ShowcaseSectionBody({')
  assert.deepEqual(wrapper.match(STATEFUL), null)
  assert.match(wrapper, /const scope = showcaseScope\(\{ local: Boolean\(props\.local\), playerApiId: props\.playerApiId, token \}\)/)
  assert.match(wrapper, /<ShowcaseSectionBody key=\{scope\} \{\.\.\.props\} \/>/)
  // Nothing else in the file renders the body without the key.
  assert.equal(source.split('<ShowcaseSectionBody').length - 1, 1)
})

test('CommentSection: keyed on the viewer, because it is also mounted outside the keyed pages', () => {
  const wrapper = between(read('../src/components/CommentSection.jsx'), 'export function CommentSection(props) {', 'function CommentSectionBody({')
  assert.deepEqual(wrapper.match(STATEFUL), null)
  assert.match(wrapper, /const viewer = useViewerKey\(\)/)
  assert.match(wrapper, /<CommentSectionBody key=\{viewer\} \{\.\.\.props\} \/>/)
})

test('LocalPlayerPage: the profile is keyed on player + viewer; the wrapper keeps only the retry counter and the analytics de-dupe', () => {
  const source = read('../src/pages/LocalPlayerPage.jsx')
  const wrapper = source.slice(source.indexOf('export function LocalPlayerPage() {'))
  assert.match(wrapper, /key=\{`\$\{numericPlayerId\}-\$\{attempt\}-\$\{viewerKey\(token\)\}`\}/)
  assert.deepEqual(wrapper.match(STATEFUL), ['useState(', 'useRef(', 'useCallback('])
  assert.match(wrapper, /const \[attempt, setAttempt\] = useState\(0\)/)
  assert.match(wrapper, /const emittedProfileViewIdsRef = useRef\(new Set\(\)\)/)
})

test('viewer-bound state on the player page and the desk goes through useViewerState', () => {
  for (const path of ['../src/pages/PlayerPage.jsx', '../src/pages/ScoutPage.jsx']) {
    const source = read(path)
    assert.ok(/const \[watchedIds, setWatchedIds\] = useViewerState\(viewer, null\)/.test(source), `${path}: watch marks`)
    assert.ok(/const \[introduce(Open|Player), setIntroduce(Open|Player)\] = useViewerState\(viewer, /.test(source), `${path}: introduction form`)
    assert.ok(!/const \[watched\w*, setWatched\w*\] = useState\(/.test(source), `${path}: watch marks in plain state`)
    assert.ok(!/const \[introduce(Open|Player|For|State), \w+\] = useState\(/.test(source), `${path}: introduction form in plain state`)
  }
})

test('a write made for another viewer changes nothing', () => {
  const b = { scope: 'user:b', value: new Set([-12]) }
  // A's late rollback after the switch to B: B's loaded state is untouched (same object).
  assert.equal(viewerStateWrite(b, { writer: 'user:a', current: 'user:b', next: (ids) => new Set([...(ids || []), -99]) }), b)
  assert.equal(viewerStateWrite(b, { writer: 'user:a', current: 'user:b', next: null }), b)
  assert.equal(viewerStateWrite(b, { writer: 'user:a', current: 'public', next: new Set() }), b)
  // The current viewer's own writes work, and never start from another viewer's value.
  const own = viewerStateWrite(b, { writer: 'user:b', current: 'user:b', next: (ids) => new Set([...ids, -15]) })
  assert.deepEqual([own.scope, [...own.value]], ['user:b', [-12, -15]])
  const fresh = viewerStateWrite({ scope: 'user:a', value: new Set([-1]) }, { writer: 'user:b', current: 'user:b', next: (ids) => ids, initial: null })
  assert.deepEqual(fresh, { scope: 'user:b', value: null })
})

// ---- PCF4: requests and side effects go through the viewer's lifetime ------
// Remounting drops state but does not stop a handler that is already running.
// So no component in the keyed subtrees talks to APIService, the router or the
// global auth actions directly: they use `life.api` (refuses to start a request
// once the viewer has changed) and `useGuarded(life, …)` (no-op once unmounted
// or the viewer has changed). These tests fail when a direct call is added.
const VIEWER_BOUND_FILES = [
  '../src/pages/PlayerPage.jsx',
  '../src/pages/LocalPlayerPage.jsx',
  '../src/pages/ScoutPage.jsx',
  '../src/pages/WatchlistPage.jsx',
  '../src/pages/IntroductionsPage.jsx',
  '../src/pages/ListsPage.jsx',
  '../src/components/contact/ContactThread.jsx',
  '../src/components/contact/ClubIntroductionsPanel.jsx',
  '../src/components/ShowcaseSection.jsx',
  '../src/components/player-card/usePlayerReadView.js',
  '../src/components/PlayerReachControls.jsx',
  '../src/components/contact/IntroduceDialog.jsx',
  '../src/components/ContentReportDialog.jsx',
  '../src/components/FlagDataDialog.jsx',
  '../src/components/CommentSection.jsx',
  '../src/components/PlayerLinksSection.jsx',
  '../src/components/showcase/PlayerFeedbackInbox.jsx',
  '../src/components/WatchingMeCard.jsx',
  '../src/components/showcase/PlayerApplicationsTeaser.jsx',
  '../src/components/ShowcasePhoto.jsx',
  '../src/components/PlayerAvailability.jsx',
  '../src/components/showcase/DevelopmentAction.jsx',
]

test('no viewer-bound component calls APIService directly — every request goes through life.api', () => {
  for (const path of VIEWER_BOUND_FILES) {
    const source = read(path)
    assert.ok(!/\bAPIService\b/.test(source), `${path}: uses APIService directly; use useViewerLifetime().api`)
    assert.ok(/const life = useViewerLifetime\(\)/.test(source), `${path}: no viewer lifetime`)
    assert.ok(/const api = life\.api\b/.test(source), `${path}: no lifetime-bound api`)
    assert.ok(!/\bfetch\(/.test(source), `${path}: raw fetch`)
  }
})

test('navigation and global auth actions in those components are guarded by the lifetime', () => {
  for (const path of VIEWER_BOUND_FILES) {
    const source = read(path)
    // The router's navigate only ever exists wrapped.
    for (const use of source.match(/.*useNavigate\(\).*/g) || []) {
      assert.ok(/useGuarded\(life, useNavigate\(\)\)/.test(use), `${path}: unguarded navigate — ${use.trim()}`)
    }
    // logout / login prompt are never taken straight from the auth UI context.
    assert.ok(!/const \{[^}]*\b(logout|openLoginModal)\b[^}]*\} = useAuthUI\(\)/.test(source), `${path}: unguarded auth action`)
    assert.ok(!/authUI\.(logout|openLoginModal)\(/.test(source.replace(/useGuarded\(life, \(\) => \{[\s\S]*?\n {2}\}\)/g, '')), `${path}: auth action called outside a guard`)
    assert.ok(!/window\.location\.(assign|replace|href\s*=)/.test(source), `${path}: imperative location change`)
  }
})

// ---- PCF5: side effects that are not React state ---------------------------
// A file download, window.open or a saved object URL must not happen for
// another viewer or after leaving the page. API helpers that download on their
// own (`download*`) run beyond the guard, so these components only fetch the
// body (`fetch*` → Blob, read in full and re-checked by life.api) and save it
// through `useGuarded(life, …)`.
test('downloads and window.open in those components only happen through a guard', () => {
  for (const path of VIEWER_BOUND_FILES) {
    const source = read(path)
    assert.ok(!/\bapi\.download\w*\(/.test(source), `${path}: API helper that downloads by itself`)
    assert.ok(!/window\.open\(/.test(source), `${path}: window.open`)
    for (const line of source.match(/.*\bsaveBlobAs\(.*/g) || []) {
      assert.ok(/^const save\w+ = \(blob\) => saveBlobAs\(/.test(line), `${path}: saveBlobAs called outside a guarded saver — ${line.trim()}`)
    }
  }
  const desk = read('../src/pages/ScoutPage.jsx')
  assert.match(desk, /const saveCsv = useGuarded\(life, saveScoutCsv\)/)
  assert.match(desk, /const blob = await api\.fetchScoutCsv\(/)
})
