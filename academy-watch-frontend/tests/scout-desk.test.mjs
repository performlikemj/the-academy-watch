import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  DESK_CHIPS, NO_MATCHES, boardsWithRows, deskFigures, deskFilterParams, deskMeta, deskPhotos, deskStatus,
  figuresSource, initialResultView, introductionThreadPath, introductionView, watchClub, watchRole,
} from '../src/lib/scout-desk.js'

const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf8')

test('cards on phones whatever was stored; the last choice on wider screens; cards when there is none', () => {
  assert.equal(initialResultView({ phone: true, stored: 'table' }), 'cards')
  assert.equal(initialResultView({ phone: false, stored: 'table' }), 'table')
  assert.equal(initialResultView({ phone: false, stored: 'cards' }), 'cards')
  assert.equal(initialResultView({ phone: false, stored: null }), 'cards')
  assert.equal(initialResultView({ phone: false, stored: 'grid' }), 'cards')
})

test('every chip is a parameter the server filters on', () => {
  assert.deepEqual(DESK_CHIPS.map((chip) => chip.label), ['Open to an introduction', 'Club-confirmed numbers', 'Under 21', 'Under 23'])
  assert.deepEqual(deskFilterParams({}), {})
  assert.deepEqual(deskFilterParams({ contactable: true }), { contactable: 1 })
  assert.deepEqual(deskFilterParams({ source: 'club' }), { source: 'club' })
  assert.deepEqual(deskFilterParams({ age: 'u21' }), { max_age: 20 })
  assert.deepEqual(deskFilterParams({ age: 'u23' }), { max_age: 22 })
  assert.deepEqual(
    deskFilterParams({ search: 'kofi', position: 'Defender', status: 'on_loan', source: 'self', age: 'u23', contactable: true, season: 2025 }),
    { search: 'kofi', position: 'Defender', status: 'on_loan', source: 'self', max_age: 22, contactable: 1, season: 2025 },
  )
})

