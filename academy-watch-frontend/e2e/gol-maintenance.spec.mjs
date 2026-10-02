/* global document, innerWidth */
import { test, expect } from '@playwright/test'
import fs from 'node:fs/promises'
import path from 'node:path'

const message = 'The assistant is under maintenance. Back soon.'

async function fixture(page, { billing = true, early = true, theme = 'light' } = {}) {
  const calls = []
  const errors = []
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
    if (p === '/api/gol/suggestions') return reply(early ? { suggestions: [], maintenance: true, error: 'maintenance', message, retryable: true } : { suggestions: ['Compare academy pathways'] })
    if (p === '/api/gol/chat') return route.fulfill({ status: 503, headers: { 'Retry-After': '60' }, json: { error: 'maintenance', message, retryable: true } })
    if (p === '/api/features') return reply({ contact_rail: false })
    if (p === '/api/billing/config') return reply({ enabled: billing, products: [], packs: [] })
    if (p === '/api/season-directory') return reply({ display_season: 2026, seasons: [2026] })
    if (p === '/api/journalists' || p === '/api/sponsors') return reply([])
    return reply({})
  })
  return { calls, errors }
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
        await expect(page.getByRole('textbox', { name: 'Ask GOL' })).toBeDisabled()
        await expect(page.getByRole('button', { name: 'Send message' })).toBeDisabled()
        if (billing) await expect(page.getByText('3 free questions left', { exact: true })).toBeVisible()
        expect(evidence.calls.filter(p => p === '/api/gol/chat')).toHaveLength(0)
        expect(evidence.calls.filter(p => p === '/api/features')).toHaveLength(featuresBefore)
        expect(evidence.errors).toEqual([])
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
        if (process.env.GOLM_SCREENSHOTS) {
          await fs.mkdir(process.env.GOLM_SCREENSHOTS, { recursive: true })
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
    await expect(page.getByRole('textbox', { name: 'Ask GOL' })).toBeDisabled()
    await expect(page.getByText('Compare pathways', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Retry', exact: true })).toHaveCount(0)
    if (billing) await expect(page.getByText('3 free questions left', { exact: true })).toBeVisible()
    expect(evidence.calls.filter(p => p === '/api/gol/chat')).toHaveLength(1)
    expect(evidence.errors).toEqual([])
  })
}
