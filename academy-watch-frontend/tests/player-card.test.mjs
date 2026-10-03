import test from 'node:test'
import assert from 'node:assert/strict'
import {
  cardCounters,
  cardLine,
  cardsLabel,
  confirmedClubName,
  initialsOf,
  isGoalkeeperPosition,
  isProviderSourced,
  keeperFigure,
  calendarSeason,
  linesReadState,
  lineSource,
  lineSummary,
  matchDateParts,
  matchResult,
  minutesShare,
  profileFacts,
  providerTotals,
  providerTotalsFromMatches,
  readProblem,
  scopedValue,
  showcaseScope,
  totalsReadState,
  viewerKey,
  publicPhotos,
  quietFigure,
  resolveSeason,
  roleLabel,
  seasonKicker,
  seasonView,
  summarizeSeason,
} from '../src/lib/player-card.js'

// Totals in the shape the server returns from GET /players/:id/matches?view=lines.
function grainTotals(overrides = {}) {
  return {
    matches: 1, appearances: 1, full_matches: 1, minutes: 90, goals: 0, assists: 0,
    yellows: 0, reds: 0, cards_known: true, saves: null, goals_conceded: null, keeper_matches: 0,
    club_confirmed: 1, self_reported_only: 0, differing: 0,
    ...overrides,
  }
}

const tile = (summary, key) => summary.tiles.find((entry) => entry.key === key)

test('the single confirmed match reads exactly as the approved mockup', () => {
  const summary = summarizeSeason({ lines: [{}], totals: grainTotals() })

  assert.equal(summary.source, 'grain')
  assert.equal(summary.confirmed, true)
  assert.deepEqual(summary.tiles.map((entry) => entry.key), ['minutes', 'appearances', 'contribution', 'discipline'])
  assert.equal(tile(summary, 'minutes').value, '90')
  assert.equal(tile(summary, 'minutes').note, 'Every minute of the 1 match recorded')
  assert.equal(tile(summary, 'minutes').share, 1)
  assert.equal(tile(summary, 'appearances').note, '1 match recorded so far')
  assert.equal(summary.sentence, 'Built from 1 match. 1 confirmed by the club, 0 only reported by the player.')
})

test('zeros are quiet: a zero contribution is muted and never listed as facts', () => {
  const contribution = tile(summarizeSeason({ lines: [{}], totals: grainTotals() }), 'contribution')

  assert.deepEqual([contribution.value, contribution.quiet, contribution.note], ['0', true, 'No goals or assists yet'])
  const scoring = tile(summarizeSeason({ lines: [{}], totals: grainTotals({ goals: 3, assists: 1 }) }), 'contribution')
  assert.deepEqual([scoring.value, scoring.quiet, scoring.note], ['4', false, '3 goals · 1 assist'])
  assert.equal(tile(summarizeSeason({ lines: [{}], totals: grainTotals({ assists: 2 }) }), 'contribution').note, '2 assists')
})

test('discipline says Clean only when card counts are actually stated', () => {
  const clean = tile(summarizeSeason({ lines: [{}], totals: grainTotals() }), 'discipline')
  assert.deepEqual([clean.value, clean.note], ['Clean', 'No yellow or red cards'])

  const unknown = summarizeSeason({ lines: [{}], totals: grainTotals({ cards_known: false, yellows: null, reds: null }) })
  assert.equal(tile(unknown, 'discipline'), undefined)

  const booked = tile(summarizeSeason({ lines: [{}], totals: grainTotals({ yellows: 2, reds: 1 }) }), 'discipline')
  assert.deepEqual([booked.value, booked.note], ['3 cards', '2 yellow · 1 red'])
  assert.equal(tile(summarizeSeason({ lines: [{}], totals: grainTotals({ yellows: 1 }) }), 'discipline').note, '1 yellow')
})

