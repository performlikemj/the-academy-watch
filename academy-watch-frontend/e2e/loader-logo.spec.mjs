/* global getComputedStyle */
import { test, expect } from '@playwright/test'
import fs from 'node:fs/promises'
import path from 'node:path'
import { CLEAT_SVG, CLEAT_CSS } from '../src/lib/cleat-loader.js'
import { LOGO_PATHS } from '../src/lib/academy-watch-logo.js'

const output = process.env.N6_SCREENSHOTS
const phases = ['green', 'claret', 'navy', 'black-gold', 'orange', 'sky']
const fills = ['rgb(15, 61, 46)', 'rgb(122, 20, 38)', 'rgb(31, 62, 115)', 'rgb(11, 14, 13)', 'rgb(227, 93, 24)', 'rgb(108, 172, 228)']
async function assertLogo(page) {
  for (const [part, geometry] of Object.entries(LOGO_PATHS)) {
    await expect(page.locator(`[data-brand-part="${part}"]`)).toHaveAttribute('d', geometry)
  }
  await expect(page.locator('svg')).toHaveAttribute('width', '144')
  await expect(page.locator('svg')).toHaveAttribute('height', '97')
}
async function assertWing(page, surface) {
  await expect(page.locator('.cleat-wing')).toHaveCSS('fill', 'rgb(255, 255, 255)')
  await expect(page.locator('.cleat-wing')).toHaveCSS('stroke', surface === 'night' ? 'none' : 'rgb(14, 19, 17)')
  expect(await page.locator('.cleat-wing').evaluate(el => el.getAnimations().length)).toBe(0)
}
async function shots(page, name) {
  if (!output) return
  await fs.mkdir(output, { recursive: true })
  await page.screenshot({ path: path.join(output, `${name}.png`), fullPage: true })
  // Native CSS-pixel size, never enlarged: useful for judging the chalk wing contour.
  await page.locator('svg').screenshot({ path: path.join(output, `${name}-1x.png`) })
}
async function pauseAt(page, time) {
  await page.locator('.cleat-body,.cleat-accent').evaluateAll((elements, time) => {
    for (const el of elements) for (const animation of el.getAnimations()) { animation.pause(); animation.currentTime = time }
  }, time)
}
async function assertPhase(page, surface, index) {
  await expect(page.locator('.cleat-body')).toHaveCSS('fill', fills[index])
  await expect(page.locator('.cleat-accent')).toHaveCSS('fill', index === 3 ? 'rgb(207, 174, 98)' : fills[index])
  await assertWing(page, surface)
  expect(await page.locator('svg path').evaluateAll(elements => elements.every(el => getComputedStyle(el).transform === 'none'))).toBe(true)
}
async function mountLoader(page, surface) {
  await page.route('**/src/main.jsx*', route => route.fulfill({ contentType: 'application/javascript', body: `
    import React from '/node_modules/.vite/deps/react.js';
    import ReactDOM from '/node_modules/.vite/deps/react-dom_client.js';
    import { CleatLoader } from '/src/components/CleatLoader.jsx';
    document.body.style.cssText = 'margin:0;background:${surface === 'night' ? '#0B0E0D' : '#F3F0E8'}';
    ReactDOM.createRoot(document.getElementById('root')).render(React.createElement('main', {style:{display:'flex',minHeight:'100dvh',alignItems:'center'}},
      React.createElement(CleatLoader, {surface:'${surface}'})));
  ` }))
  await page.goto('/')
  await expect(page.locator('.cleat-loader svg')).toBeVisible()
}