test('the desk never filters a page of results in the browser', () => {
  const desk = read('../src/pages/ScoutPage.jsx')
  assert.ok(!/players\.filter\(/.test(desk), 'results are filtered client-side')
  assert.match(desk, /const filterParams = useMemo\(\(\) => deskFilterParams\(/)
})

test('where the figures come from', () => {
  assert.equal(figuresSource({ source_category: 'club', primary_source: 'club' }), 'club')
  assert.equal(figuresSource({ source_category: 'self', primary_source: 'user' }), 'self')
  assert.equal(figuresSource({ source_category: 'api', primary_source: 'journey' }), 'provider')
  assert.equal(figuresSource({ primary_source: 'fixtures' }), 'provider')
  // Merged club + self-only totals (the merged-lines rollup).
  assert.equal(figuresSource({ source_category: 'club', primary_source: 'matches' }), 'mixed')
  assert.equal(figuresSource(null), null)
})

test('figures print with their source word once the row carries the merged-lines contract', () => {
  const club = { club_confirmed: true, appearances: 1, minutes_played: 90, goals: 0, assists: 0, provenance: { source_category: 'club', primary_source: 'club' } }
  assert.deepEqual(
    (({ kind, appearances, minutes, contributions, sourceWord }) => ({ kind, appearances, minutes, contributions, sourceWord }))(deskFigures(club)),
    { kind: 'figures', appearances: 1, minutes: 90, contributions: 0, sourceWord: 'club-confirmed' },
  )
  const self = { club_confirmed: false, appearances: 1, minutes_played: 72, goals: 1, assists: 0, provenance: { source_category: 'self', primary_source: 'user' } }
  assert.equal(deskFigures(self).sourceWord, 'self-reported')
  assert.equal(deskFigures(self).sourceSentence, 'Self-reported, not yet confirmed by the club')
  assert.equal(deskFigures(self).contributions, 1)
  const mixed = { club_confirmed: true, appearances: 3, minutes_played: 254, provenance: { source_category: 'club', primary_source: 'matches' } }
  assert.equal(deskFigures(mixed).sourceWord, 'club + self-reported')
  const provider = { appearances: 30, minutes_played: 2412, avg_rating: 7.1, provenance: { source_category: 'api', primary_source: 'journey' } }
  assert.equal(deskFigures(provider).sourceWord, 'public match data')
  assert.equal(deskFigures(provider).rating, 7.1)
})

test('club- or player-entered figures are withheld on a payload that predates the contract', () => {
  // No `club_confirmed` key: these totals could differ from the player's page.
  assert.deepEqual(deskFigures({ appearances: 2, minutes_played: 164, provenance: { source_category: 'club', primary_source: 'club' } }), { kind: 'withheld' })
  assert.deepEqual(deskFigures({ appearances: 0, minutes_played: 0, provenance: { source_category: 'self' } }), { kind: 'withheld' })
  // Provider figures are the same totals the player's page shows, before and after.
  assert.equal(deskFigures({ appearances: 30, minutes_played: 2412, provenance: { source_category: 'api' } }).kind, 'figures')
})

test('"No matches recorded yet" only when the season is known to be empty', () => {
  assert.equal(NO_MATCHES, 'No matches recorded yet')
  assert.deepEqual(deskFigures({ club_confirmed: false, appearances: 0, minutes_played: 0, provenance: { source_category: 'self' } }), { kind: 'none' })
  assert.deepEqual(deskFigures({ club_confirmed: false, appearances: null, minutes_played: null, provenance: { source_category: 'self' } }), { kind: 'none' })
  assert.deepEqual(deskFigures({ appearances: 0, minutes_played: 0, provenance: { source_category: 'api' } }), { kind: 'none' })
})

test('the status line comes only from real data: own introduction, then availability, then pathway', () => {
  assert.equal(deskStatus({}), '')
  assert.equal(deskStatus({ availability: 'open_to_moves' }), 'Open to moves')
  assert.equal(deskStatus({ availability: 'not_looking' }), 'Not looking')
  assert.equal(deskStatus({ availability: 'trial_available' }), 'Available for trials')
  assert.equal(deskStatus({ availability: 'somewhere' }), '')
  assert.equal(deskStatus({ status: 'on_loan' }), 'On loan')
  assert.equal(deskStatus({ availability: 'open_to_moves', introduction: { state: 'pending' } }), 'Introduction pending')
  assert.equal(deskStatus({ introduction: { state: 'accepted', conversation_open: true } }), 'In conversation')
  assert.equal(deskStatus({ introduction: { state: 'accepted', conversation_open: false } }), 'Introduction accepted')
  // A finished request says nothing on the card; what the player published still shows.
  assert.equal(deskStatus({ availability: 'not_looking', introduction: { state: 'declined' } }), 'Not looking')
  assert.equal(deskStatus({ introduction: { state: 'none', can_ask: true } }), '')
})

test('club · age, and which image the tile gets', () => {
  assert.equal(deskMeta({ primary_team_name: 'Quillmere Athletic', age: 23 }), 'Quillmere Athletic · 23')
  assert.equal(deskMeta({ loan_team_name: 'Loan FC', primary_team_name: 'Parent FC', age: 19 }), 'Loan FC · 19')
  assert.equal(deskMeta({ age: 24 }), '24')
  assert.equal(deskMeta({}), '')
  assert.deepEqual(deskPhotos({ approved_photo_url: '/a.jpg', player_photo: '/p.png' }), { photoUrl: '/a.jpg', faceUrl: null })
  assert.deepEqual(deskPhotos({ player_photo: '/p.png' }), { photoUrl: null, faceUrl: '/p.png' })
  assert.deepEqual(deskPhotos({}), { photoUrl: null, faceUrl: null })
})

test('only boards that have rows are shown', () => {
  const phase = [{ key: 'top_scorers' }, { key: 'top_assists' }, { key: 'most_minutes' }]
  assert.deepEqual(boardsWithRows({ top_scorers: [{ player_id: 1 }], top_assists: [], most_minutes: null }, phase), [{ key: 'top_scorers' }])
  assert.deepEqual(boardsWithRows({}, phase), [])
  assert.deepEqual(boardsWithRows(null, phase), [])
})

const YEAR = new Date().getFullYear()

test('introduction: not asked — Ask only when the rules allow it', () => {
  assert.deepEqual(introductionView({ state: 'none', can_ask: true }), {
    label: 'Not asked', tone: 'quiet', detail: 'You have not asked for an introduction.', action: { kind: 'ask', label: 'Ask' },
  })
  assert.deepEqual(introductionView({ state: 'none', can_ask: false }), {
    label: 'Not asked', tone: 'quiet', detail: 'This player is not taking introductions here.', action: null,
  })
  // An unverified scout is sent to verification instead of the form.
  assert.deepEqual(introductionView({ state: 'none', can_ask: true }, { verification: 'unverified' }).action, {
    kind: 'verify', label: 'Get verified to ask', to: '/scout/verification',
  })
  assert.equal(introductionView(null), null)
  assert.equal(introductionView({ state: 'mystery' }), null)
})

test('introduction: pending and accepted open the thread and say who is awaited', () => {
  const pending = introductionView({ state: 'pending', request_id: 'r-1', created_at: `${YEAR}-09-30T10:00:00`, via_club: 'Quillmere Athletic', waiting_on: 'club' })
  assert.deepEqual(pending, {
    label: 'Pending', tone: 'wait', detail: 'Sent 30 Sep, through Quillmere Athletic. Waiting on the club.', action: { kind: 'thread', label: 'Open thread', to: '/introductions?request=r-1' },
  })
  assert.equal(introductionView({ state: 'pending', created_at: `${YEAR}-09-30T10:00:00`, waiting_on: 'player' }).detail, 'Sent 30 Sep. Waiting on the player.')
  assert.equal(introductionView({ state: 'pending', created_at: `${YEAR}-09-30T10:00:00`, via_club: 'Q', waiting_on: 'club_and_player' }).detail, 'Sent 30 Sep, through Q. Waiting on the club and the player.')

  const open = introductionView({ state: 'accepted', request_id: 'r-2', responded_at: `${YEAR}-09-28T10:00:00`, conversation_open: true })
  assert.deepEqual([open.label, open.tone, open.detail, open.action.label], ['Accepted', 'good', 'Accepted 28 Sep. Conversation open.', 'Open thread'])
  const awaitingClub = introductionView({ state: 'accepted', responded_at: `${YEAR}-09-28T10:00:00`, conversation_open: false, waiting_on: 'club' })
  assert.deepEqual([awaitingClub.tone, awaitingClub.detail], ['wait', 'Accepted 28 Sep. Waiting on the club.'])
  assert.equal(introductionThreadPath({}), '/introductions')
})

test('introduction: declined, expired and withdrawn offer "Ask again" only where the rules allow it', () => {
  const cooling = introductionView({ state: 'declined', responded_at: `${YEAR}-09-10T10:00:00`, declined_by: 'player', can_ask: false, ask_again_from: `${YEAR}-10-10T10:00:00` })
  assert.deepEqual(cooling, { label: 'Declined', tone: 'quiet', detail: 'Declined on 10 Sep. You can ask again from 10 Oct.', action: null })
  const later = introductionView({ state: 'declined', responded_at: `${YEAR}-06-10T10:00:00`, declined_by: 'club', can_ask: true, ask_again_from: null })
  assert.deepEqual([later.detail, later.action], ['Declined by the club on 10 Jun.', { kind: 'ask', label: 'Ask again' }])

  const expired = introductionView({ state: 'expired', expires_at: `${YEAR}-09-14T10:00:00`, can_ask: true })
  assert.deepEqual([expired.label, expired.detail, expired.action.label], ['Expired', 'No answer by 14 Sep, so the request lapsed.', 'Ask again'])
  assert.equal(introductionView({ state: 'expired', can_ask: false }).action, null)

  const withdrawn = introductionView({ state: 'withdrawn', can_ask: true })
  assert.deepEqual([withdrawn.label, withdrawn.detail, withdrawn.action.label], ['Withdrawn', 'You withdrew this request.', 'Ask again'])
  assert.equal(introductionView({ state: 'withdrawn', can_ask: true }, { verification: 'unverified' }).action.kind, 'verify')
})

test('introduction: a thread that is no longer reachable offers nothing', () => {
  assert.deepEqual(introductionView({ state: 'pending', closed: true, request_id: 'r-9' }), {
    label: 'Pending', tone: 'quiet', detail: 'This introduction is closed.', action: null,
  })
})

test('a date in another year keeps its year', () => {
  assert.equal(introductionView({ state: 'pending', created_at: '2024-09-30T10:00:00', waiting_on: 'player' }).detail, 'Sent 30 Sep 2024. Waiting on the player.')
})

test('watchlist identity lines use only what exists', () => {
  assert.equal(watchRole({ position: 'Left-back', age: 24 }), 'Left-back · 24')
  assert.equal(watchRole({ position: 'Left-back' }), 'Left-back')
  assert.equal(watchRole({}), '')
  assert.equal(watchClub({ primary_team_name: 'Quillmere Athletic' }), 'Quillmere Athletic')
  assert.equal(watchClub({ loan_team_name: 'Loan FC', primary_team_name: 'Parent FC' }), 'Loan FC · from Parent FC')
  assert.equal(watchClub({ loan_team_name: 'Loan FC', primary_team_name: 'Parent FC', owner_team_name: 'Owner FC' }), 'Loan FC · from Owner FC')
  assert.equal(watchClub({ loan_team_name: 'Town FC' }), 'Town FC')
  assert.equal(watchClub({}), '')
})

test('the watchlist prints the note in full, and never beside a control that cuts it', () => {
  const page = read('../src/pages/WatchlistPage.jsx')
  const note = page.slice(page.indexOf('function NoteBlock'), page.indexOf('function IntroductionBlock'))
  assert.match(note, /whitespace-pre-wrap[^"]*\[overflow-wrap:anywhere\]/)
  assert.ok(!/truncate|line-clamp/.test(note), 'the note is cut')
  assert.ok(!/<table/.test(page), 'the watchlist is a table again')
})

test('leaders are drawn only with rows, below the results', () => {
  const desk = read('../src/pages/ScoutPage.jsx')
  assert.match(desk, /\{leaderBoards\.length \? \(/)
  assert.ok(desk.indexOf('aria-label="Results"') < desk.indexOf('aria-label="Leaders"'), 'leaders come before the results')
  assert.ok(!/No data yet/.test(desk), 'an empty board is drawn')
  assert.ok(!/Every tracked academy and loan player/.test(desk), 'the frozen product line is back')
  assert.match(desk, /Adult players who chose to be seen, with numbers their clubs stand behind\./)
})
