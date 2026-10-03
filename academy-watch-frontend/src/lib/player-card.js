// View-model helpers for the player card and the read view of a player's season.
// Pure (no React, no network) so the wording and the quiet-zero rules are unit-tested.
//
// Match lines and their totals are NOT computed here: the server merges the
// player's own entries with the club's (GET /players/:id/matches?view=lines) and
// totals exactly those lines. This module only decides what to say about them.

const GRAIN_SOURCES = new Set(['club', 'club_confirmed', 'club_verified', 'user', 'self', 'self_reported', 'matches'])
const FULL_MATCH_MINUTES = 90
export const MATCH_LINES_PREVIEW = 10
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

const FOOT_LABELS = { left: 'Left', right: 'Right', both: 'Both' }
const CONTRACT_LABELS = { under_contract: 'Under contract', expiring: 'Contract expiring', free_agent: 'Free agent' }
const AVAILABILITY_LABELS = { open_to_moves: 'Open to moves', not_looking: 'Not looking', trial_available: 'Available for trials' }
const VENUE_LABELS = { home: 'home', away: 'away', neutral: 'neutral venue' }

function count(value) {
  const number = Number(value)
  return Number.isFinite(number) && number > 0 ? number : 0
}

function known(value) {
  return value !== null && value !== undefined && Number.isFinite(Number(value))
}

function plural(number, one, many = `${one}s`) {
  return `${number.toLocaleString('en-GB')} ${number === 1 ? one : many}`
}

export function initialsOf(name) {
  const words = String(name || '').trim().split(/\s+/).filter(Boolean)
  if (!words.length) return '·'
  const letters = words.length === 1 ? [words[0][0]] : [words[0][0], words[words.length - 1][0]]
  return letters.join('').toUpperCase()
}

export function isGoalkeeperPosition(position) {
  const normalized = String(position || '').trim().toLowerCase()
  return /(^|[^a-z])(g|gk|goalkeeper|keeper)(?=$|[^a-z])/.test(normalized)
}

// Same public rule as the showcase read view: approved photos that carry a
// public URL, primary first, then the owner's order.
export function publicPhotos(photos) {
  return (Array.isArray(photos) ? photos : [])
    .filter((photo) => photo?.status === 'approved' && photo.public_url)
    .sort((a, b) => {
      const primary = Number(Boolean(b.is_primary)) - Number(Boolean(a.is_primary))
      if (primary) return primary
      const aOrder = a.sort_order == null ? Number.MAX_SAFE_INTEGER : a.sort_order
      const bOrder = b.sort_order == null ? Number.MAX_SAFE_INTEGER : b.sort_order
      return aOrder - bOrder || a.id - b.id
    })
}

export function confirmedClubName(affiliations) {
  const confirmed = (Array.isArray(affiliations) ? affiliations : [])
    .filter((affiliation) => affiliation?.status === 'club_confirmed' && affiliation.club_name)
  return confirmed.length ? confirmed[confirmed.length - 1].club_name : null
}

function formatContractUntil(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(value || ''))
  if (!match) return null
  const month = MONTHS[Number(match[2]) - 1]
  return month ? `${Number(match[3])} ${month} ${match[1]}` : null
}

// Facts strip: only fields that have a value, never a placeholder dash.
export function profileFacts(profile) {
  if (!profile) return []
  const contractStatus = profile.profile_contract_status ?? profile.contract_status
  const contractUntil = formatContractUntil(profile.contract_until)
  const contract = [CONTRACT_LABELS[contractStatus], contractUntil ? `until ${contractUntil}` : null].filter(Boolean)
  const facts = [
    ['Positions', profile.positions],
    ['Foot', FOOT_LABELS[profile.preferred_foot]],
    ['Height', known(profile.height_cm) ? `${Number(profile.height_cm)} cm` : null],
    ['Contract', contract.length ? contract.join(' · ').replace(/^until /, 'Until ') : null],
    ['Availability', AVAILABILITY_LABELS[profile.availability]],
    ['Second nationality', profile.nationality_secondary],
    ['Languages', profile.languages],
    ['Agent', profile.agent_name],
  ]
    .filter(([, value]) => typeof value === 'string' && value.trim())
    .map(([label, value]) => ({ label, value: value.trim() }))
  // The server only includes the agent's email for signed-in readers.
  if (typeof profile.agent_contact_email === 'string' && profile.agent_contact_email.trim()) {
    facts.push({ label: 'Agent email', value: profile.agent_contact_email.trim(), email: true })
  }
  return facts
}

