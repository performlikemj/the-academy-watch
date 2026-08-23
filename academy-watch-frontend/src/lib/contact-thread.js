// Thread state + copy, pure so it is unit-tested without React.

export const MESSAGE_MAX = 2000
export const OUTCOME_NOTES_MAX = 2000

export const OUTCOME_STAGES = [
  { value: 'contacted', label: 'Contacted' },
  { value: 'trial_scheduled', label: 'Trial scheduled' },
  { value: 'trial_completed', label: 'Trial completed' },
  { value: 'signed', label: 'Signed' },
  { value: 'no_fit', label: 'Not a fit' },
]

export function outcomeLabel(stage) {
  return OUTCOME_STAGES.find((s) => s.value === stage)?.label || stage || '—'
}

export function describeThreadState(request) {
  if (!request) return { open: false, note: 'No request selected.' }
  if (request.messaging_open) return { open: true, note: null }
  if (request.status === 'pending' && request.routing_mode === 'club_included' && request.club_consent_status === 'pending') {
    return { open: false, note: 'Waiting for the player to accept and the club to allow the introduction.' }
  }
  if (request.status === 'pending') return { open: false, note: 'Waiting for the player to accept.' }
  if (request.status === 'accepted' && request.club_consent_status === 'pending') {
    return { open: false, note: 'The player accepted. Messaging opens once the club allows the introduction.' }
  }
  if (request.club_consent_status === 'declined') return { open: false, note: 'The club declined this introduction.' }
  if (request.status === 'declined') return { open: false, note: 'The player declined this introduction.' }
  if (request.status === 'withdrawn') return { open: false, note: 'This introduction was withdrawn.' }
  if (request.status === 'expired') return { open: false, note: 'This introduction expired without a reply.' }
  return { open: false, note: 'Messaging is not available for this request.' }
}

export function participantName(request, role) {
  const name = request?.participants?.[role]?.display_name
  if (name) return name
  if (role === 'scout') return 'Scout'
  if (role === 'player') return 'Player'
  return 'Club'
}

export function canSendMessage(body) {
  const trimmed = String(body || '').trim()
  return trimmed.length > 0 && trimmed.length <= MESSAGE_MAX
}
