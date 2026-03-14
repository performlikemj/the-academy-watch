export const NEWSLETTER_GENERATE_ENDPOINT = '/newsletters/generate'
export const NEWSLETTER_GENERATE_ALL_ENDPOINT = '/newsletters/generate-weekly-all'
export const LOANS_SEED_TEAM_ENDPOINT = '/admin/loans/seed-team'
export const LOANS_SEED_TOP5_ENDPOINT = '/admin/loans/seed-top5'

export function buildGenerateTeamRequest({ teamId, targetDate, forceRefresh }) {
  if (!teamId) throw new Error('teamId is required')
  return {
    endpoint: NEWSLETTER_GENERATE_ENDPOINT,
    options: {
      method: 'POST',
      body: JSON.stringify({
        team_id: teamId,
        target_date: targetDate,
        force_refresh: !!forceRefresh
      })
    },
    admin: true
  }
}

export function buildGenerateAllRequest({ targetDate }) {
  return {
    endpoint: NEWSLETTER_GENERATE_ALL_ENDPOINT,
    options: {
      method: 'POST',
      body: JSON.stringify({
        target_date: targetDate
      })
    },
    admin: true
  }
}

export function buildSeedTeamRequest({ teamId, season, dryRun = false, overwrite = false, apiTeamId } = {}) {
  const numericSeason = season != null ? Number(season) : NaN
  const dbId = teamId != null ? Number(teamId) : NaN
  const apiId = apiTeamId != null ? Number(apiTeamId) : NaN

  if (!Number.isFinite(numericSeason)) throw new Error('season is required')
  if (!Number.isFinite(dbId) && !Number.isFinite(apiId)) throw new Error('teamId or apiTeamId is required')

  const body = {
    season: numericSeason,
    dry_run: !!dryRun,
    overwrite: !!overwrite,
  }
  if (Number.isFinite(dbId)) body.team_db_id = dbId
  if (!Number.isFinite(dbId) && Number.isFinite(apiId)) body.api_team_id = apiId

  return {
    endpoint: LOANS_SEED_TEAM_ENDPOINT,
    options: {
      method: 'POST',
      body: JSON.stringify(body),
    },
    admin: true,
  }
}

export function buildSeedTop5Request({ season, dryRun = false, overwrite = false, leagueIds, windowKey } = {}) {
  const numericSeason = season != null ? Number(season) : NaN
  if (!Number.isFinite(numericSeason)) throw new Error('season is required')

  const body = {
    season: numericSeason,
    dry_run: !!dryRun,
    overwrite: !!overwrite,
  }

  if (Array.isArray(leagueIds) && leagueIds.length) body.league_ids = leagueIds
  if (windowKey != null && `${windowKey}`.trim() !== '') body.window_key = `${windowKey}`.trim()

  return {
    endpoint: LOANS_SEED_TOP5_ENDPOINT,
    options: {
      method: 'POST',
      body: JSON.stringify(body),
    },
    admin: true,
  }
}