export function seasonStartOf(value) {
  const match = /^(\d{4})/.exec(String(value ?? '').trim())
  return match ? Number(match[1]) : null
}

// Provider totals count only when the provider really has play for the season.
// Totals whose headline source is the club or the player are the match grain,
// and those are read from the merged lines instead — never from here.
export function providerTotals(stats) {
  if (!stats || typeof stats !== 'object') return null
  const frozenBlock = stats.public_match_data
  if (frozenBlock && typeof frozenBlock === 'object') {
    const totals = frozenBlock.available ? frozenBlock.totals : null
    if (!totals || !(count(totals.appearances) || count(totals.minutes))) return null
    return { ...totals, as_of: frozenBlock.as_of || null }
  }
  const source = String(stats.provenance?.primary_source ?? stats.provenance?.source ?? stats.source ?? '')
    .trim().toLowerCase().replaceAll('-', '_')
  if (GRAIN_SOURCES.has(source) || GRAIN_SOURCES.has(String(stats.source || '').toLowerCase())) return null
  if (!(count(stats.appearances) || count(stats.minutes))) return null
  return {
    appearances: stats.appearances,
    minutes: stats.minutes,
    goals: stats.goals,
    assists: stats.assists,
    yellows: stats.yellows,
    reds: stats.reds,
    saves: stats.saves,
    goals_conceded: stats.goals_conceded,
    avg_rating: stats.avg_rating,
    as_of: null,
  }
}

// Which season the read view shows: an explicit pick wins; otherwise the season
// the provider totals describe; otherwise the newest season that has lines.
export function resolveSeason({ picked, statsSeason, provider, seasons }) {
  if (Number.isInteger(picked)) return picked
  const available = (Array.isArray(seasons) ? seasons : []).map((entry) => entry.season)
  const fromStats = seasonStartOf(statsSeason)
  if (provider && fromStats != null) return fromStats
  if (available.length) return Math.max(...available)
  return fromStats
}

// Everything the season block needs, decided in one place from ONE picked
// season. Provider totals are used only when they describe the season being
// shown — a response for another season (e.g. still in flight after a pick)
// is never printed under this season's heading.
export function seasonView({ picked, stats, seasons, fallbackSeason, matchRows, matchRowsSeason } = {}) {
  // The provider's per-match rows are a second, independent witness of play:
  // when the totals read is empty or failed, totals are built from them (as
  // the page always did) rather than calling the season empty.
  const rowsSeason = seasonStartOf(matchRowsSeason)
  const fromRows = rowsSeason != null ? providerTotalsFromMatches(matchRows) : null
  const fromStats = providerTotals(stats)
  const statsSeason = seasonStartOf(stats?.season)
  const providerSeason = fromStats && statsSeason != null ? statsSeason : fromRows ? rowsSeason : null
  const season = resolveSeason({
    picked,
    statsSeason: providerSeason ?? statsSeason ?? fallbackSeason,
    provider: providerSeason != null ? (fromStats || fromRows) : null,
    seasons,
  })
  const entry = (Array.isArray(seasons) ? seasons : []).find((item) => item.season === season) || null
  const provider = fromStats && statsSeason === season
    ? fromStats
    : fromRows && rowsSeason === season ? fromRows : null
  return {
    season,
    provider,
    statsMatchSeason: statsSeason === season,
    lines: entry?.lines || [],
    totals: entry?.totals || null,
  }
}

// Provider totals rebuilt from the provider's own per-match rows.
export function providerTotalsFromMatches(rows) {
  const played = (Array.isArray(rows) ? rows : []).filter((row) => row && typeof row === 'object')
  if (!played.length) return null
  const sum = (key) => played.reduce((total, row) => total + count(row[key]), 0)
  const knownSum = (key) => (played.some((row) => known(row[key])) ? sum(key) : null)
  const dates = played.map((row) => String(row.fixture_date || '').slice(0, 10)).filter(Boolean).sort()
  return {
    appearances: played.length,
    minutes: sum('minutes'),
    goals: sum('goals'),
    assists: sum('assists'),
    yellows: knownSum('yellows'),
    reds: knownSum('reds'),
    saves: knownSum('saves'),
    goals_conceded: knownSum('goals_conceded'),
    avg_rating: null,
    as_of: dates.length ? dates[dates.length - 1] : null,
    from_match_rows: true,
  }
}

