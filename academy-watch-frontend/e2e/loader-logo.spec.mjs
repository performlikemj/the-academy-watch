/* global window, getComputedStyle */
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
    for (const element of await page.locator(`[data-brand-part="${part}"]`).all()) await expect(element).toHaveAttribute('d', geometry)
  }
  expect(await page.locator('svg').evaluateAll(elements => elements.every(el => !el.innerHTML.includes('M20 47 Q20')))).toBe(true)
}
async function shots(page, name) {
  if (!output) return
  await fs.mkdir(output, { recursive: true })
  await page.screenshot({ path: path.join(output, `${name}-AB.png`), fullPage: true })
  for (const variant of ['A', 'B']) await page.locator(`[data-variant="${variant}"]`).screenshot({ path: path.join(output, `${name}-${variant}.png`) })
}
async function mountVariants(page, surface) {
  await page.route('**/src/main.jsx*', route => route.fulfill({ contentType: 'application/javascript', body: `
    import React from '/node_modules/.vite/deps/react.js';
    import ReactDOM from '/node_modules/.vite/deps/react-dom_client.js';
    import { CleatLoader } from '/src/components/CleatLoader.jsx';
    import { logoSvg } from '/src/lib/cleat-loader.js';
    window.n6SvgB = logoSvg('B');
    document.body.style.cssText = 'margin:0;background:${surface === 'night' ? '#0B0E0D' : '#F3F0E8'};color:${surface === 'night' ? '#F3F0E8' : '#0E1311'}';
    ReactDOM.createRoot(document.getElementById('root')).render(React.createElement('main', {style:{display:'flex',minHeight:'100dvh',alignItems:'center'}},
      ...['A','B'].map(variant => React.createElement('section', {'data-variant':variant,style:{width:'50%',textAlign:'center'}},
        React.createElement('p', {style:{font:'11px monospace',letterSpacing:'.08em'}},variant === 'A' ? 'A · NEUTRAL WING' : 'B · CLUB WING'),
        React.createElement(CleatLoader, {surface:'${surface}'})))));
  ` }))
  await page.goto('/')
  await expect(page.locator('[data-variant="B"] svg')).toBeVisible()
  await page.locator('[data-variant="B"] svg').evaluate(el => { el.outerHTML = window.n6SvgB })
}

for (const width of [1440, 390]) for (const surface of ['chalk', 'night']) {
  const size = width === 390 ? 'phone' : 'desktop'
  test(`brand geometry, six phases and still variants: ${surface} ${size}`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
    await mountVariants(page, surface)
    await assertLogo(page)
    const neutral = surface === 'night' ? 'rgb(243, 240, 232)' : 'rgb(14, 19, 17)'
    for (const [index, phase] of phases.entries()) {
      await page.locator('.cleat-body,.cleat-accent').evaluateAll((elements, time) => {
        for (const el of elements) for (const animation of el.getAnimations()) { animation.pause(); animation.currentTime = time }
      }, index * 1200)
      for (const el of await page.locator('[data-brand-part="body"]').all()) await expect(el).toHaveCSS('fill', fills[index])
      await expect(page.locator('[data-variant="A"] .cleat-wing')).toHaveCSS('fill', neutral)
      await expect(page.locator('[data-variant="B"] .cleat-wing')).toHaveCSS('fill', fills[index])
      for (const el of await page.locator('.cleat-accent').all()) await expect(el).toHaveCSS('fill', index === 3 ? 'rgb(207, 174, 98)' : fills[index])
      expect(await page.locator('svg path').evaluateAll(elements => elements.every(el => getComputedStyle(el).transform === 'none'))).toBe(true)
      await shots(page, `logo-${surface}-${size}-${phase}`)
    }
    await page.emulateMedia({ reducedMotion: 'reduce' })
    expect(await page.locator('svg path').evaluateAll(elements => elements.every(el => el.getAnimations().length === 0))).toBe(true)
    await expect(page.locator('[data-variant="A"] .cleat-body')).toHaveCSS('fill', fills[0])
    await expect(page.locator('[data-variant="A"] .cleat-wing')).toHaveCSS('fill', neutral)
    await expect(page.locator('[data-variant="B"] .cleat-wing')).toHaveCSS('fill', fills[0])
    await shots(page, `logo-${surface}-${size}-reduced`)
  })
  test(`request-free boot splash under self-only scripts: ${surface} ${size}`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
    await page.emulateMedia({ reducedMotion: 'reduce' })
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
    expect(await page.locator('svg path').evaluateAll(elements => elements.every(el => el.getAnimations().length === 0))).toBe(true)
    if (output) await page.screenshot({ path: path.join(output, `splash-${surface}-${size}-reduced.png`), fullPage: true })
  })
}

test('render exact brand paths at 600px for independent numeric proof', async ({ page }) => {
  test.skip(!output, 'Set N6_SCREENSHOTS to save proof inputs')
  const svg = CLEAT_SVG.replace('viewBox="54 104 490 330" width="144" height="97"', 'viewBox="0 0 600 600" width="600" height="600"')
  await fs.writeFile(path.join(output, 'logo-600.svg'), svg)
  await page.setViewportSize({ width: 600, height: 600 })
  // Neutral white reproduces the source ink. Geometry and production contour stroke are unchanged.
  await page.setContent(`<style>${CLEAT_CSS}body{margin:0;background:transparent}svg{display:block;color:white}svg path{animation:none!important;fill:white!important}</style>${svg}`)
  await page.screenshot({ path: path.join(output, 'logo-600.png'), omitBackground: true })
})
