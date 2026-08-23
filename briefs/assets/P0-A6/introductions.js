// Row copy and action rules for the introductions page. Pure, unit-tested without React.

export const STATUS_LABELS = {
  pending: 'Pending',
  accepted: 'Accepted',
  declined: 'Declined',
  withdrawn: 'Withdrawn',
  expired: 'Expired',
}

export function statusLabel(status) {
  return STATUS_LABELS[status] || status || '—'
}

export function counterpartName(request, box) {
  const role = box === 'inbox' ? 'scout' : 'player'
  const name = request?.participants?.[role]?.display_name
  if (name) return name
  return role === 'scout' ? 'A scout' : `Player ${request?.player_api_id ?? ''}`.trim()
}

export function canWithdraw(request, box) {
  return box === 'sent' && request?.status === 'pending'
}

export function canRespond(request, box) {
  return box === 'inbox' && request?.status === 'pending'
}

export function previewText(message, max = 120) {
  const text = String(message || '').replace(/\s+/g, ' ').trim()
  return text.length > max ? `${text.slice(0, max - 1)}…` : text
}

export function upsertRequest(list, updated) {
  if (!updated?.id) return list
  const exists = list.some((r) => r.id === updated.id)
  return exists ? list.map((r) => (r.id === updated.id ? updated : r)) : [updated, ...list]
}
