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

test('ShowcaseSection: the exported wrapper holds no state and keys the manage section on player + viewer', () => {
  const source = read('../src/components/ShowcaseSection.jsx')
  const wrapper = between(source, 'export function ShowcaseSection(props) {', 'function ShowcaseSectionBody({')
  assert.deepEqual(wrapper.match(STATEFUL), null)
  assert.match(wrapper, /const scope = showcaseScope\(\{ local: Boolean\(props\.local\), playerApiId: props\.playerApiId, token \}\)/)
  assert.match(wrapper, /<ShowcaseSectionBody key=\{scope\} \{\.\.\.props\} \/>/)
  // Nothing else in the file renders the body without the key.
  assert.equal(source.split('<ShowcaseSectionBody').length - 1, 1)
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
