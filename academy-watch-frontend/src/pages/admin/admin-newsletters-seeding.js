export function seedSelectedButtonLabel({ isSeeding, selectionCount }) {
  if (isSeeding) {
    if (selectionCount > 1) return `Seeding ${selectionCount} teams...`
    return 'Seeding team...'
  }
  return 'Seed Selected Teams'
}

export function seedTop5ButtonLabel({ isSeeding, dryRun }) {
  if (isSeeding) return 'Seeding top-5...'
  return dryRun ? 'Preview Seeding' : 'Seed Top-5 Leagues'
}

export function buildMissingNamesParams({ season, teamDbId, teamApiId, activeOnly = true, limit } = {}) {
  const params = {}

  const seasonProvided = season !== undefined && season !== null && `${season}`.trim() !== ''
  if (seasonProvided) {
    const numericSeason = Number(season)
    if (!Number.isFinite(numericSeason)) throw new Error('season must be a year when provided')
    params.season = numericSeason
  }

  const hasDbId = teamDbId !== undefined && teamDbId !== null && `${teamDbId}`.trim() !== ''
  const hasApiId = teamApiId !== undefined && teamApiId !== null && `${teamApiId}`.trim() !== ''

  if (hasDbId) {
    const dbId = Number(teamDbId)
    if (!Number.isFinite(dbId)) throw new Error('primary_team_db_id must be numeric')
    params.primary_team_db_id = dbId
  } else if (hasApiId) {
    const apiId = Number(teamApiId)
    if (!Number.isFinite(apiId)) throw new Error('primary_team_api_id must be numeric')
    if (!seasonProvided) throw new Error('season is required when using team API id')
    params.primary_team_api_id = apiId
  }

  params.active_only = activeOnly ? 'true' : 'false'

  const limitProvided = limit !== undefined && limit !== null && `${limit}`.trim() !== ''
  if (limitProvided) {
    const numericLimit = Number(limit)
    if (!Number.isFinite(numericLimit)) throw new Error('limit must be numeric')
    params.limit = numericLimit
  }

  return params
}

export function buildBackfillNamesPayload({ season, teamDbId, teamApiId, activeOnly = true, limit, dryRun = false } = {}) {
  const numericSeason = Number(season)
  if (!Number.isFinite(numericSeason)) throw new Error('season is required')

  const payload = {
    season: numericSeason,
    active_only: !!activeOnly,
    dry_run: !!dryRun,
  }

  const hasDbId = teamDbId !== undefined && teamDbId !== null && `${teamDbId}`.trim() !== ''
  const hasApiId = teamApiId !== undefined && teamApiId !== null && `${teamApiId}`.trim() !== ''

  if (hasDbId) {
    const dbId = Number(teamDbId)
    if (!Number.isFinite(dbId)) throw new Error('primary_team_db_id must be numeric')
    payload.primary_team_db_id = dbId
  } else if (hasApiId) {
    const apiId = Number(teamApiId)
    if (!Number.isFinite(apiId)) throw new Error('primary_team_api_id must be numeric')
    payload.primary_team_api_id = apiId
  }

  const limitProvided = limit !== undefined && limit !== null && `${limit}`.trim() !== ''
  if (limitProvided) {
    const numericLimit = Number(limit)
    if (!Number.isFinite(numericLimit)) throw new Error('limit must be numeric')
    payload.limit = numericLimit
  }

  return payload
}
