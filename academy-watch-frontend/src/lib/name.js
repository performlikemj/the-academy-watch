/**
 * Initials for a player/person name — the ONE implementation used by the
 * profile hero, scout cards, and the canvas stat card, so a player's
 * initials render identically everywhere ("Jordan Demo" → "JD").
 */
export function getInitials(name) {
  const parts = (name || '').trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase()
}
