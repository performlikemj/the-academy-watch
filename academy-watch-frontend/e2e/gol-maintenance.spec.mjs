/* global document, innerWidth */
import { test, expect } from '@playwright/test'
import fs from 'node:fs/promises'
import path from 'node:path'

const message = 'The assistant is under maintenance. Back soon.'

async function fixture(page, { billing = true, early = true, theme = 'light' } = {}) {
  const calls = []
  const errors = []
  const submissions = []
  let healthy = false
  const retryAfter = '60'
  page.on('pageerror', error => errors.push(error.message))
  await page.addInitScript(({ theme }) => {
    document.addEventListener('DOMContentLoaded', () => {
      const style = document.createElement('style')
      style.textContent = '[data-agentation-root] { display: none !important; }'
      document.head.append(style)
    })
    localStorage.clear()
    sessionStorage.clear()
    localStorage.setItem('theme', theme)
    localStorage.setItem('academy_watch_user_token', 'maintenance-test-token')
    localStorage.setItem('academy_watch_display_name', 'Test Scout')
    localStorage.setItem('academyWatch.playerOnboardingPromptDismissed.v1', 'true')
  }, { theme })
  await page.route('**/api/**', async route => {
    const p = new URL(route.request().url()).pathname
    calls.push(p)
    const reply = json => route.fulfill({ json })
    if (p === '/api/auth/me') return reply({ email: 'test@example.com', role: 'user', account_role: 'scout', user_id: 42, display_name: 'Test Scout', display_name_confirmed: true, scout_tier: 'free', scout_pro: { enabled: billing, features: { gol_chat: true, free_questions_remaining: 3, credit_balance: 7 } } })
    if (p === '/api/gol/suggestions') return reply(early && !healthy ? { suggestions: [], maintenance: true, error: 'maintenance', message, retryable: true, retry_after: Number(retryAfter) } : { suggestions: ['Compare academy pathways'] })
    if (p === '/api/gol/chat') {
      submissions.push(route.request().postDataJSON())
      return healthy
        ? route.fulfill({ contentType: 'text/event-stream', body: 'event: replace\ndata: {"content":"Recovered answer"}\n\nevent: done\ndata: {}\n\n' })
        : route.fulfill({ status: 503, headers: { 'Retry-After': retryAfter }, json: { error: 'maintenance', message, retryable: true } })
    }
    if (p === '/api/features') return reply({ contact_rail: false })
    if (p === '/api/billing/config') return reply({ enabled: billing, products: [], packs: [] })
    if (p === '/api/season-directory') return reply({ display_season: 2026, seasons: [2026] })
    if (p === '/api/journalists' || p === '/api/sponsors') return reply([])
    return reply({})
  })
  return { calls, errors, submissions, resume: () => { healthy = true } }
}

for (const width of [390, 1440]) {
  for (const theme of ['light', 'dark']) {
    for (const billing of [false, true]) {
      test(`maintenance switch for the assistant ${width} ${theme} billing ${billing}`, async ({ page }) => {
        await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
        const evidence = await fixture(page, { billing, theme })
        await page.goto('/settings')
        await page.evaluate(theme => document.documentElement.classList.toggle('dark', theme === 'dark'), theme)
        await page.waitForLoadState('networkidle')
        const featuresBefore = evidence.calls.filter(p => p === '/api/features').length
        await page.getByRole('button', { name: 'Open GOL Assistant chat' }).click()
        await expect(page.getByText(message, { exact: true })).toBeVisible()
        await expect(page.getByRole('status').filter({ hasText: message })).toBeVisible()
        await expect(page.getByRole('textbox', { name: 'Ask GOL' })).toHaveAccessibleDescription(message)
        await expect(page.getByRole('textbox', { name: 'Ask GOL' })).toBeDisabled()
        await expect(page.getByRole('button', { name: 'Send message' })).toBeDisabled()
        if (billing) await expect(page.getByText('3 free questions left', { exact: true })).toBeVisible()
        expect(evidence.calls.filter(p => p === '/api/gol/chat')).toHaveLength(0)
        expect(evidence.calls.filter(p => p === '/api/features')).toHaveLength(featuresBefore)
        expect(evidence.errors).toEqual([])
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
        if (process.env.GOLM_SCREENSHOTS) {
          await fs.mkdir(process.env.GOLM_SCREENSHOTS, { recursive: true })
          await page.waitForTimeout(400)
          await page.screenshot({ path: path.join(process.env.GOLM_SCREENSHOTS, `${width}-${theme}-billing-${billing}.png`), fullPage: true })
        }
      })
    }
  }
}

