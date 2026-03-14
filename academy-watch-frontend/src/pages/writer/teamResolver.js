/**
 * Resolve the latest team row (new season) that matches the selected assignment.
 * Falls back to the given teamId if anything fails.
 * @param {string|number} teamId - the assignment's team PK
 * @param {{ getTeam: Function, getTeams: Function }} api
 * @returns {Promise<string|number>}
 */
export async function resolveLatestTeamId(teamId, api) {
  try {
    const selected = await api.getTeam(teamId)
    const apiTeamId = selected?.team_id
    if (!apiTeamId) return teamId

    const teams = await api.getTeams({ has_loans: 'true' })
    if (!Array.isArray(teams)) return teamId

    const latest = teams.find((t) => String(t.team_id) === String(apiTeamId))
    return latest?.id ?? teamId
  } catch (err) {
    console.warn('resolveLatestTeamId fallback to original id', err)
    return teamId
  }
}
