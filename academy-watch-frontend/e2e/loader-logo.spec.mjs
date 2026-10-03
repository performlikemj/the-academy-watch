/* global document, createImageBitmap, OffscreenCanvas, getComputedStyle, MutationObserver */
import { test, expect } from '@playwright/test'
import fs from 'node:fs/promises'
import path from 'node:path'
import { CLEAT_MARK, CLUB_PALETTE, INK } from '../src/lib/cleat-loader.js'
import { CLEAT_CSS, LOADER_WIDTH, LOADER_HEIGHT } from '../src/lib/cleat-splash.js'
import { LOGO_SAMPLES } from '../src/lib/academy-watch-logo.js'

const output = process.env.N7_SCREENSHOTS
const SURFACES = { chalk: '#F3F0E8', night: '#0B0E0D', navy: '#1F3E73' }
const ICON = new URL('../../academy-watch-ios/AcademyWatch/Assets.xcassets/AppIcon.appiconset/AppIcon-1024.png', import.meta.url)
const hex = value => [1, 3, 5].map(i => parseInt(value.slice(i, i + 2), 16))
// Fully transparent colours serialise with or without their channels; alpha 0 is what matters.
const rgb = value => value.startsWith('rgba') ? /^rgba\(\d+, \d+, \d+, 0\)$/ : `rgb(${hex(value).join(', ')})`

async function save(page, name, options = {}) {
  if (!output) return
  await fs.mkdir(output, { recursive: true })
  await page.screenshot({ path: path.join(output, `${name}.png`), ...options })
}
async function pauseAt(page, time) {
  await page.locator('.cleat-shade,.cleat-trim').evaluateAll((elements, time) => {
    for (const el of elements) for (const animation of el.getAnimations()) { animation.pause(); animation.currentTime = time }
  }, time)
}
// Reads rendered pixels of the logo at the probe points (fractions of the logo box).
async function probe(page, points) {
  const mark = page.locator('.cleat-mark').first()
  const png = await mark.screenshot({ animations: 'allow' })
  return page.evaluate(async ({ data, points }) => {
    const bitmap = await createImageBitmap(new Blob([new Uint8Array(data)], { type: 'image/png' }))
    const context = new OffscreenCanvas(bitmap.width, bitmap.height).getContext('2d')
    context.drawImage(bitmap, 0, 0)
    const pixels = context.getImageData(0, 0, bitmap.width, bitmap.height).data
    const unique = new Set()
    for (let i = 0; i < pixels.length; i += 4) unique.add((pixels[i] << 16) | (pixels[i + 1] << 8) | pixels[i + 2])
    return {
      unique: unique.size,
      values: points.map(([x, y]) => {
        const at = (Math.floor(y * bitmap.height) * bitmap.width + Math.floor(x * bitmap.width)) * 4
        return [pixels[at], pixels[at + 1], pixels[at + 2]]
      }),
    }
  }, { data: [...png], points })
}
const near = (actual, expected, tolerance) => actual.every((channel, i) => Math.abs(channel - expected[i]) <= tolerance)
// The club colour, lifted by the icon's own highlights (white, up to ~35%).
const lit = (actual, body, tolerance) => [0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35].some(k => near(actual, body.map(c => c + (255 - c) * k), tolerance))

async function mountLoader(page, background, surface) {
  await page.route('**/src/main.jsx*', route => route.fulfill({ contentType: 'application/javascript', body: `
    import React from '/node_modules/.vite/deps/react.js';
    import ReactDOM from '/node_modules/.vite/deps/react-dom_client.js';
    import { CleatLoader } from '/src/components/CleatLoader.jsx';
    document.body.style.cssText = 'margin:0;background:${background}';
    ReactDOM.createRoot(document.getElementById('root')).render(React.createElement('main', {style:{display:'flex',minHeight:'100dvh',alignItems:'center',background:'${background}'}},
      React.createElement(CleatLoader, ${surface ? `{surface:'${surface}'}` : '{}'})));
  ` }))
  await page.goto('/')
  await expect(page.locator('main .cleat-loader .cleat-mark')).toBeVisible()
}