test('a full mixed season states its sources and the mismatch rule without accusing anyone', () => {
  const totals = grainTotals({
    matches: 22, appearances: 20, full_matches: 14, minutes: 1611, goals: 2, assists: 5,
    yellows: 4, reds: 0, club_confirmed: 15, self_reported_only: 7, differing: 1,
  })
  const summary = summarizeSeason({ lines: new Array(22).fill({}), totals })

  assert.equal(tile(summary, 'minutes').value, '1,611')
  assert.equal(tile(summary, 'minutes').note, '81 minutes a game across 20 appearances')
  assert.ok(tile(summary, 'minutes').share > 0.89 && tile(summary, 'minutes').share < 0.9)
  assert.equal(tile(summary, 'appearances').note, 'Played in 20 of 22 matches recorded')
  assert.equal(
    summary.sentence,
    "Built from 22 matches. 15 confirmed by the club, 7 only reported by the player. Where the two reports differ, the club's figures are used.",
  )
  assert.doesNotMatch(summary.sentence, /wrong|false|incorrect|dispute/i)
})

test('only self-reported matches: no green tick on the source sentence', () => {
  const summary = summarizeSeason({ lines: [{}, {}], totals: grainTotals({ matches: 2, appearances: 2, full_matches: 1, minutes: 150, club_confirmed: 0, self_reported_only: 2 }) })

  assert.equal(summary.confirmed, false)
  assert.equal(summary.sentence, 'Built from 2 matches. 0 confirmed by the club, 2 only reported by the player.')
})

test('no matches yet is an honest empty state with no zero tiles', () => {
  for (const totals of [null, grainTotals({ matches: 0, appearances: 0, minutes: 0 })]) {
    const summary = summarizeSeason({ lines: [], totals })
    assert.deepEqual([summary.source, summary.tiles, summary.sentence], ['none', [], null])
  }
})

test('goalkeepers get keeper figures in place of goals + assists; unknown is not zero', () => {
  const keeper = summarizeSeason({
    lines: [{}, {}],
    goalkeeper: true,
    totals: grainTotals({ matches: 2, appearances: 2, full_matches: 2, minutes: 180, saves: 9, goals_conceded: 2, keeper_matches: 2 }),
  })
  assert.equal(tile(keeper, 'contribution'), undefined)
  assert.deepEqual([tile(keeper, 'keeper').label, tile(keeper, 'keeper').value, tile(keeper, 'keeper').note], ['Saves', '9', '2 conceded in 2 matches'])

  const unknown = tile(summarizeSeason({ lines: [{}], goalkeeper: true, totals: grainTotals() }), 'keeper')
  assert.deepEqual([unknown.value, unknown.quiet, unknown.note], ['–', true, 'No keeper figures recorded yet'])

  const concededOnly = tile(summarizeSeason({ lines: [{}], goalkeeper: true, totals: grainTotals({ goals_conceded: 0, keeper_matches: 1 }) }), 'keeper')
  assert.deepEqual([concededOnly.label, concededOnly.value, concededOnly.quiet], ['Conceded', '0', false])
})

test('provider totals are kept whole, labelled, and never added to the match lines', () => {
  const provider = providerTotals({
    season: '2025/2026', source: 'season-rollup', provenance: { primary_source: 'journey' },
    appearances: 30, minutes: 2400, goals: 6, assists: 4, yellows: 3, reds: 0, avg_rating: 7.12,
  })
  const summary = summarizeSeason({ lines: [{}, {}], totals: grainTotals({ matches: 2, appearances: 2, minutes: 180 }), provider })

  assert.equal(summary.source, 'provider')
  assert.equal(tile(summary, 'minutes').value, '2,400')
  assert.equal(tile(summary, 'appearances').value, '30')
  assert.equal(tile(summary, 'appearances').note, null)
  assert.equal(summary.avgRating, 7.12)
  assert.equal(
    summary.sentence,
    'Totals come from public match data. The 2 matches entered by the club or the player are listed below and are not added to these totals.',
  )
})

test('frozen mode keeps the public-data freshness line and the same no-adding rule', () => {
  const stats = {
    appearances: 1, minutes: 90, source: 'club_verified',
    public_match_data: { available: true, as_of: '2026-05-20T10:00:00+00:00', totals: { appearances: 12, minutes: 900, goals: 4, assists: 1, yellows: 2, reds: 0 } },
    club_verified: { available: true, totals: { appearances: 1, minutes: 90, goals: 2 } },
  }
  const provider = providerTotals(stats)
  const summary = summarizeSeason({ lines: [{}], totals: grainTotals(), provider, frozen: true })

  assert.equal(provider.goals, 4)
  assert.equal(tile(summary, 'contribution').value, '5')
  assert.match(summary.sentence, /^Public match data — last updated 2026-05-20\. The 1 match entered by the club or the player is listed below and is not added to these totals\.$/)
  assert.equal(tile(summary, 'minutes').value, '900')
})

