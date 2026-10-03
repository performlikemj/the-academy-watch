// View-model helpers for the scout desk (Discover) and the watchlist.
// Pure (no React, no network) so the wording and the "only from real data"
// rules are unit-tested. Numbers are never computed here: the server's season
// totals are printed as they arrive, with the word that says where they come from.

import { isProviderSourced } from './player-card.js'

export const RESULT_VIEWS = [
  { value: 'cards', label: 'Cards' },
  { value: 'table', label: 'Table' },
]
export const RESULT_VIEW_KEY = 'aw.scout.view'

// Cards on phones, always (the table scrolls sideways there). On wider screens
// the last choice made on this device wins; with none, cards.
export function initialResultView({ phone = false, stored = null } = {}) {
  if (phone) return 'cards'
  return RESULT_VIEWS.some((option) => option.value === stored) ? stored : 'cards'
}

// Each chip is a filter the server answers (it counts and pages the filtered
// set); nothing is filtered in the browser.
export const DESK_CHIPS = [
  { key: 'contactable', label: 'Open to an introduction', contactRailOnly: true },
  { key: 'club', label: 'Club-confirmed numbers' },
  { key: 'u21', label: 'Under 21' },
  { key: 'u23', label: 'Under 23' },
]
const AGE_PARAMS = { u21: { max_age: 20 }, u23: { max_age: 22 } }

export function deskFilterParams({ search = '', position = null, status = 'all', source = 'all', age = 'all', contactable = false, season = null } = {}) {
  const params = {}
  if (search) params.search = search
  if (position) params.position = position
  if (status !== 'all') params.status = status
  if (source !== 'all') params.source = source
  Object.assign(params, AGE_PARAMS[age] || {})
  if (contactable) params.contactable = 1
  if (season != null) params.season = season
  return params
}

function count(value) {
  const number = Number(value)
  return Number.isFinite(number) && number > 0 ? number : 0
}

function normalized(value) {
  return String(value || '').trim().toLowerCase().replaceAll('-', '_')
}

// Where a row's figures come from, as one of four kinds.
export function figuresSource(provenance) {
  const primary = normalized(provenance?.primary_source)
  if (primary === 'matches') return 'mixed'
  if (isProviderSourced(provenance)) return 'provider'
  const category = normalized(typeof provenance === 'string' ? provenance : provenance?.source_category || provenance?.source || primary)
  if (['club', 'club_confirmed', 'club_verified'].includes(category)) return 'club'
  if (['self', 'user', 'self_reported'].includes(category)) return 'self'
  return null
}

const SOURCE_WORDS = { club: 'club-confirmed', self: 'self-reported', mixed: 'club + self-reported', provider: 'public match data' }
const SOURCE_SENTENCES = {
  club: 'Club-confirmed',
  self: 'Self-reported, not yet confirmed by the club',
  mixed: 'Club-confirmed and self-reported matches, each counted once',
  provider: 'Public match data',
}

/**
 * The figures a list row may print.
 *   'figures'  — apps / minutes (and goals + assists) with their source,
 *   'none'     — the season has no play recorded: say so,
 *   'withheld' — club- or player-entered figures on a payload that does not yet
 *                carry the merged-lines contract (`club_confirmed` on the row):
 *                they could differ from the player's page, so print nothing.
 */
export function deskFigures(player) {
  if (!player) return { kind: 'withheld' }
  const source = figuresSource(player.provenance)
  const sameAsPlayerPage = source === 'provider' || Object.hasOwn(player, 'club_confirmed')
  if (!sameAsPlayerPage) return { kind: 'withheld' }
  const appearances = count(player.appearances)
  const minutes = count(player.minutes_played)
  if (!appearances && !minutes) return { kind: 'none' }
  return {
    kind: 'figures',
    appearances,
    minutes,
    contributions: count(player.goals) + count(player.assists),
    rating: player.avg_rating ?? null,
    source,
    sourceWord: SOURCE_WORDS[source] || null,
    sourceSentence: SOURCE_SENTENCES[source] || null,
  }
}

export const NO_MATCHES = 'No matches recorded yet'

const AVAILABILITY_LABELS = { open_to_moves: 'Open to moves', not_looking: 'Not looking', trial_available: 'Available for trials' }
const PATHWAY_LABELS = { academy: 'Academy', on_loan: 'On loan', first_team: 'First team', released: 'Released', sold: 'Sold', left: 'Left' }

// The card's status line: the scout's own introduction first, then what the
// player published, then the provider's pathway status. Nothing when none exists.
export function deskStatus(player) {
  const introduction = player?.introduction
  if (introduction?.state === 'pending') return 'Introduction pending'
  if (introduction?.state === 'accepted') return introduction.conversation_open ? 'In conversation' : 'Introduction accepted'
  return AVAILABILITY_LABELS[player?.availability] || PATHWAY_LABELS[player?.status] || ''
}

export function deskClubName(player) {
  return player?.loan_team_name || player?.primary_team_name || null
}

// "Quillmere Athletic · 23" — only the parts that exist.
export function deskMeta(player) {
  return [deskClubName(player), player?.age ? String(player.age) : null].filter(Boolean).join(' · ')
}