for (const billing of [false, true]) {
  test(`maintenance switch for the assistant answers a send with billing ${billing}`, async ({ page }) => {
    const evidence = await fixture(page, { billing, early: false })
    await page.goto('/settings')
    await page.getByRole('button', { name: 'Open GOL Assistant chat' }).click()
    await expect(page.getByRole('button', { name: 'Compare academy pathways' })).toBeVisible()
    await page.getByRole('textbox', { name: 'Ask GOL' }).fill('Compare pathways')
    await page.getByRole('button', { name: 'Send message' }).click()
    await expect(page.getByText(message, { exact: true })).toBeVisible()
    await expect(page.getByRole('status').filter({ hasText: message })).toBeVisible()
    await expect(page.getByRole('textbox', { name: 'Ask GOL' })).toHaveAccessibleDescription(message)
    await expect(page.getByRole('textbox', { name: 'Ask GOL' })).toBeDisabled()
    await expect(page.getByText('Compare pathways', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Retry', exact: true })).toHaveCount(0)
    if (billing) await expect(page.getByText('3 free questions left', { exact: true })).toBeVisible()
    expect(evidence.calls.filter(p => p === '/api/gol/chat')).toHaveLength(1)
    expect(evidence.errors).toEqual([])
    if (process.env.GOLM_SCREENSHOTS) {
      await fs.mkdir(process.env.GOLM_SCREENSHOTS, { recursive: true })
      await page.waitForTimeout(400)
      await page.screenshot({ path: path.join(process.env.GOLM_SCREENSHOTS, `submitted-billing-${billing}.png`), fullPage: true })
    }
  })
}


for (const width of [390, 1440]) {
  for (const recovery of ['reopen', 'control', 'clear']) {
    test(`operational control recovers on ${recovery} at ${width} without reload`, async ({ page }) => {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
      await page.clock.install()
      const evidence = await fixture(page, { early: false })
      await page.goto('/settings')
      await page.getByRole('button', { name: 'Open GOL Assistant chat' }).click()
      await expect(page.getByRole('button', { name: 'Compare academy pathways' })).toBeVisible()
      await page.getByRole('textbox', { name: 'Ask GOL' }).fill('Keep my question')
      await page.getByRole('button', { name: 'Send message' }).click()
      await expect(page.getByRole('status').filter({ hasText: message })).toBeVisible()
      const suggestionCount = evidence.calls.filter(p => p === '/api/gol/suggestions').length
      const featuresCount = evidence.calls.filter(p => p === '/api/features').length
      await expect(page.getByRole('button', { name: 'Please wait to check availability' })).toBeDisabled()
      evidence.resume()
      // Opening during Retry-After must not poll the endpoint.
      await page.getByRole('button', { name: 'Close', exact: true }).click()
      await page.getByRole('button', { name: 'Open GOL Assistant chat' }).click()
      await expect(page.getByRole('textbox', { name: 'Ask GOL' })).toBeDisabled()
      expect(evidence.calls.filter(p => p === '/api/gol/suggestions')).toHaveLength(suggestionCount)
      if (recovery === 'clear') {
        await page.getByRole('button', { name: 'Clear', exact: true }).click()
        await expect(page.getByText('Keep my question', { exact: true })).toHaveCount(0)
      } else {
        await page.clock.fastForward(61000)
        if (recovery === 'reopen') {
          await page.getByRole('button', { name: 'Close', exact: true }).click()
          await page.getByRole('button', { name: 'Open GOL Assistant chat' }).click()
        } else {
          await page.getByRole('button', { name: 'Check availability', exact: true }).click()
        }
        await expect(page.getByRole('textbox', { name: 'Ask GOL' })).toBeEnabled()
        await expect(page.getByText('Keep my question', { exact: true })).toBeVisible()
        await page.getByRole('button', { name: 'Retry', exact: true }).click()
        await expect(page.getByText('Recovered answer', { exact: true })).toBeVisible()
        expect(evidence.submissions).toHaveLength(2)
        expect(evidence.submissions[1]).toEqual(evidence.submissions[0])
      }
      await expect(page.getByRole('textbox', { name: 'Ask GOL' })).toBeEnabled()
      await expect(page.getByText(message, { exact: true })).toHaveCount(0)
      expect(evidence.calls.filter(p => p === '/api/gol/suggestions')).toHaveLength(suggestionCount + 1)
      expect(evidence.calls.filter(p => p === '/api/features')).toHaveLength(featuresCount)
      expect(evidence.errors).toEqual([])
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    })
  }
}

test('pre-send operational control retains the disabled draft and rechecks on reopening', async ({ page }) => {
  await page.clock.install()
  const evidence = await fixture(page, { early: true })
  await page.goto('/settings')
  // Delay the first read so a draft can be entered before the state arrives.
  let release
  const delay = new Promise(resolve => { release = resolve })
  await page.route('**/api/gol/suggestions', async route => {
    await delay
    await route.fallback()
  }, { times: 1 })
  await page.getByRole('button', { name: 'Open GOL Assistant chat' }).click()
  await page.getByRole('textbox', { name: 'Ask GOL' }).fill('Unsent draft')
  release()
  await expect(page.getByRole('status').filter({ hasText: message })).toBeVisible()
  await expect(page.getByRole('textbox', { name: 'Ask GOL' })).toHaveValue('Unsent draft')
  evidence.resume()
  await page.clock.fastForward(61000)
  await page.getByRole('button', { name: 'Close', exact: true }).click()
  await page.getByRole('button', { name: 'Open GOL Assistant chat' }).click()
  await expect(page.getByRole('textbox', { name: 'Ask GOL' })).toBeEnabled()
  expect(evidence.calls.filter(p => p === '/api/gol/suggestions')).toHaveLength(2)
  expect(evidence.calls.filter(p => p === '/api/gol/chat')).toHaveLength(0)
  expect(evidence.errors).toEqual([])
})