test('an empty or grain-sourced stats response is not provider data', () => {
  // The frozen provider block of a community player: "available" but all zeros.
  assert.equal(providerTotals({ public_match_data: { available: true, totals: { appearances: 0, minutes: 0 } } }), null)
  assert.equal(providerTotals({ public_match_data: { available: false, totals: null } }), null)
  // Rollup totals whose headline is the club or the player are the match grain.
  assert.equal(providerTotals({ appearances: 1, minutes: 90, provenance: { primary_source: 'club' } }), null)
  assert.equal(providerTotals({ appearances: 4, minutes: 300, provenance: { primary_source: 'user' } }), null)
  assert.equal(providerTotals({ appearances: 0, minutes: 0, source: 'none' }), null)
  assert.equal(providerTotals(null), null)
  assert.equal(providerTotals({ appearances: 3, minutes: 0, source: 'limited-coverage' }).appearances, 3)
})

test('limited-coverage provider totals leave the minutes tile out instead of printing zero', () => {
  const provider = providerTotals({ appearances: 9, minutes: 0, goals: 2, assists: 1, yellows: 1, reds: 0, source: 'limited-coverage' })
  const summary = summarizeSeason({ provider, minutesKnown: false })

  assert.deepEqual(summary.tiles.map((entry) => entry.key), ['appearances', 'contribution', 'discipline'])
})

test('provider totals without stated cards show no discipline tile', () => {
  const summary = summarizeSeason({ provider: { appearances: 5, minutes: 400, goals: 1, assists: 0, yellows: null, reds: null } })

  assert.equal(tile(summary, 'discipline'), undefined)
})

test('the season shown: an explicit pick, else the provider season, else the newest with lines', () => {
  const seasons = [{ season: 2026 }, { season: 2024 }]
  assert.equal(resolveSeason({ picked: 2023, statsSeason: '2025/2026', provider: {}, seasons }), 2023)
  assert.equal(resolveSeason({ statsSeason: '2025/2026', provider: {}, seasons }), 2025)
  assert.equal(resolveSeason({ statsSeason: '2025/2026', provider: null, seasons }), 2026)
  assert.equal(resolveSeason({ statsSeason: 2025, provider: null, seasons: [] }), 2025)
  assert.equal(resolveSeason({ statsSeason: undefined, provider: null, seasons: [] }), null)
})

test('per-match figures: zeros and unknowns are an en dash, keeper zeros are facts', () => {
  assert.deepEqual([quietFigure(0), quietFigure(null), quietFigure(2)], ['–', '–', '2'])
  assert.deepEqual([keeperFigure(0), keeperFigure(null), keeperFigure(4)], ['0', '–', '4'])
  assert.equal(cardsLabel({ yellows: 0, reds: 0 }), 'None')
  assert.equal(cardsLabel({ yellows: 1, reds: 1 }), '1 yellow · 1 red')
  assert.equal(cardsLabel({ yellows: null, reds: null }), null)
  assert.deepEqual([minutesShare(45), minutesShare(120), minutesShare(null)], [0.5, 1, 0])
})

test('match date, venue and result wording', () => {
  assert.deepEqual(matchDateParts('2026-09-20'), { day: '20 Sep', year: '2026', compact: '20 SEP 2026' })
  assert.equal(matchDateParts('nonsense').day, 'Date not recorded')
  assert.deepEqual(matchResult({ result_for: 3, result_against: 1 }), { outcome: 'W', score: '3–1', label: 'Won 3–1' })
  assert.equal(matchResult({ result_for: 0, result_against: 0 }).label, 'Drew 0–0')
  assert.equal(matchResult({ result_for: 1, result_against: 2 }).outcome, 'L')
  assert.equal(matchResult({ result_for: null, result_against: 2 }), null)
})