// ---- Who is looking --------------------------------------------------------
// Everything the read view keeps is scoped to the player AND the viewer. The
// moment the viewer changes (logout, login, another account) the previous
// viewer's data stops being used — at render time, before any request answers.
export function viewerKey(token) {
  return token ? `user:${token}` : 'public'
}

export function showcaseScope({ local = false, playerApiId, token }) {
  return `${local ? 'local' : 'api'}:${playerApiId}:${viewerKey(token)}`
}

// A value stored with the scope it was loaded for is only usable in that scope.
export function scopedValue(entry, scope) {
  return entry && scope != null && entry.scope === scope ? entry.value : null
}

// One write to a viewer-bound state entry `{ scope, value }`.
// `writer` is the viewer the setter was made for; `current` is the viewer on
// screen now. A write from another viewer — a mutation started by A that
// answers or fails after the switch to B — changes nothing: it can neither
// show A's value to B nor throw away what B has already loaded.
export function viewerStateWrite(previous, { writer, current, next, initial = null }) {
  if (writer !== current) return previous
  const base = previous && previous.scope === writer ? previous.value : initial
  return { scope: writer, value: typeof next === 'function' ? next(base) : next }
}

// Season totals read: the same rule as the match lines. `scopeKey` is player +
// viewer + season; a failure keeps the last good totals of the SAME scope.
export function totalsReadState({ good, settled, scopeKey, requestKey }) {
  const hasTotals = scopeKey != null && good?.scopeKey === scopeKey
  const isSettled = settled?.requestKey === requestKey
  return {
    hasTotals,
    stats: hasTotals ? good.value : null,
    totalsLoading: !hasTotals && !isSettled,
    totalsError: isSettled && settled.failed === true,
  }
}

// The one sentence shown when a read behind the season block failed, or null.
// `showing` = something is on screen for the season (tiles or lines).
export function readProblem({ linesError = false, linesStale = false, totalsError = false, totalsStale = false, showing = false } = {}) {
  if (!linesError && !totalsError) return null
  const stale = (linesError && linesStale) || (totalsError && totalsStale)
  if (stale) return 'The latest figures could not be loaded. Showing what was loaded before.'
  if (!showing) {
    return linesError && !totalsError
      ? 'The matches could not be loaded. This is a loading problem — it does not mean nothing has been recorded.'
      : 'The season could not be loaded. This is a loading problem — it does not mean nothing has been recorded.'
  }
  if (totalsError) return 'The season totals could not be loaded. What is shown comes from the matches that did load.'
  return 'The matches entered by the club or the player could not be loaded.'
}

// What the read view may show for the match lines, given the last good answer
// and how the latest request ended. A failed read is never an empty season:
// the last good data for the SAME player and viewer stays, flagged as an error.
const NO_SEASONS = Object.freeze([])

export function linesReadState({ good, settled, subjectKey, requestKey }) {
  const hasLines = subjectKey != null && good?.subjectKey === subjectKey
  const isSettled = settled?.requestKey === requestKey
  return {
    hasLines,
    seasons: hasLines ? good.seasons : NO_SEASONS,
    truncated: hasLines && good.truncated === true,
    linesLoading: !hasLines && !isSettled,
    linesError: isSettled && settled.failed === true,
  }
}

// Football season that contains a date: August to July, as the server's
// current_stats_season() does. Used only to word the heading.
export function calendarSeason(date = new Date()) {
  return date.getMonth() >= 7 ? date.getFullYear() : date.getFullYear() - 1
}

export function seasonKicker(season, currentSeason) {
  return Number.isInteger(season) && season === currentSeason ? 'This season' : 'Season'
}

const PROVIDER_SOURCES = new Set(['api', 'api_football', 'fixtures', 'journey', 'apss', 'shadow'])

