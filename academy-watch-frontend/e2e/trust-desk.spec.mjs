import { test, expect } from '@playwright/test'

const verification = {
  id: 17,
  user_account_id: 91,
  user_email: 'ava@example.com',
  full_name: 'Ava Morgan',
  organization: 'Northbank Scouting',
  role_title: 'First-team scout',
  statement: 'I cover emerging academy players across the north west.',
  evidence_urls: ['https://example.com/scout-profile'],
  status: 'pending',
  submitted_at: '2026-08-07T09:30:00Z',
  review_notes: null,
}

const report = {
  id: 29,
  status: 'open',
  reason: 'harassment',
  reason_code: 'harassment',
  details: 'Repeated unwanted messages.',
  created_at: '2026-08-08T11:15:00Z',
  reporter: {
    account_id: 42,
    display_name: 'Jamie Chen',
    email: 'jamie@example.com',
  },
  target: {
    content_type: 'contact_message',
    id: 'message-12',
    excerpt: 'This is the reported message excerpt.',
  },
}

const contactRequest = {
  id: 'request-flagged',
  created_at: '2026-08-06T08:00:00Z',
  last_activity: '2026-08-08T10:30:00Z',
  status: 'pending',
  routing_mode: 'club_notified',
  club_consent_status: 'not_required',
  scout: { account_id: 91, name: 'Ava Morgan', organization: 'Northbank Scouting' },
  player_api_id: 7001,
  player_name: 'Jordan Hale',
  message_count: 2,
  status_contradiction: true,
}

test('Trust Desk renders all queues, flags contradictions, and approves a verification', async ({ page }) => {
  const approveRequests = []

  await page.addInitScript(() => {
    localStorage.setItem('academy_watch_user_token', 'mock-admin-token')
    localStorage.setItem('academy_watch_is_admin', 'true')
    localStorage.setItem('academy_watch_admin_key', 'mock-admin-key')
  })

  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())

    if (url.pathname === '/api/admin/auth-check') {
      return route.fulfill({ json: { ok: true } })
    }
    if (url.pathname === '/api/admin/scout-verifications' && request.method() === 'GET') {
      return route.fulfill({ json: { verifications: [verification], total: 1, limit: 50, offset: 0 } })
    }
    if (url.pathname === '/api/admin/scout-verifications/17/approve' && request.method() === 'POST') {
      approveRequests.push({ method: request.method(), pathname: url.pathname, body: request.postDataJSON() })
      return route.fulfill({ json: { verification: { ...verification, status: 'approved' } } })
    }
    if (url.pathname === '/api/admin/reports' && request.method() === 'GET') {
      return route.fulfill({ json: { reports: [report], total: 1, limit: 50, offset: 0 } })
    }
    if (url.pathname === '/api/admin/contact/requests' && request.method() === 'GET') {
      return route.fulfill({ json: { requests: [contactRequest], total: 1, page: 1, pages: 1 } })
    }

    return route.fulfill({ json: {} })
  })

  await page.goto('/admin/trust')

  await expect(page.getByRole('heading', { name: 'Trust Desk' })).toBeVisible()
  await expect(page.getByRole('tab', { name: 'Verifications' })).toBeVisible()
  await expect(page.getByRole('tab', { name: 'Reports' })).toBeVisible()
  await expect(page.getByRole('tab', { name: 'Contact oversight' })).toBeVisible()
  await expect(page.getByText('Ava Morgan', { exact: true })).toBeVisible()

  await page.getByRole('button', { name: 'Approve' }).click()
  await page.getByLabel('Review note').fill('Credentials and evidence checked.')
  await page.getByRole('button', { name: 'Approve application' }).click()

  await expect.poll(() => approveRequests).toEqual([{
    method: 'POST',
    pathname: '/api/admin/scout-verifications/17/approve',
    body: { review_notes: 'Credentials and evidence checked.' },
  }])

  await page.getByRole('tab', { name: 'Reports' }).click()
  await expect(page.getByText('Content reports', { exact: true })).toBeVisible()

  await page.getByRole('tab', { name: 'Contact oversight' }).click()
  await expect(page.getByText('Contact oversight', { exact: true }).last()).toBeVisible()
  await expect(page.getByText('Contradiction', { exact: true })).toBeVisible()
})