test('source wording is neutral and uses no gendered pronoun', () => {
  assert.deepEqual(lineSource({ confirmation: 'club_confirmed', self_report: 'matches' }), {
    mark: 'Club-confirmed', confirmed: true, note: "Matches the player's own report",
  })
  assert.deepEqual(lineSource({ confirmation: 'club_confirmed', self_report: 'differs' }), {
    mark: 'Club-confirmed', confirmed: true, lead: 'Club figures shown', note: "Differs from the player's report",
  })
  assert.deepEqual(lineSource({ confirmation: 'club_confirmed', self_report: null }), { mark: 'Club-confirmed', confirmed: true, note: null })
  assert.deepEqual(lineSource({ confirmation: 'self_reported', self_report: null }), { mark: 'Self-reported', confirmed: false, note: null })
  for (const selfReport of ['matches', 'differs']) {
    const source = lineSource({ confirmation: 'club_confirmed', self_report: selfReport })
    assert.doesNotMatch(`${source.lead || ''} ${source.note}`, /\b(his|her|he|she)\b/i)
  }
})

test('the phone card sentence for one match', () => {
  assert.equal(lineSummary({ goals: 0, assists: 0, yellows: 0, reds: 0 }), 'No goals, assists or cards')
  assert.equal(lineSummary({ goals: 0, assists: 0, yellows: null, reds: null }), 'No goals or assists')
  assert.equal(lineSummary({ goals: 1, assists: 2, yellows: 1, reds: 0 }), '1 goal · 2 assists · 1 yellow')
  assert.equal(lineSummary({ saves: 5, goals_conceded: 0, yellows: 0, reds: 0 }, { goalkeeper: true }), '5 saves · none conceded')
  assert.equal(lineSummary({ saves: null, goals_conceded: null, yellows: 0, reds: 0 }, { goalkeeper: true }), 'No cards')
})

test('facts strip lists only fields with a value and keeps the server-gated agent email', () => {
  assert.deepEqual(profileFacts(null), [])
  assert.deepEqual(profileFacts({ bio: 'Only a bio', positions: '  ', height_cm: null }), [])
  const facts = profileFacts({
    positions: 'RB, RWB', preferred_foot: 'right', height_cm: 178, contract_status: 'under_contract',
    availability: 'not_looking', languages: 'English, Twi', nationality_secondary: '',
  })
  assert.deepEqual(facts.map((fact) => [fact.label, fact.value]), [
    ['Positions', 'RB, RWB'], ['Foot', 'Right'], ['Height', '178 cm'],
    ['Contract', 'Under contract'], ['Availability', 'Not looking'], ['Languages', 'English, Twi'],
  ])
  assert.ok(facts.every((fact) => !/[—–-]$/.test(fact.value)))
  assert.equal(profileFacts({ contract_status: 'expiring', contract_until: '2027-06-30' })[0].value, 'Contract expiring · until 30 Jun 2027')
  assert.equal(profileFacts({ contract_until: '2027-06-30' })[0].value, 'Until 30 Jun 2027')
  // The claimant's own contract status wins, as in the previous read view.
  assert.equal(profileFacts({ contract_status: 'free_agent', profile_contract_status: 'under_contract' })[0].value, 'Under contract')
  assert.deepEqual(profileFacts({ agent_name: 'A. Agent' }), [{ label: 'Agent', value: 'A. Agent' }])
  assert.deepEqual(
    profileFacts({ agent_name: 'A. Agent', agent_contact_email: 'agent@example.test' })[1],
    { label: 'Agent email', value: 'agent@example.test', email: true },
  )
})

test('only approved photos with a public URL are used, primary first', () => {
  const photos = publicPhotos([
    { id: 1, status: 'approved', public_url: '/a.jpg', sort_order: 2 },
    { id: 2, status: 'pending', public_url: '/pending.jpg', is_primary: true },
    { id: 3, status: 'approved', public_url: null, approved_preview_url: '/private' },
    { id: 4, status: 'approved', public_url: '/b.jpg', is_primary: true, sort_order: 9 },
    { id: 5, status: 'approved', public_url: '/c.jpg', sort_order: 1 },
    { id: 6, status: 'rejected', public_url: '/rejected.jpg' },
  ])

  assert.deepEqual(photos.map((photo) => photo.id), [4, 5, 1])
  assert.deepEqual(publicPhotos(undefined), [])
})

test('club confirmation comes only from a club-confirmed affiliation', () => {
  assert.equal(confirmedClubName([{ status: 'self_reported', club_name: 'Elsewhere' }]), null)
  assert.equal(confirmedClubName([{ status: 'club_confirmed', club_name: 'Quillmere Athletic' }, { status: 'pending', club_name: 'X' }]), 'Quillmere Athletic')
  assert.equal(confirmedClubName(null), null)
})

