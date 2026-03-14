export function parseNewsletterId(value) {
  if (value === null || typeof value === 'undefined') return null
  const str = String(value).trim()
  if (!str) return null
  if (str.startsWith('-')) return null

  const trailingDigits = str.match(/(\d+)(?:\D*)$/)
  if (trailingDigits && trailingDigits[1]) {
    const parsed = Number(trailingDigits[1])
    if (Number.isInteger(parsed) && parsed > 0) {
      return parsed
    }
  }

  const direct = Number(str)
  if (Number.isInteger(direct) && direct > 0) {
    return direct
  }
  return null
}

export function normalizeNewsletterIds(input) {
  const source = Array.isArray(input) ? input : [input]
  const seen = new Set()
  const result = []
  for (const candidate of source) {
    const value = parseNewsletterId(candidate)
    if (!value) continue
    if (seen.has(value)) continue
    seen.add(value)
    result.push(value)
  }
  return result
}

export function formatSendPreviewSummary({ successIds = [], failureDetails = [] } = {}) {
  const succCount = Array.isArray(successIds) ? successIds.length : 0
  const failList = Array.isArray(failureDetails) ? failureDetails : []

  if (succCount === 0 && failList.length === 0) {
    return 'No newsletters were processed.'
  }

  const chunks = []
  if (succCount > 0) {
    const suffix = succCount === 1 ? '' : 's'
    chunks.push(`Sent admin preview to ${succCount} newsletter${suffix}.`)
  }

  if (failList.length > 0) {
    const suffix = failList.length === 1 ? '' : 's'
    const ids = failList
      .map((item) => (item && item.id ? `#${item.id}` : null))
      .filter(Boolean)
    const idList = ids.length ? `: ${ids.join(', ')}` : ''
    chunks.push(`Failed for ${failList.length} newsletter${suffix}${idList}.`)
  }

  return chunks.join(' ')
}

export function formatDeleteSummary({ successIds = [], failureDetails = [] } = {}) {
  const succCount = Array.isArray(successIds) ? successIds.length : 0
  const failList = Array.isArray(failureDetails) ? failureDetails : []

  if (succCount === 0 && failList.length === 0) {
    return 'No newsletters were deleted.'
  }

  const parts = []
  if (succCount > 0) {
    const suffix = succCount === 1 ? '' : 's'
    parts.push(`Deleted ${succCount} newsletter${suffix}.`)
  }

  if (failList.length > 0) {
    const suffix = failList.length === 1 ? '' : 's'
    const ids = failList
      .map((item) => (item && item.id ? `#${item.id}` : null))
      .filter(Boolean)
    const idList = ids.length ? `: ${ids.join(', ')}` : ''
    parts.push(`Failed to delete ${failList.length} newsletter${suffix}${idList}.`)
  }

  return parts.join(' ')
}

export function resolveBulkActionPayload({
  useFilters = false,
  filterParams = {},
  totalMatched = 0,
  excludedIds = [],
  explicitIds = [],
} = {}) {
  if (useFilters) {
    const expected = Number.isFinite(totalMatched) ? Number(totalMatched) : 0
    return {
      mode: 'filters',
      body: {
        filter_params: { ...(filterParams || {}) },
        exclude_ids: normalizeNewsletterIds(excludedIds),
        expected_total: expected < 0 ? 0 : expected,
      },
    }
  }

  return {
    mode: 'ids',
    body: {
      ids: normalizeNewsletterIds(explicitIds),
    },
  }
}

export function formatBulkSelectionToast({ totalMatched = 0, totalExcluded = 0 } = {}) {
  const matched = Number(totalMatched) || 0
  const excluded = Number(totalExcluded) || 0
  if (matched <= 0) {
    return 'No newsletters match your filters.'
  }
  const base = `All ${matched} filtered newsletters selected.`
  if (excluded > 0) {
    const verb = excluded === 1 ? 'is' : 'are'
    return `${base} ${excluded} ${verb} excluded.`
  }
  return base
}

export function computeReviewProgress({ index = 0, total = 0 } = {}) {
  const safeTotal = Number(total) || 0
  if (safeTotal <= 0) {
    return 'No newsletters to review'
  }
  const safeIndex = Math.min(Math.max(Number(index) || 0, 0), safeTotal - 1)
  return `Newsletter ${safeIndex + 1} of ${safeTotal}`
}

export function getReviewModalSizing({
  minWidth = 720,
  minHeight = 480,
  maxWidth = 1100,
  maxHeight = 900,
} = {}) {
  const clamp = (value, floor) => (value && value >= floor ? value : floor)
  const resolvedMinWidth = clamp(Number(minWidth) || 0, 480)
  const resolvedMinHeight = clamp(Number(minHeight) || 0, 360)
  const resolvedMaxWidth = Math.max(Number(maxWidth) || resolvedMinWidth, resolvedMinWidth)
  const resolvedMaxHeight = Math.max(Number(maxHeight) || resolvedMinHeight, resolvedMinHeight)
  return {
    minWidth: resolvedMinWidth,
    minHeight: resolvedMinHeight,
    maxWidth: resolvedMaxWidth,
    maxHeight: resolvedMaxHeight,
    resize: 'both',
  }
}

export function buildAdminPreviewSendOptions({
  renderMode = 'web',
  useSnippets = false,
  simulateSubscription = false,
  selectedJournalists = [],
} = {}) {
  const mode = renderMode === 'email' ? 'email' : 'web'
  const normalizedJournalists = simulateSubscription
    ? normalizeNewsletterIds(selectedJournalists)
    : null

  return {
    render_mode: mode,
    use_snippets: mode === 'email' ? Boolean(useSnippets) : false,
    journalist_ids: simulateSubscription ? normalizedJournalists : null,
  }
}