// True only when a list row's figures are known to come from the provider.
// Scout counters now receive the canonical reported totals too. This helper
// classifies provenance for other consumers that distinguish provider figures.
export function isProviderSourced(provenance) {
  const raw = typeof provenance === 'string'
    ? provenance
    : provenance?.source_category || provenance?.source || provenance?.primary_source
  return PROVIDER_SOURCES.has(String(raw || '').trim().toLowerCase().replaceAll('-', '_'))
}

function minutesTile(totals, matchCount) {
  const minutes = count(totals.minutes)
  const appearances = count(totals.appearances)
  const full = known(totals.full_matches) ? count(totals.full_matches) : null
  let note = null
  if (appearances > 0) {
    note = full != null && full === matchCount && matchCount > 0
      ? `Every minute of the ${plural(matchCount, 'match', 'matches')} recorded`
      : `${Math.round(minutes / appearances)} minutes a game across ${plural(appearances, 'appearance')}`
  }
  return {
    key: 'minutes',
    label: 'Minutes',
    shortLabel: 'Minutes',
    value: minutes.toLocaleString('en-GB'),
    quiet: minutes === 0,
    share: appearances > 0 ? Math.min(1, minutes / (appearances * FULL_MATCH_MINUTES)) : 0,
    note,
  }
}

function appearancesTile(totals, matchCount, { provider }) {
  const appearances = count(totals.appearances)
  let note = null
  if (!provider) {
    note = appearances === matchCount
      ? `${plural(matchCount, 'match', 'matches')} recorded so far`
      : `Played in ${appearances} of ${plural(matchCount, 'match', 'matches')} recorded`
  }
  return { key: 'appearances', label: 'Appearances', shortLabel: 'Apps', value: appearances.toLocaleString('en-GB'), quiet: appearances === 0, note }
}

function contributionTile(totals) {
  const goals = count(totals.goals)
  const assists = count(totals.assists)
  return {
    key: 'contribution',
    label: 'Goals + assists',
    shortLabel: 'G + A',
    value: String(goals + assists),
    quiet: goals + assists === 0,
    note: goals + assists === 0
      ? 'No goals or assists yet'
      : [goals ? plural(goals, 'goal') : null, assists ? plural(assists, 'assist') : null].filter(Boolean).join(' · '),
  }
}

// Whatever keeper figures exist replace the goals + assists tile. Unknown is not zero.
function keeperTile(totals) {
  const savesKnown = known(totals.saves)
  const concededKnown = known(totals.goals_conceded)
  const keeperMatches = count(totals.keeper_matches)
  const across = keeperMatches ? ` in ${plural(keeperMatches, 'match', 'matches')}` : ''
  if (!savesKnown && !concededKnown) {
    return { key: 'keeper', label: 'Saves', shortLabel: 'Saves', value: '–', quiet: true, note: 'No keeper figures recorded yet' }
  }
  if (!savesKnown) {
    const conceded = count(totals.goals_conceded)
    return { key: 'keeper', label: 'Conceded', shortLabel: 'Conceded', value: String(conceded), quiet: false, note: `Goals conceded${across}` }
  }
  const saves = count(totals.saves)
  return {
    key: 'keeper',
    label: 'Saves',
    shortLabel: 'Saves',
    value: String(saves),
    quiet: saves === 0,
    note: concededKnown ? `${count(totals.goals_conceded)} conceded${across}` : 'Goals conceded not recorded',
  }
}

// "Clean" only when the source actually states card counts. Unknown shows nothing.
function disciplineTile(totals) {
  const cardsKnown = 'cards_known' in totals ? Boolean(totals.cards_known) : known(totals.yellows) && known(totals.reds)
  if (!cardsKnown) return null
  const yellows = count(totals.yellows)
  const reds = count(totals.reds)
  if (yellows + reds === 0) {
    return { key: 'discipline', label: 'Discipline', shortLabel: 'Cards', value: 'Clean', word: true, quiet: false, note: 'No yellow or red cards' }
  }
  return {
    key: 'discipline',
    label: 'Discipline',
    shortLabel: 'Cards',
    value: plural(yellows + reds, 'card'),
    word: true,
    quiet: false,
    note: [yellows ? `${yellows} yellow` : null, reds ? `${reds} red` : null].filter(Boolean).join(' · '),
  }
}