test('card text is built only from fields that exist', () => {
  assert.equal(initialsOf('Kofi Asante-Reid'), 'KA')
  assert.equal(initialsOf('Jean Pierre Dupont'), 'JD')
  assert.equal(initialsOf('Zed'), 'Z')
  assert.equal(initialsOf(''), '·')
  assert.equal(cardLine({ position: 'Right-back', clubName: 'Quillmere Athletic', bio: 'Defends properly. Overlaps all day.' }), 'Right-back at Quillmere Athletic. Defends properly.')
  assert.equal(cardLine({ position: 'Defender' }), 'Defender.')
  assert.equal(cardLine({}), '')
  assert.deepEqual(cardCounters({ appearances: 1, minutes: 90 }), [{ value: '1', unit: 'app' }, { value: '90', unit: 'min' }])
  assert.deepEqual(cardCounters({ appearances: 12, minutes: 1020 }), [{ value: '12', unit: 'apps' }, { value: '1,020', unit: 'min' }])
  assert.deepEqual(cardCounters({ appearances: 0, minutes: null }), [])
  assert.equal(roleLabel('RB, RWB', 'Defender'), 'RB · RWB')
  assert.equal(roleLabel('', 'Goalkeeper'), 'Goalkeeper')
  assert.equal(roleLabel(null, null), null)
})

test('goalkeeper detection matches the edit form', () => {
  for (const position of ['G', 'GK', 'Goalkeeper', 'keeper', 'GK / sweeper']) assert.equal(isGoalkeeperPosition(position), true)
  for (const position of ['Winger', 'Midfielder', 'CB', '', null]) assert.equal(isGoalkeeperPosition(position), false)
})

// ---- Fix round PCF1 -------------------------------------------------------

const providerStats = (season, minutes) => ({
  season: `${season}/${season + 1}`, source: 'season-rollup', provenance: { primary_source: 'journey' },
  appearances: 30, minutes, goals: 6, assists: 4, yellows: 3, reds: 0,
})

test('a picked season never shows provider totals that belong to another season', () => {
  // Reviewer's probe: current provider season 2026 (2,412 min), picked 2025 with one 30-minute line.
  const seasons = [{ season: 2025, lines: [{ minutes: 30 }], totals: { matches: 1, minutes: 30 } }]
  const stale = seasonView({ picked: 2025, stats: providerStats(2026, 2412), seasons })

  assert.equal(stale.season, 2025)
  assert.equal(stale.provider, null)
  assert.equal(stale.totals.minutes, 30)
  assert.equal(stale.lines.length, 1)

  const fresh = seasonView({ picked: 2025, stats: providerStats(2025, 1800), seasons })
  assert.equal(fresh.provider.minutes, 1800)
  assert.equal(fresh.lines.length, 1)
})

test('with no pick the provider season is shown, else the newest season with lines, else the fallback', () => {
  const seasons = [{ season: 2026, lines: [{}], totals: { matches: 1 } }, { season: 2024, lines: [{}, {}], totals: { matches: 2 } }]
  const provider = seasonView({ stats: providerStats(2025, 900), seasons })
  assert.deepEqual([provider.season, provider.provider.minutes, provider.lines.length], [2025, 900, 0])

  const grain = seasonView({ stats: { season: '2025/2026', appearances: 0, minutes: 0, source: 'none' }, seasons })
  assert.deepEqual([grain.season, grain.provider, grain.totals.matches], [2026, null, 1])

  assert.equal(seasonView({ stats: null, seasons: [], fallbackSeason: 2025 }).season, 2025)
  assert.equal(seasonView({ picked: 2023, stats: null, seasons }).lines.length, 0)
})

