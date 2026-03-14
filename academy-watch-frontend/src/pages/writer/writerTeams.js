/**
 * Normalize writer team payloads for selection lists, including assignment metadata.
 * Supports legacy array responses and the newer object shape.
 * @param {any} data
 * @returns {Array<{key: string, team_id: number | null, team_name: string, assignment_type: 'parent' | 'loan', direction: 'loaned_from' | 'loaned_to', is_custom_team: boolean}>}
 */
export function normalizeWriterTeams(data) {
  const normalized = []

  if (Array.isArray(data)) {
    for (const assignment of data) {
      const teamId = assignment?.team_id ?? null
      if (!teamId) continue
      normalized.push({
        key: `parent:${teamId}`,
        team_id: teamId,
        team_name: assignment?.team_name || assignment?.name || '',
        assignment_type: 'parent',
        direction: 'loaned_from',
        is_custom_team: false,
      })
    }
    return normalized
  }

  if (!data || typeof data !== 'object') {
    return []
  }

  const parentAssignments = Array.isArray(data.assignments)
    ? data.assignments
    : Array.isArray(data.parent_club_assignments)
      ? data.parent_club_assignments
      : []

  for (const assignment of parentAssignments) {
    const teamId = assignment?.team_id ?? null
    if (!teamId) continue
    normalized.push({
      key: `parent:${teamId}`,
      team_id: teamId,
      team_name: assignment?.team_name || assignment?.name || '',
      assignment_type: 'parent',
      direction: 'loaned_from',
      is_custom_team: false,
    })
  }

  const loanAssignments = Array.isArray(data.loan_team_assignments) ? data.loan_team_assignments : []
  for (const assignment of loanAssignments) {
    const teamId = assignment?.loan_team_id ?? null
    const name = assignment?.loan_team_name || assignment?.team_name || ''
    const key = teamId ? `loan:${teamId}` : `loan:custom:${name}`
    normalized.push({
      key,
      team_id: teamId,
      team_name: name,
      assignment_type: 'loan',
      direction: 'loaned_to',
      is_custom_team: Boolean(assignment?.is_custom_team || !teamId),
    })
  }

  return normalized
}
