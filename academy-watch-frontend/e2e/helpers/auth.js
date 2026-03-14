import { expect } from '@playwright/test'
import { waitForEmailToken } from './db.js'

export async function loginWithCode(page, email, dbClient, { displayName = 'E2E User' } = {}) {
  await page.goto('/settings')
  const signInButton = page.getByRole('button', { name: /^Sign in$/i })
  const isSignedOut = await signInButton.isVisible().catch(() => false)
  if (!isSignedOut) {
    const logOutButton = page.getByRole('button', { name: /Log Out/i })
    if (await logOutButton.isVisible().catch(() => false)) {
      await logOutButton.click()
    } else {
      await page.evaluate(() => {
        localStorage.removeItem('academy_watch_user_token')
      })
      await page.reload()
    }
    await expect(signInButton).toBeVisible()
  }
  await signInButton.click()

  await page.getByLabel('Email').fill(email)
  await page.getByRole('button', { name: /send login code/i }).click()

  const code = await waitForEmailToken(dbClient, email, 'login')

  await page.getByLabel('Verification code').fill(code)
  await page.getByRole('button', { name: /verify & sign in/i }).click()

  // If display name prompt appears, set it.
  const displayNameInput = page.locator('#display-name')
  if (await displayNameInput.isVisible().catch(() => false)) {
    await displayNameInput.fill(displayName)
    await page.getByRole('button', { name: /^Save$/i }).click()
  }

  const closeButton = page.getByRole('button', { name: /^Close$/i }).filter({ hasText: /^Close$/i })
  await closeButton.first().click()

  await expect.poll(async () => page.evaluate(() => localStorage.getItem('academy_watch_user_token'))).not.toBeNull()
}

export async function setAdminKey(page, adminKey) {
  await page.evaluate((key) => {
    localStorage.setItem('academy_watch_admin_key', key)
  }, adminKey)
}

export async function getUserToken(page) {
  return page.evaluate(() => localStorage.getItem('academy_watch_user_token'))
}