test('a failed read is never an empty season', () => {
  const good = { subjectKey: '-12:public', seasons: [{ season: 2026 }], truncated: true }

  // First load fails: an error, nothing to show, not "loading" and not "empty".
  assert.deepEqual(
    linesReadState({ good: { subjectKey: null, seasons: [] }, settled: { requestKey: 'r1', failed: true }, subjectKey: '-12:public', requestKey: 'r1' }),
    { hasLines: false, seasons: [], truncated: false, linesLoading: false, linesError: true },
  )
  // A refresh fails: the last good data stays, flagged.
  assert.deepEqual(
    linesReadState({ good, settled: { requestKey: 'r2', failed: true }, subjectKey: '-12:public', requestKey: 'r2' }),
    { hasLines: true, seasons: good.seasons, truncated: true, linesLoading: false, linesError: true },
  )
  // A refresh in flight: last good data, no error yet.
  assert.equal(linesReadState({ good, settled: { requestKey: 'r1', failed: false }, subjectKey: '-12:public', requestKey: 'r2' }).linesError, false)
  // Another viewer or another player never inherits the data.
  for (const subjectKey of ['-12:token-a', '-13:public']) {
    const other = linesReadState({ good, settled: { requestKey: null, failed: false }, subjectKey, requestKey: 'r1' })
    assert.deepEqual([other.hasLines, other.seasons, other.linesLoading], [false, [], true])
  }
})

test('entries that share a date and opponent are each listed and say so', () => {
  assert.deepEqual(lineSource({ confirmation: 'club_confirmed', self_report: null, shared_slot: true }), {
    mark: 'Club-confirmed', confirmed: true, note: 'One of several entries for this date and opponent',
  })
  assert.equal(lineSource({ confirmation: 'self_reported', shared_slot: true }).mark, 'Self-reported')
  assert.equal(lineSource({ confirmation: 'self_reported', shared_slot: false }).note, null)
})

test('list counters are printed only for provider-sourced figures', () => {
  for (const source of ['journey', 'fixtures', 'apss', 'shadow', 'api-football', { primary_source: 'journey' }, { source_category: 'api' }]) {
    assert.equal(isProviderSourced(source), true)
  }
  for (const source of ['club', 'self', 'user', 'club_confirmed', { source: 'club' }, { source_category: 'self' }, null, undefined, '', 'none', 'live-fallback']) {
    assert.equal(isProviderSourced(source), false)
  }
})

test('"This season" heads only the season that contains today', () => {
  assert.equal(calendarSeason(new Date(2026, 9, 3)), 2026)
  assert.equal(calendarSeason(new Date(2026, 6, 31)), 2025)
  assert.equal(calendarSeason(new Date(2026, 7, 1)), 2026)
  assert.equal(seasonKicker(2026, 2026), 'This season')
  assert.equal(seasonKicker(2024, 2026), 'Season')
  assert.equal(seasonKicker(null, 2026), 'Season')
})

test('the source sentence says when entries sharing a date and opponent were kept apart', () => {
  const totals = grainTotals({ matches: 2, appearances: 2, full_matches: 0, minutes: 105, club_confirmed: 2 })
  const summary = summarizeSeason({ lines: [{ shared_slot: true }, { shared_slot: true }], totals })

  assert.equal(
    summary.sentence,
    'Built from 2 matches. 2 confirmed by the club, 0 only reported by the player. Entries that share a date and opponent are listed separately and each is counted.',
  )
  assert.doesNotMatch(summarizeSeason({ lines: [{ shared_slot: false }], totals: grainTotals() }).sentence, /listed separately/)
})

// ---- Fix round PCF2 -------------------------------------------------------

test('what is held for one viewer is never usable by another', () => {
  const signedIn = showcaseScope({ playerApiId: '-12', token: 'token-a' })
  const entry = { scope: signedIn, value: { profile: { agent_contact_email: 'private-agent@example.test' } } }

  assert.equal(scopedValue(entry, signedIn), entry.value)
  // Logout, another account, another player, the local/api twin: all withheld.
  for (const scope of [
    showcaseScope({ playerApiId: '-12', token: null }),
    showcaseScope({ playerApiId: '-12', token: 'token-b' }),
    showcaseScope({ playerApiId: '-13', token: 'token-a' }),
    showcaseScope({ playerApiId: '-12', token: 'token-a', local: true }),
    null,
  ]) assert.equal(scopedValue(entry, scope), null)
  assert.equal(scopedValue(null, signedIn), null)
  assert.notEqual(viewerKey('public'), viewerKey(null))
  assert.equal(viewerKey(''), viewerKey(undefined))
})

