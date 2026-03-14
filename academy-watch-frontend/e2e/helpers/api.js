import { env } from './env.js'

export async function apiRequest(path, { method = 'GET', headers = {}, body } = {}, { adminKey, token } = {}) {
  const url = path.startsWith('http') ? path : `${env.apiBaseURL}${path}`
  const mergedHeaders = {
    'Content-Type': 'application/json',
    ...headers,
  }
  if (adminKey) {
    mergedHeaders['X-API-Key'] = adminKey
    mergedHeaders['X-Admin-Key'] = adminKey
  }
  if (token) {
    mergedHeaders.Authorization = `Bearer ${token}`
  }

  const res = await fetch(url, {
    method,
    headers: mergedHeaders,
    body: body ? JSON.stringify(body) : undefined,
  })

  const text = await res.text()
  let payload = null
  try {
    payload = text ? JSON.parse(text) : null
  } catch {
    payload = text
  }

  if (!res.ok) {
    const message = payload?.error || payload?.message || `Request failed with ${res.status}`
    const err = new Error(message)
    err.status = res.status
    err.payload = payload
    throw err
  }

  return payload
}

export async function inviteJournalist(email, { adminKey, token, bio = 'E2E journalist', profileImageUrl = '' } = {}) {
  return apiRequest('/journalists/invite', {
    method: 'POST',
    body: {
      email,
      bio,
      profile_image_url: profileImageUrl,
    },
  }, { adminKey, token })
}

export async function assignJournalistTeams(journalistId, teamIds, { adminKey, token } = {}) {
  return apiRequest(`/journalists/${journalistId}/assign-teams`, {
    method: 'POST',
    body: { team_ids: teamIds },
  }, { adminKey, token })
}

export async function generateNewsletter(teamId, targetDate) {
  return apiRequest('/newsletters/generate', {
    method: 'POST',
    body: {
      team_id: teamId,
      target_date: targetDate,
      type: 'weekly',
    },
  })
}

export async function verifyLoginCode(email, code) {
  return apiRequest('/auth/verify-code', {
    method: 'POST',
    body: { email, code },
  })
}
