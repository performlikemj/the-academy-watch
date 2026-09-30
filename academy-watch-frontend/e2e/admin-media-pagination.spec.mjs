import { expect, test } from '@playwright/test'

test('photo moderation pages, resets filters and recovers after the last item is reviewed', async ({ page, context }) => {
  await page.addInitScript(() => {
    localStorage.setItem('academy_watch_user_token', 'synthetic-token')
    localStorage.setItem('academy_watch_is_admin', 'true')
    localStorage.setItem('academy_watch_admin_key', 'synthetic-key')
    localStorage.setItem('academy_watch_display_name_confirmed', 'true')
    localStorage.setItem('academyWatch.playerOnboardingPromptDismissed.v1', 'true')
  })
  let pendingCount = 51
  const offsets = []
  await context.route('**/*', async route => {
    const url = new URL(route.request().url())
    if (!['127.0.0.1', 'localhost'].includes(url.hostname)) return route.abort()
    if (!url.pathname.startsWith('/api/')) return route.continue()
    if (url.pathname === '/api/auth/me') {
      return route.fulfill({ json: { email: 'synthetic@example.test', role: 'admin', is_admin: true, display_name: 'Synthetic Admin', display_name_confirmed: true } })
    }
    if (url.pathname === '/api/admin/auth-check') return route.fulfill({ json: { ok: true } })
    if (url.pathname.endsWith('/media/51/review')) {
      pendingCount = 50
      return route.fulfill({ json: { media: { id: 51, status: 'approved' } } })
    }
    if (url.pathname === '/api/admin/showcase/media') {
      const offset = Number(url.searchParams.get('offset'))
      const limit = Number(url.searchParams.get('limit'))
      expect(limit).toBe(50)
      const status = url.searchParams.get('status')
      offsets.push([status, offset])
      const total = status === 'pending' ? pendingCount : 1
      const media = Array.from({ length: Math.max(0, Math.min(limit, total - offset)) }, (_, index) => ({
        id: offset + index + 1, player_api_id: 5001, status, kind: 'photo',
      }))
      return route.fulfill({ json: { media, total, limit, offset } })
    }
    return route.fulfill({ json: {} })
  })
  await page.goto('/admin/showcase')
  await page.getByRole('tab', { name: 'Media', exact: true }).click()
  const previous = page.getByRole('button', { name: 'Previous', exact: true })
  const next = page.getByRole('button', { name: 'Next', exact: true })
  await expect(page.getByText('1–50 of 51 photos')).toBeVisible()
  await expect(previous).toBeDisabled()
  await next.click()
  await expect(page.getByText('51–51 of 51 photos')).toBeVisible()
  await expect(next).toBeDisabled()
  await previous.click()
  await expect(page.getByText('1–50 of 51 photos')).toBeVisible()
  await next.click()
  await page.getByRole('combobox').click()
  await page.getByRole('option', { name: 'Approved', exact: true }).click()
  await expect(page.getByText('1–1 of 1 photos')).toBeVisible()
  await expect(previous).toBeDisabled()
  expect(offsets.at(-1)).toEqual(['approved', 0])
  await page.getByRole('combobox').click()
  await page.getByRole('option', { name: 'Pending', exact: true }).click()
  await expect(page.getByText('1–50 of 51 photos')).toBeVisible()
  await next.click()
  await page.getByRole('button', { name: 'Approve', exact: true }).click()
  await expect(page.getByText('1–50 of 50 photos')).toBeVisible()
  await expect(previous).toBeDisabled()
  await expect(next).toBeDisabled()
  expect(offsets.slice(-2)).toEqual([['pending', 50], ['pending', 0]])
})