function grainSentence(totals, lines = []) {
  const matches = count(totals.matches)
  const confirmed = count(totals.club_confirmed)
  const selfOnly = count(totals.self_reported_only)
  const parts = [`Built from ${plural(matches, 'match', 'matches')}. ${confirmed} confirmed by the club, ${selfOnly} only reported by the player.`]
  if (count(totals.differing) > 0) parts.push("Where the two reports differ, the club's figures are used.")
  if (lines.some((line) => line?.shared_slot)) parts.push('Entries that share a date and opponent are listed separately and each is counted.')
  return parts.join(' ')
}

function providerSentence(provider, { frozen, lineCount }) {
  const asOf = provider.as_of ? String(provider.as_of).slice(0, 10) : null
  if (provider.from_match_rows) {
    const built = `Totals are built from the ${plural(count(provider.appearances), 'match', 'matches')} in the public match log.`
    if (!lineCount) return built
    return `${built} The ${plural(lineCount, 'match', 'matches')} entered by the club or the player ${lineCount === 1 ? 'is' : 'are'} listed separately and ${lineCount === 1 ? 'is' : 'are'} not added to these totals.`
  }
  const lead = frozen
    ? `Public match data — last updated ${asOf || 'unknown'}.`
    : 'Totals come from public match data.'
  if (!lineCount) return lead
  return `${lead} The ${plural(lineCount, 'match', 'matches')} entered by the club or the player ${lineCount === 1 ? 'is' : 'are'} listed below and ${lineCount === 1 ? 'is' : 'are'} not added to these totals.`
}

/**
 * One description of the season block. `source` is:
 *   'provider' — the provider has real totals; they are shown whole and labelled,
 *   'grain'    — totals are exactly the merged match lines,
 *   'none'     — nothing recorded: an honest empty state, no zero tiles.
 * Provider totals and match-line totals are never added together.
 */
export function summarizeSeason({ lines = [], totals = null, provider = null, goalkeeper = false, frozen = false, minutesKnown = true } = {}) {
  const lineCount = Array.isArray(lines) ? lines.length : 0
  const usingProvider = Boolean(provider)
  if (!usingProvider && (!totals || !count(totals.matches))) {
    return { source: 'none', tiles: [], sentence: null, confirmed: false }
  }
  const figures = usingProvider ? provider : totals
  const matchCount = usingProvider ? count(provider.appearances) : count(totals.matches)
  const tiles = [
    // Limited-coverage provider totals carry no minutes: leave the tile out rather than print a zero.
    usingProvider && !minutesKnown ? null : minutesTile(usingProvider ? { ...figures, full_matches: null } : figures, matchCount),
    appearancesTile(figures, matchCount, { provider: usingProvider }),
    goalkeeper ? keeperTile(figures) : contributionTile(figures),
    disciplineTile(figures),
  ].filter(Boolean)
  return {
    source: usingProvider ? 'provider' : 'grain',
    tiles,
    sentence: usingProvider ? providerSentence(provider, { frozen, lineCount }) : grainSentence(totals, Array.isArray(lines) ? lines : []),
    confirmed: !usingProvider && count(totals.club_confirmed) > 0,
    avgRating: usingProvider && known(provider.avg_rating) ? Number(provider.avg_rating) : null,
  }
}

export function matchDateParts(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(value || ''))
  const month = match ? MONTHS[Number(match[2]) - 1] : null
  if (!month) return { day: 'Date not recorded', year: '', compact: 'DATE NOT RECORDED' }
  const day = `${Number(match[3])} ${month}`
  return { day, year: match[1], compact: `${day} ${match[1]}`.toUpperCase() }
}

export function venueLabel(homeAway) {
  return VENUE_LABELS[homeAway] || null
}

export function matchResult(line) {
  if (!known(line?.result_for) || !known(line?.result_against)) return null
  const goalsFor = Number(line.result_for)
  const against = Number(line.result_against)
  const outcome = goalsFor > against ? 'W' : goalsFor < against ? 'L' : 'D'
  return {
    outcome,
    score: `${goalsFor}–${against}`,
    label: `${outcome === 'W' ? 'Won' : outcome === 'L' ? 'Lost' : 'Drew'} ${goalsFor}–${against}`,
  }
}