for (const width of [1440, 390]) for (const surface of ['chalk', 'night']) {
  const size = width === 390 ? 'phone' : 'desktop'
  test(`brand geometry, six phases and white still wing: ${surface} ${size}`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
    await mountLoader(page, surface)
    await assertLogo(page)
    for (const [index, phase] of phases.entries()) {
      await pauseAt(page, index * 1200)
      await assertPhase(page, surface, index)
      await shots(page, `logo-${surface}-${size}-${phase}`)
      // Theme ancestry must not alter an explicitly selected loader surface.
      await page.locator('html').evaluate(el => el.classList.add('dark'))
      await assertWing(page, surface)
      await page.locator('html').evaluate(el => el.classList.remove('dark'))
      // Check the easing midpoint as well as the six colour holds.
      await pauseAt(page, index * 1200 + 1100)
      await assertWing(page, surface)
    }
    await page.emulateMedia({ reducedMotion: 'reduce' })
    expect(await page.locator('svg path').evaluateAll(elements => elements.every(el => el.getAnimations().length === 0))).toBe(true)
    await assertPhase(page, surface, 0)
    await shots(page, `logo-${surface}-${size}-reduced`)
  })
  test(`request-free boot splash under self-only scripts: ${surface} ${size}`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
    await page.route('**/src/main.jsx*', route => route.abort())
    await page.route('**/src/index.css*', route => route.abort())
    await page.route('**/', async route => {
      const response = await route.fetch()
      const html = await response.text()
      await route.fulfill({ response, headers: { ...response.headers(), 'content-security-policy': "script-src 'self'; object-src 'none'" }, body: surface === 'night' ? html.replace('<html lang="en">', '<html lang="en" class="dark">').replaceAll('background:#F3F0E8', 'background:#0B0E0D') : html })
    })
    await page.goto('/')
    await expect(page.getByRole('status', { name: 'Loading', exact: true })).toBeVisible()
    await expect(page.locator('[data-brand-logo]')).toHaveCount(1)
    await assertLogo(page)
    for (const [index, phase] of phases.entries()) {
      await pauseAt(page, index * 1200)
      await assertPhase(page, surface, index)
      await shots(page, `splash-${surface}-${size}-${phase}`)
    }
    await page.emulateMedia({ reducedMotion: 'reduce' })
    expect(await page.locator('svg path').evaluateAll(elements => elements.every(el => el.getAnimations().length === 0))).toBe(true)
    await assertPhase(page, surface, 0)
    await shots(page, `splash-${surface}-${size}-reduced`)
  })
}

test('implicit loader surfaces follow the light and dark theme with white wings', async ({ page }) => {
  await mountLoader(page, 'chalk')
  await page.locator('.cleat-loader').evaluate(el => el.removeAttribute('data-surface'))
  for (const dark of [false, true]) {
    await page.locator('html').evaluate((el, dark) => el.classList.toggle('dark', dark), dark)
    for (const [index] of phases.entries()) {
      await pauseAt(page, index * 1200)
      await assertWing(page, dark ? 'night' : 'chalk')
    }
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await assertPhase(page, dark ? 'night' : 'chalk', 0)
    await page.emulateMedia({ reducedMotion: 'no-preference' })
  }
})

test('render exact brand paths at 600px for independent numeric proof', async ({ page }) => {
  test.skip(!output, 'Set N6_SCREENSHOTS to save proof inputs')
  await fs.mkdir(output, { recursive: true })
  const svg = CLEAT_SVG.replace('viewBox="54 104 490 330" width="144" height="97"', 'viewBox="0 0 600 600" width="600" height="600"')
  await fs.writeFile(path.join(output, 'logo-600.svg'), svg)
  await page.setViewportSize({ width: 600, height: 600 })
  // Keep the accepted white-ink geometry proof baseline: body contour retained;
  // exclude the new light-only ink wing contour from the silhouette measurement.
  await page.setContent(`<style>${CLEAT_CSS}body{margin:0;background:transparent}svg{display:block;color:white}svg path{animation:none!important;fill:white!important}.cleat-wing{stroke:none!important}</style>${svg}`)
  await page.screenshot({ path: path.join(output, 'logo-600.png'), omitBackground: true })
})
