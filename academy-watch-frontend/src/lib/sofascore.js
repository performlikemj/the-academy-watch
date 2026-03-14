export function normalizeSofascoreId(value) {
  if (value === null || typeof value === 'undefined') {
    return null
  }
  const trimmed = String(value).trim()
  if (!trimmed) return null
  if (!/^[0-9]+$/.test(trimmed)) {
    return null
  }
  const parsed = Number.parseInt(trimmed, 10)
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return null
  }
  return parsed
}

export function buildSofascoreEmbedUrl(value, options = {}) {
  const id = normalizeSofascoreId(value)
  if (!id) return null
  const theme = typeof options.theme === 'string' && options.theme.trim() ? options.theme.trim() : 'dark'
  return `https://widgets.sofascore.com/embed/player/${id}?widgetTheme=${encodeURIComponent(theme)}`
}