// The approved photo is a portrait; the provider's headshot is a small face.
export function deskPhotos(player) {
  return { photoUrl: player?.approved_photo_url || null, faceUrl: player?.approved_photo_url ? null : player?.player_photo || null }
}

// Boards worth showing: only those that have rows.
export function boardsWithRows(boards, phaseBoards = []) {
  return phaseBoards.filter((board) => Array.isArray(boards?.[board.key]) && boards[board.key].length > 0)
}

// ---- Watchlist: where this scout's introduction to a player stands ----------

export const INTRODUCTION_LABELS = {
  none: 'Not asked',
  pending: 'Pending',
  accepted: 'Accepted',
  declined: 'Declined',
  expired: 'Expired',
  withdrawn: 'Withdrawn',
}
const WAITING = { club: 'Waiting on the club.', player: 'Waiting on the player.', club_and_player: 'Waiting on the club and the player.' }

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

// "30 Sep", with the year only when it is not this year. Flask's naive ISO
// timestamps are UTC (as in lib/display-date.js); shown on the viewer's calendar.
function shortDate(value) {
  const text = typeof value === 'string' ? value.trim() : ''
  if (!text) return null
  const naive = /^\d{4}-\d{2}-\d{2}T/.test(text) && !/(?:z|[+-]\d{2}:?\d{2})$/i.test(text)
  const date = new Date(naive ? `${text}Z` : text)
  if (Number.isNaN(date.getTime())) return null
  const day = `${date.getDate()} ${MONTHS[date.getMonth()]}`
  return date.getFullYear() === new Date().getFullYear() ? day : `${day} ${date.getFullYear()}`
}

export function introductionThreadPath(introduction) {
  return introduction?.request_id ? `/introductions?request=${encodeURIComponent(introduction.request_id)}` : '/introductions'
}

/**
 * One description of the introduction block: `{ label, tone, detail, action }`.
 * `action` is the one sensible next step, or null:
 *   { kind: 'ask', label }      open the introduction form,
 *   { kind: 'verify', label }   the scout must be verified first,
 *   { kind: 'thread', label, to } open the existing thread.
 * Whether asking is allowed comes from the server (`can_ask`); this only words it.
 * `verification` is 'approved' | 'unverified' | 'loading' | 'unavailable'.
 */
export function introductionView(introduction, { verification = 'approved' } = {}) {
  if (!introduction || !INTRODUCTION_LABELS[introduction.state]) return null
  const { state } = introduction
  const label = INTRODUCTION_LABELS[state]
  const ask = (text) => {
    if (!introduction.can_ask) return null
    return verification === 'unverified' ? { kind: 'verify', label: 'Get verified to ask', to: '/scout/verification' } : { kind: 'ask', label: text }
  }
  const thread = { kind: 'thread', label: 'Open thread', to: introductionThreadPath(introduction) }
  const sent = shortDate(introduction.created_at)
  const answered = shortDate(introduction.responded_at)
  const via = introduction.via_club ? `, through ${introduction.via_club}` : ''

  if (state === 'none') {
    return introduction.can_ask
      ? { label, tone: 'quiet', detail: 'You have not asked for an introduction.', action: ask('Ask') }
      : { label, tone: 'quiet', detail: 'This player is not taking introductions here.', action: null }
  }
  if (introduction.closed) {
    return { label, tone: 'quiet', detail: 'This introduction is closed.', action: null }
  }
  if (state === 'pending') {
    const lead = sent ? `Sent ${sent}${via}.` : `Sent${via}.`
    return { label, tone: 'wait', detail: [lead, WAITING[introduction.waiting_on]].filter(Boolean).join(' '), action: thread }
  }
  if (state === 'accepted') {
    const lead = answered ? `Accepted ${answered}.` : 'Accepted.'
    return introduction.conversation_open
      ? { label, tone: 'good', detail: `${lead} Conversation open.`, action: thread }
      : { label, tone: 'wait', detail: [lead, WAITING[introduction.waiting_on]].filter(Boolean).join(' '), action: thread }
  }
  if (state === 'declined') {
    const who = introduction.declined_by === 'club' ? ' by the club' : ''
    const lead = answered ? `Declined${who} on ${answered}.` : `Declined${who}.`
    const again = shortDate(introduction.ask_again_from)
    return { label, tone: 'quiet', detail: again && !introduction.can_ask ? `${lead} You can ask again from ${again}.` : lead, action: ask('Ask again') }
  }
  if (state === 'expired') {
    const due = shortDate(introduction.expires_at)
    return { label, tone: 'quiet', detail: due ? `No answer by ${due}, so the request lapsed.` : 'No answer in time, so the request lapsed.', action: ask('Ask again') }
  }
  return { label, tone: 'quiet', detail: 'You withdrew this request.', action: ask('Ask again') }
}

// "Left-back · 24"
export function watchRole(player) {
  return [String(player?.position || '').trim() || null, player?.age ? String(player.age) : null].filter(Boolean).join(' · ')
}

// "Loan FC · on loan from Parent FC" for provider-tracked players; the club otherwise.
export function watchClub(player) {
  const club = deskClubName(player)
  const owner = player?.owner_team_name || player?.primary_team_name
  if (player?.loan_team_name && owner && owner !== player.loan_team_name) return `${player.loan_team_name} · from ${owner}`
  return club || ''
}
