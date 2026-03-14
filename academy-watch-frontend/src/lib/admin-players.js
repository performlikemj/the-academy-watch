export function buildPlayerNameUpdatePayload(playerId, draftName, currentName = draftName) {
  const trimmed = typeof draftName === 'string' ? draftName.trim() : ''
  if (!trimmed) {
    return null
  }
  const baseline = typeof currentName === 'string' ? currentName.trim() : ''
  if (trimmed === baseline) {
    return null
  }
  return {
    playerId,
    payload: {
      name: trimmed,
    },
  }
}