test('a failed season-totals read keeps the last good totals of the same player, viewer and season only', () => {
  const good = { scopeKey: '42:public:2026', value: { minutes: 2412 } }

  // Initial failure: an error, nothing to show, not loading.
  assert.deepEqual(
    totalsReadState({ good: { scopeKey: null, value: null }, settled: { requestKey: 'r1', failed: true }, scopeKey: '42:public:2026', requestKey: 'r1' }),
    { hasTotals: false, stats: null, totalsLoading: false, totalsError: true },
  )
  // Failed refresh: last good totals stay, flagged.
  assert.deepEqual(
    totalsReadState({ good, settled: { requestKey: 'r2', failed: true }, scopeKey: '42:public:2026', requestKey: 'r2' }),
    { hasTotals: true, stats: good.value, totalsLoading: false, totalsError: true },
  )
  // Another season, another viewer, another player: nothing is carried over.
  for (const scopeKey of ['42:public:2025', '42:user:token-a:2026', '43:public:2026']) {
    assert.deepEqual(
      totalsReadState({ good, settled: { requestKey: 'r2', failed: false }, scopeKey, requestKey: 'r3' }),
      { hasTotals: false, stats: null, totalsLoading: true, totalsError: false },
    )
  }
})

test('provider match rows are a witness of play when the totals read is empty or failed', () => {
  const rows = [
    { fixture_date: '2026-09-01', minutes: 90, goals: 1, assists: 0 },
    { fixture_date: '2026-09-08T15:00:00Z', minutes: 62, goals: 0, assists: 2 },
  ]
  const fromRows = providerTotalsFromMatches(rows)
  assert.deepEqual(
    [fromRows.appearances, fromRows.minutes, fromRows.goals, fromRows.assists, fromRows.yellows, fromRows.as_of, fromRows.from_match_rows],
    [2, 152, 1, 2, null, '2026-09-08', true],
  )
  assert.equal(providerTotalsFromMatches([]), null)
  assert.equal(providerTotalsFromMatches(null), null)

  // Totals read failed (stats null), lines empty, rows exist: the season is not empty.
  const view = seasonView({ stats: null, seasons: [], matchRows: rows, matchRowsSeason: 2026 })
  assert.deepEqual([view.season, view.provider.minutes, view.lines.length], [2026, 152, 0])
  const summary = summarizeSeason({ provider: view.provider })
  assert.equal(summary.source, 'provider')
  assert.equal(summary.sentence, 'Totals are built from the 2 matches in the public match log.')
  assert.equal(summary.tiles.find((entry) => entry.key === 'discipline'), undefined)

  // Real provider totals win over the rebuilt ones; rows of another season are not used.
  const real = seasonView({ stats: { season: '2026/2027', appearances: 30, minutes: 2412, provenance: { primary_source: 'journey' } }, seasons: [], matchRows: rows, matchRowsSeason: 2026 })
  assert.equal(real.provider.minutes, 2412)
  assert.equal(seasonView({ picked: 2025, stats: null, seasons: [], matchRows: rows, matchRowsSeason: 2026 }).provider, null)
  assert.equal(seasonView({ stats: null, seasons: [], matchRows: rows }).provider, null)
})

test('a failed read is worded as a loading problem, never as an empty season', () => {
  assert.equal(readProblem({}), null)
  assert.match(readProblem({ totalsError: true }), /^The season could not be loaded\. This is a loading problem/)
  assert.match(readProblem({ linesError: true }), /^The matches could not be loaded\. This is a loading problem/)
  assert.match(readProblem({ totalsError: true, linesError: true }), /^The season could not be loaded/)
  assert.equal(readProblem({ totalsError: true, showing: true }), 'The season totals could not be loaded. What is shown comes from the matches that did load.')
  assert.equal(readProblem({ linesError: true, showing: true }), 'The matches entered by the club or the player could not be loaded.')
  for (const stale of [{ totalsError: true, totalsStale: true }, { linesError: true, linesStale: true }]) {
    assert.equal(readProblem({ ...stale, showing: true }), 'The latest figures could not be loaded. Showing what was loaded before.')
  }
  // "Stale" data of the read that did NOT fail is not a reason to say "loaded before".
  assert.match(readProblem({ totalsError: true, linesStale: true, showing: true }), /^The season totals could not be loaded/)
  for (const problem of [readProblem({ totalsError: true }), readProblem({ linesError: true }), readProblem({ totalsError: true, showing: true })]) {
    assert.doesNotMatch(problem, /No matches recorded|Nothing has been entered/)
  }
})