export function minutesShare(minutes) {
  return Math.max(0, Math.min(1, count(minutes) / FULL_MATCH_MINUTES))
}

// Per-match figure: a zero is an en dash, an unknown is an en dash, never "0".
export function quietFigure(value) {
  return count(value) > 0 ? String(count(value)) : '–'
}

// Keeper figures are facts even at zero (a clean sheet); only unknown is a dash.
export function keeperFigure(value) {
  return known(value) ? String(Number(value)) : '–'
}

export function cardsLabel(line) {
  if (!known(line?.yellows) || !known(line?.reds)) return null
  const yellows = count(line.yellows)
  const reds = count(line.reds)
  if (yellows + reds === 0) return 'None'
  return [yellows ? `${yellows} yellow` : null, reds ? `${reds} red` : null].filter(Boolean).join(' · ')
}

// One plain sentence for the phone card.
export function lineSummary(line, { goalkeeper = false } = {}) {
  const parts = []
  if (goalkeeper) {
    if (known(line.saves)) parts.push(plural(Number(line.saves), 'save'))
    if (known(line.goals_conceded)) parts.push(Number(line.goals_conceded) === 0 ? 'none conceded' : `${Number(line.goals_conceded)} conceded`)
  } else {
    if (count(line.goals)) parts.push(plural(count(line.goals), 'goal'))
    if (count(line.assists)) parts.push(plural(count(line.assists), 'assist'))
  }
  if (count(line.yellows)) parts.push(`${count(line.yellows)} yellow`)
  if (count(line.reds)) parts.push(`${count(line.reds)} red`)
  if (parts.length) return parts.join(' · ')
  const cardsStated = known(line.yellows) && known(line.reds)
  if (goalkeeper) return cardsStated ? 'No cards' : 'No keeper figures recorded'
  return cardsStated ? 'No goals, assists or cards' : 'No goals or assists'
}

// Source wording. Neutral by design: a difference is stated, never judged.
export function lineSource(line) {
  // Several entries share this date and opponent and could not be paired:
  // each is listed and counted, and the page says so rather than guessing.
  if (line?.shared_slot) {
    const confirmed = line.confirmation === 'club_confirmed'
    return { mark: confirmed ? 'Club-confirmed' : 'Self-reported', confirmed, note: 'One of several entries for this date and opponent' }
  }
  if (line?.confirmation === 'club_confirmed') {
    if (line.self_report === 'matches') return { mark: 'Club-confirmed', confirmed: true, note: "Matches the player's own report" }
    if (line.self_report === 'differs') return { mark: 'Club-confirmed', confirmed: true, lead: 'Club figures shown', note: "Differs from the player's report" }
    return { mark: 'Club-confirmed', confirmed: true, note: null }
  }
  return { mark: 'Self-reported', confirmed: false, note: null }
}

// Short role label for the chip on a photo: "RB, RWB" -> "RB · RWB".
export function roleLabel(positions, fallback) {
  const stated = String(positions || '').split(/[,/;]/).map((part) => part.trim()).filter(Boolean).slice(0, 3)
  if (stated.length) return stated.join(' · ')
  return String(fallback || '').trim() || null
}

// The line under the name on a list card: only fields that exist, never invented.
export function cardLine({ position, clubName, bio } = {}) {
  const role = [String(position || '').trim(), String(clubName || '').trim()].filter(Boolean)
  const lead = role.length === 2 ? `${role[0]} at ${role[1]}.` : role.length ? `${role[0]}.` : ''
  const sentence = String(bio || '').trim().split(/(?<=[.!?])\s+/)[0] || ''
  return [lead, sentence].filter(Boolean).join(' ')
}

export function cardCounters({ appearances, minutes } = {}) {
  const counters = []
  if (count(appearances)) counters.push({ value: count(appearances).toLocaleString('en-GB'), unit: count(appearances) === 1 ? 'app' : 'apps' })
  if (count(minutes)) counters.push({ value: count(minutes).toLocaleString('en-GB'), unit: 'min' })
  return counters
}