// Every phase: wing pixels stay the icon's white, the boot body takes the club colour,
// the icon's lace slots/seams stay dark ink, the outer keyline takes the trim colour
// (gold only for black-gold), and the art keeps its shading (not a flat fill).
async function assertDarkSlots(page, label) {
  const { values: slots } = await probe(page, LOGO_SAMPLES.slots)
  expect(slots.filter(pixel => near(pixel, hex(INK), 40)).length, `${label} lace slots ${JSON.stringify(slots)}`).toBeGreaterThanOrEqual(10)
}
async function assertPhases(page) {
  for (const [index, colour] of CLUB_PALETTE.entries()) {
    for (const time of [index * 1200, index * 1200 + 1100]) {
      await pauseAt(page, time)
      const { values: wing } = await probe(page, LOGO_SAMPLES.wing)
      for (const pixel of wing) expect(pixel.every(channel => channel >= 232), `${colour.name} @${time}ms wing ${pixel}`).toBe(true)
    }
    await pauseAt(page, index * 1200)
    await expect(page.locator('.cleat-shade')).toHaveCSS('background-color', rgb(colour.body))
    await expect(page.locator('.cleat-boot')).toHaveCSS('background-color', rgb(INK))
    await expect(page.locator('.cleat-trim')).toHaveCSS('background-color', rgb(colour.trim))
    const body = await probe(page, LOGO_SAMPLES.body)
    expect(body.values.filter(pixel => lit(pixel, hex(colour.body), 18)).length, `${colour.name} body ${JSON.stringify(body.values)}`).toBeGreaterThanOrEqual(10)
    await assertDarkSlots(page, colour.name)
    const { values: trim } = await probe(page, LOGO_SAMPLES.trim)
    const gold = trim.filter(pixel => near(pixel, hex('#CFAE62'), 60)).length
    if (colour.trim !== '#CFAE62') expect(gold, `${colour.name} keyline ${JSON.stringify(trim)}`).toBe(0)
    else expect(gold, `${colour.name} keyline ${JSON.stringify(trim)}`).toBeGreaterThanOrEqual(5)
    expect(body.unique, 'real shaded artwork, not a flat fill').toBeGreaterThan(400)
  }
}

