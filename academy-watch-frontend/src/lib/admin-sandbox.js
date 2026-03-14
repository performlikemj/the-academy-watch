function toStringOrEmpty(value) {
  if (value === null || typeof value === 'undefined') {
    return ''
  }
  return String(value)
}

/**
 * Build form value updates for a sandbox select parameter.
 * Ensures linked hidden fields (e.g. team ids) mirror the selected option metadata.
 */
export function buildSelectUpdates(param, option, allParams = []) {
  if (!param || typeof param.name !== 'string') {
    return {}
  }

  const paramNames = new Set(
    Array.isArray(allParams)
      ? allParams
          .map((p) => (p && typeof p.name === 'string' ? p.name : null))
          .filter(Boolean)
      : []
  )

  const updates = {}
  const primaryName = param.name

  if (!option) {
    updates[primaryName] = ''
    if (paramNames.has('team_db_id')) updates.team_db_id = ''
    if (paramNames.has('api_team_id')) updates.api_team_id = ''
    return updates
  }

  updates[primaryName] = toStringOrEmpty(option.value ?? option.label ?? '')

  for (const [key, value] of Object.entries(option)) {
    if (key === 'value' || key === 'label') continue
    if (paramNames.has(key)) {
      updates[key] = toStringOrEmpty(value)
    }
  }

  if ('team_id' in option && paramNames.has('api_team_id')) {
    updates.api_team_id = toStringOrEmpty(option.team_id)
  }

  return updates
}

function toBoolean(value, fallback = true) {
  if (typeof value === 'boolean') {
    return value
  }
  return !!fallback
}

export function mergeCollapseState(previous = {}, tasks = [], defaultCollapsed = true) {
  const next = {}
  if (!Array.isArray(tasks)) {
    return { ...previous }
  }

  for (const task of tasks) {
    if (!task || typeof task.task_id !== 'string') continue
    const taskId = task.task_id
    if (Object.prototype.hasOwnProperty.call(previous || {}, taskId)) {
      next[taskId] = toBoolean(previous[taskId], defaultCollapsed)
    } else {
      next[taskId] = toBoolean(undefined, defaultCollapsed)
    }
  }

  return next
}

export function toggleCollapseState(state = {}, taskId) {
  if (!taskId || typeof taskId !== 'string') {
    return state
  }

  const currentValue = Object.prototype.hasOwnProperty.call(state || {}, taskId)
    ? toBoolean(state[taskId])
    : true

  return { ...state, [taskId]: !currentValue }
}

export function sandboxCardHeaderClasses(additional = '') {
  const base = 'flex items-start justify-between gap-3 border-b px-4 py-3 sticky top-16 z-20 bg-white'
  return additional ? `${base} ${additional}` : base
}

export function sofascoreRowKey(row, index = 0) {
  if (row && typeof row === 'object') {
    if (row.player_id) {
      return `player-${row.player_id}`
    }
    if (row.supplemental_id) {
      return `supp-${row.supplemental_id}`
    }
  }

  const name = (row?.player_name || 'player').toString().trim().toLowerCase().replace(/\s+/g, '-') || 'player'
  const loan = (row?.loan_team || '').toString().trim().toLowerCase().replace(/\s+/g, '-')
  return `row-${name}-${loan}-${index}`
}

export function buildSofascoreUpdatePayload(row, value) {
  if (!row || typeof row !== 'object') {
    return null
  }

  const payload = {
    sofascore_id: typeof value === 'string' ? value : value ?? '',
  }

  if (row.player_id) {
    payload.player_id = row.player_id
  }
  if (row.supplemental_id) {
    payload.supplemental_id = row.supplemental_id
  }
  if (row.player_name) {
    payload.player_name = row.player_name
  }

  if (!payload.player_id && !payload.supplemental_id) {
    return null
  }

  return payload
}
