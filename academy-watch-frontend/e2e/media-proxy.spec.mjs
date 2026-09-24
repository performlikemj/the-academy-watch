import fs from 'node:fs'
import { test, expect } from '@playwright/test'

// Opt-in real-server test: fixture tokens and media belong to a throwaway DB.
const fixturePath = process.env.E2E_MEDIA_FIXTURE
const fixture = fixturePath ? JSON.parse(fs.readFileSync(fixturePath, 'utf8')) : {}
const artifacts = process.env.E2E_MEDIA_ARTIFACTS || '/tmp/media-proxy-work'
test.skip(!fixturePath, 'Requires an isolated media fixture and local backend')

async function authenticate(page, token, admin = false) {
  await page.addInitScript(({ token, admin }) => {
    localStorage.setItem('academy_watch_user_token', token)
    localStorage.setItem('academy_watch_is_admin', String(admin))
    localStorage.setItem('academy_watch_display_name', 'Synthetic Media Tester')
    localStorage.setItem('academy_watch_display_name_confirmed', 'true')
    localStorage.setItem('academyWatch.playerOnboardingPromptDismissed.v1', 'true')
    if (admin) localStorage.setItem('academy_watch_admin_key', 'media-proxy-throwaway-admin')
  }, { token, admin })
}

async function localRequestsOnly(context) {
  // This test never needs production, storage accounts, email or remote images.
  await context.route('**/*', route => {
    const host = new URL(route.request().url()).hostname
    return ['127.0.0.1', 'localhost'].includes(host) ? route.continue() : route.abort()
  })
}

test.beforeEach(async ({ context }) => localRequestsOnly(context))

test('real upload, admin approval and anonymous showcase image', async ({ page, browser, request }) => {
  await authenticate(page, fixture.owner_token)
  await page.goto(`/local-players/${fixture.local_player_id}`)
  await page.getByRole('button', { name: 'Add photo', exact: true }).click()
  await page.getByLabel('Photo', { exact: true }).setInputFiles(`${artifacts}/player.png`)
  const completed = page.waitForResponse(r => r.url().endsWith('/complete') && r.request().method() === 'POST')
  await page.getByRole('button', { name: 'Upload photo', exact: true }).click()
  const uploaded = await (await completed).json()
  expect(uploaded.media.status).toBe('pending')
  await page.screenshot({ path: `${artifacts}/shots/01-photo-pending.png`, fullPage: true })

  const adminContext = await browser.newContext()
  await localRequestsOnly(adminContext)
  const admin = await adminContext.newPage()
  await authenticate(admin, fixture.admin_token, true)
  await admin.goto('/admin/showcase')
  await admin.getByRole('tab', { name: 'Media', exact: true }).click()
  const row = admin.getByLabel(`Review note for photo ${uploaded.media.id}`).locator('../..')
  const moderated = admin.waitForResponse(r => r.url().endsWith(`/media/${uploaded.media.id}/review`) && r.request().method() === 'POST')
  await row.getByRole('button', { name: 'Approve', exact: true }).click()
  const approval = await (await moderated).json()
  expect(approval.media.public_url).toMatch(/^http:\/\/127\.0\.0\.1:5017\/api\/media\/published\/local-players\//)
  await admin.screenshot({ path: `${artifacts}/shots/02-admin-approved.png`, fullPage: true })
  await adminContext.close()

  const publicContext = await browser.newContext()
  await localRequestsOnly(publicContext)
  const publicPage = await publicContext.newPage()
  await publicPage.goto(`/local-players/${fixture.local_player_id}`)
  const image = publicPage.locator(`img[src="${approval.media.public_url}"]`)
  await expect(image).toBeVisible()
  await expect.poll(() => image.evaluate(img => img.complete && img.naturalWidth > 0)).toBe(true)
  expect(await image.getAttribute('src')).toBe(approval.media.public_url)
  const served = await request.get(approval.media.public_url)
  expect(served.headers()['content-type']).toBe('image/jpeg')
  expect(served.headers()['cache-control']).toBe('public, max-age=86400')
  expect(served.headers()['x-content-type-options']).toBe('nosniff')
  const head = await request.head(approval.media.public_url)
  expect(head.status()).toBe(200)
  expect(await head.body()).toHaveLength(0)
  expect((await request.get(approval.media.public_url, {
    headers: { 'If-None-Match': served.headers().etag },
  })).status()).toBe(304)
  await publicPage.screenshot({ path: `${artifacts}/shots/03-public-photo.png`, fullPage: true })
  await publicContext.close()
})

test('real club banner upload and replacement', async ({ page, request }) => {
  await authenticate(page, fixture.manager_token)
  await page.goto(`/my-club?program=${fixture.program_id}&view=branding`)
  const banner = page.locator('.ch-banner')
  const upload = async file => {
    const completed = page.waitForResponse(r => r.url().endsWith('/branding/banner/complete') && r.request().method() === 'POST')
    await page.getByLabel('Upload banner', { exact: true }).setInputFiles(`${artifacts}/${file}.png`)
    const response = await completed
    expect(response.status()).toBe(200)
    const { brand } = await response.json()
    expect(brand.banner_url).toContain('/api/media/published/club-banners/')
    await expect(banner).toHaveCSS('background-image', new RegExp(brand.banner_url.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')))
    await expect.poll(() => page.evaluate(async url => {
      const image = new globalThis.Image()
      image.src = url
      await image.decode()
      return image.naturalWidth
    }, brand.banner_url)).toBe(1200)
    return brand.banner_url
  }
  const oldUrl = await upload('banner')
  await page.screenshot({ path: `${artifacts}/shots/04-club-banner.png`, fullPage: true })
  const newUrl = await upload('replacement')
  expect(newUrl).not.toBe(oldUrl)
  expect((await request.get(oldUrl)).status()).toBe(404)
  expect((await request.get(newUrl)).status()).toBe(200)
  await page.screenshot({ path: `${artifacts}/shots/05-club-banner-replaced.png`, fullPage: true })
})