test.describe('loader logo', () => {
  test('markup and CSS: real artwork layers, request-free, wing never animated', () => {
    expect(CLEAT_MARK).toContain('data-brand-logo="academy-watch-winged-boot"')
    for (const part of ['art', 'boot', 'shade', 'light', 'trim']) expect(CLEAT_MARK).toContain(`data-brand-part="${part}"`)
    expect(CLEAT_MARK).not.toMatch(/<svg|<path|<img|href=|src=/)
    expect([...CLEAT_CSS.matchAll(/url\(([^)]*)\)/g)].every(([, url]) => url.startsWith('data:image/webp;base64,'))).toBe(true)
    expect(CLEAT_CSS).not.toMatch(/\.cleat-(art|boot|light)\{[^}]*animation/)
  })

  for (const scale of [1, 2, 3]) {
    test.describe(`at ${scale}x`, () => {
      test.use({ deviceScaleFactor: scale })
      test(`lace slots stay dark in all six phases at ${scale}x`, async ({ page }) => {
        await mountLoader(page, SURFACES.chalk)
        for (const [index, colour] of CLUB_PALETTE.entries()) {
          for (const time of [index * 1200, index * 1200 + 1100]) {
            await pauseAt(page, time)
            await assertDarkSlots(page, `${colour.name} @${time}ms ${scale}x`)
          }
        }
      })
    })
  }

  test('React loaders reuse the splash stylesheet: one copy of the artwork in the page', async ({ page }) => {
    await mountLoader(page, SURFACES.chalk)
    const sheets = await page.evaluate(() => [...document.querySelectorAll('style')].filter(el => el.textContent.includes('.cleat-mark{')).length)
    expect(sheets).toBe(1)
  })

  for (const [name, background] of [['oklch', 'oklch(0.33 0.09 262)'], ['color-mix', 'color-mix(in oklab, #1F3E73 90%, transparent)'], ['rgb', '#1F3E73']]) {
    test(`dark ${name} panels are detected as night`, async ({ page }) => {
      await mountLoader(page, background)
      await expect(page.locator('main .cleat-loader')).toHaveAttribute('data-surface', 'night')
      await expect(page.locator('.cleat-mark')).toHaveCSS('filter', /drop-shadow/)
    })
  }

  test('a gradient panel is not guessed from the page behind it', async ({ page }) => {
    await mountLoader(page, 'linear-gradient(#1F3E73, #13294B)')
    await expect(page.locator('main .cleat-loader')).not.toHaveAttribute('data-surface', /./)
  })

  for (const width of [1440, 390]) for (const [surfaceName, background] of Object.entries(SURFACES)) {
    test(`six phases on ${surfaceName} at ${width}px: white wing, coloured shaded boot, still wings`, async ({ page }) => {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
      await mountLoader(page, background)
      // The loader works out its surface from the painted background (navy console included).
      await expect(page.locator('main .cleat-loader')).toHaveAttribute('data-surface', surfaceName === 'chalk' ? 'chalk' : 'night')
      await expect(page.locator('.cleat-mark')).toHaveCSS('width', `${LOADER_WIDTH}px`)
      await expect(page.locator('.cleat-mark')).toHaveCSS('height', `${LOADER_HEIGHT}px`)
      await expect(page.locator('.cleat-mark')).toHaveCSS('filter', surfaceName === 'chalk' ? 'none' : /drop-shadow/)
      expect(await page.locator('.cleat-art').evaluate(el => el.getAnimations().length)).toBe(0)
      expect(await page.locator('.cleat-mark span').evaluateAll(els => els.every(el => getComputedStyle(el).transform === 'none'))).toBe(true)
      await assertPhases(page)
    })
  }

  test('reduced motion is one still green frame with the white wing', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await mountLoader(page, SURFACES.chalk)
    expect(await page.locator('.cleat-mark span').evaluateAll(els => els.every(el => el.getAnimations().length === 0))).toBe(true)
    await expect(page.locator('.cleat-shade')).toHaveCSS('background-color', rgb(CLUB_PALETTE[0].body))
    const first = await page.locator('.cleat-mark').screenshot()
    await page.waitForTimeout(1500)
    expect((await page.locator('.cleat-mark').screenshot()).equals(first)).toBe(true)
    const { values: wing } = await probe(page, LOGO_SAMPLES.wing)
    for (const pixel of wing) expect(pixel.every(channel => channel >= 232)).toBe(true)
    await save(page, 'reduced-motion-still', { clip: await page.locator('.cleat-loader').boundingBox() })
  })

  test('dark theme over a chalk panel keeps an ink caption and no rim', async ({ page }) => {
    await page.addInitScript(() => document.documentElement.classList.add('dark'))
    await mountLoader(page, SURFACES.chalk)
    await expect(page.locator('main .cleat-loader')).toHaveAttribute('data-surface', 'chalk')
    await expect(page.locator('.cleat-caption')).toHaveCSS('color', 'rgb(14, 19, 17)')
    await expect(page.locator('.cleat-mark')).toHaveCSS('filter', 'none')
  })

  test('explicit surfaces win over detection', async ({ page }) => {
    await mountLoader(page, SURFACES.navy, 'chalk')
    await expect(page.locator('main .cleat-loader')).toHaveAttribute('data-surface', 'chalk')
    await expect(page.locator('.cleat-mark')).toHaveCSS('filter', 'none')
  })

  for (const width of [1440, 390]) {
    test(`boot splash is request-free and identical to the loader: ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
      const requests = []
      page.on('request', request => requests.push(request))
      await page.route('**/src/main.jsx*', route => route.abort())
      await page.route('**/src/index.css*', route => route.abort())
      await page.route(/fonts\.(googleapis|gstatic)\.com/, route => route.abort())
      await page.route('**/', async route => {
        const response = await route.fetch()
        await route.fulfill({ response, headers: { ...response.headers(), 'content-security-policy': "script-src 'self'; object-src 'none'" } })
      })
      await page.goto('/')
      await expect(page.getByRole('status', { name: 'Loading', exact: true })).toBeVisible()
      await expect(page.locator('[data-brand-logo]')).toHaveCount(1)
      const html = await page.content()
      expect(html).toContain(CLEAT_MARK)
      for (const [index, colour] of CLUB_PALETTE.entries()) {
        await pauseAt(page, index * 1200)
        await expect(page.locator('.cleat-shade')).toHaveCSS('background-color', rgb(colour.body))
        const { values: wing } = await probe(page, LOGO_SAMPLES.wing)
        for (const pixel of wing) expect(pixel.every(channel => channel >= 232)).toBe(true)
      }
      // Nothing the splash draws is fetched: no images, no logo assets.
      const fetched = requests.filter(request => request.resourceType() === 'image' && !/loan_army_assets\/favicon/.test(request.url()))
      expect(fetched.map(request => request.url())).toEqual([])
      expect(requests.filter(request => /\.webp|academy-watch-logo|LaunchBoot|AppIcon/.test(request.url()))).toEqual([])
      await page.emulateMedia({ reducedMotion: 'reduce' })
      expect(await page.locator('.cleat-mark span').evaluateAll(els => els.every(el => el.getAnimations().length === 0))).toBe(true)
    })
  }
})

// ---- Proof images (only with N7_SCREENSHOTS) --------------------------------------------
test.describe('loader proof', () => {
  test.skip(!output, 'Set N7_SCREENSHOTS to write proof images')

  async function sheet(page, scale) {
    const icon = `data:image/png;base64,${(await fs.readFile(ICON)).toString('base64')}`
    const frozen = index => CLEAT_MARK.replace(/class="cleat-(shade|trim)"/g, `$& style="animation-delay:-${index * 1200}ms;animation-play-state:paused"`)
    const cells = CLUB_PALETTE.map((colour, index) => `<figure><div class="cleat-loader" data-surface="SURFACE" style="min-height:0">${frozen(index)}</div><figcaption>${colour.name}</figcaption></figure>`).join('')
    const rows = Object.entries(SURFACES).map(([name, background]) => `<section style="background:${background};color:${name === 'chalk' ? '#0E1311' : '#F3F0E8'}"><h2>${name === 'navy' ? 'navy club console' : name}</h2><figure><img src="${icon}" width="144" height="144" alt=""><figcaption>app icon</figcaption></figure>${cells.replaceAll('SURFACE', name === 'chalk' ? 'chalk' : 'night')}</section>`).join('')
    await page.setViewportSize({ width: 1400, height: 700 })
    await page.setContent(`<style>${CLEAT_CSS}body{margin:0;font:12px 'Helvetica Neue',sans-serif}section{display:flex;align-items:center;gap:28px;padding:18px 24px}h2{width:96px;font-size:13px;margin:0}figure{margin:0;display:flex;flex-direction:column;align-items:center;gap:6px}figcaption{opacity:.8}.cleat-loader{width:auto}</style><h1 style="font-size:15px;margin:12px 24px">App icon (AppIcon-1024 scaled to 144 px) vs loader, every phase — rendered at ${scale}x</h1>${rows}`)
    return page.screenshot({ path: path.join(output, `contact-sheet-${scale}x.png`), fullPage: true })
  }

  for (const scale of [1, 3]) {
    test.describe(`at ${scale}x`, () => {
      test.use({ deviceScaleFactor: scale })
      test(`contact sheet ${scale}x`, async ({ page }) => { await sheet(page, scale) })
    })
  }

  test.describe('side by side', () => {
    test.use({ deviceScaleFactor: 2 })
    test('app icon vs loader, green phase, same boot size', async ({ page }) => {
      const icon = `data:image/png;base64,${(await fs.readFile(ICON)).toString('base64')}`
      // The icon crops 304 master px; the loader box spans 253 of them, so this size puts
      // both boots at the same on-screen size.
      const iconSize = Math.round(LOADER_WIDTH * 304 / 253 * 1.6)
      const loaderStyle = `transform:scale(1.6);transform-origin:center;margin:${LOADER_HEIGHT * 0.3}px ${LOADER_WIDTH * 0.3}px`
      await page.setViewportSize({ width: 880, height: 420 })
      await page.setContent(`<style>${CLEAT_CSS}body{margin:0;background:#9A9A9A;font:15px 'Helvetica Neue',sans-serif;color:#111}main{display:flex;gap:48px;align-items:center;justify-content:center;height:420px}figure{margin:0;display:flex;flex-direction:column;align-items:center;gap:14px}.cleat-loader{min-height:0;width:auto}.cleat-shade,.cleat-trim{animation-play-state:paused!important;animation-delay:0s!important}</style><main><figure><img src="${icon}" width="${iconSize}" height="${iconSize}" alt=""><figcaption>App icon</figcaption></figure><figure><div class="cleat-loader" data-surface="chalk" style="${loaderStyle}">${CLEAT_MARK}</div><figcaption>Web loader — green phase</figcaption></figure></main>`)
      await page.screenshot({ path: path.join(output, 'side-by-side-icon-vs-loader-green.png') })
    })
  })

  const pages = [
    ['home-first-load', '/', null],
    ['club-console', '/my-club', 'token'],
    ['player-page', '/players/1', null],
  ]
  for (const [name, url, auth] of pages) for (const width of [1440, 390]) for (const theme of ['light', 'dark']) {
    test(`in place: ${name} ${width} ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
      if (name === 'home-first-load') await page.route('**/src/main.jsx*', route => route.abort())
      // Hold every API call open so the real loading state stays on screen.
      await page.route('**/api/**', () => {})
      await page.addInitScript(({ auth, theme }) => {
        if (auth) localStorage.setItem('academy_watch_user_token', 'n7-proof-token')
        if (theme === 'dark') new MutationObserver(() => document.documentElement.classList.add('dark')).observe(document.documentElement, { attributes: true, childList: true, subtree: false })
      }, { auth, theme })
      await page.goto(url)
      if (theme === 'dark') await page.locator('html').evaluate(el => el.classList.add('dark'))
      await expect(page.locator('.cleat-loader .cleat-mark').first()).toBeVisible()
      await page.waitForTimeout(300)
      await pauseAt(page, 0)
      await save(page, `in-place-${name}-${width}-${theme}`)
    })
  }
})
