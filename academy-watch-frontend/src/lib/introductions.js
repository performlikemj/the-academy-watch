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

// Mirrors the backend's ACTIVE_REQUEST_STATUSES: only these can still change (consent, accept, withdraw).
export const ACTIVE_REQUEST_STATUSES = ['pending', 'accepted']

export function canDecideConsent(request) {
  return request?.club_consent_status === 'pending' && ACTIVE_REQUEST_STATUSES.includes(request?.status)
}

// Pages through a list endpoint (limit/offset) until a short page comes back, so users with more than one page of
// introductions still see all of them. fetchPage(limit, offset) resolves to the API response ({ requests, total }).
export async function fetchAllRequests(fetchPage, { pageSize = 100, maxPages = 20 } = {}) {
  let rows = []
  let offset = 0
  for (let page = 0; page < maxPages; page += 1) {
    const res = await fetchPage(pageSize, offset)
    const more = Array.isArray(res?.requests) ? res.requests : []
    rows = rows.concat(more)
    if (more.length < pageSize) break
    offset += more.length
  }
  return rows
}
