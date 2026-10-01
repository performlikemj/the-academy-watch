/* global document, innerWidth */
import { expect, test } from '@playwright/test'

test.describe.configure({ mode: 'serial' })
for (const width of [1440, 390]) {
  test(`real app scoped save and refusal-only neutral 429 at ${width}px`, async ({ page, request }) => {
    test.skip(process.env.E2E_UXM2F3_REAL !== 'true', 'Requires foreground serve_uxm2f3_briefs.py')
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
    await expect.poll(async () => (await request.get(`/api/__uxm2f3-fixture?width=${width}`)).status()).toBe(200)
    const metadata = await (await request.get(`/api/__uxm2f3-fixture?width=${width}`)).json()
    const { program_id: pid, member_id: mid, coach_token: token } = metadata
    const headers = { Authorization: `Bearer ${token}` }
    const url = `/api/club/${pid}/roster/${mid}/brief`
    await page.addInitScript(token => {
      localStorage.setItem('academy_watch_user_token', token)
      localStorage.setItem('academyWatch.playerOnboardingPromptDismissed.v1', 'true')
    }, token)
    // The only stub is a local HTML harness. API calls, role reads and saves
    // reach src.main.app, including its real limiter and global error handler.
    await page.route('**/__uxm2f3-real', route => route.fulfill({ contentType: 'text/html', body: `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">
      import RefreshRuntime from '/@react-refresh'; RefreshRuntime.injectIntoGlobalHook(window); window.$RefreshReg$ = () => {}; window.$RefreshSig$ = () => type => type; window.__vite_plugin_react_preamble_installed__ = true;
      await import('/@vite/client');
      const React = (await import('/node_modules/.vite/deps/react.js')).default;
      const {createRoot} = (await import('/node_modules/.vite/deps/react-dom_client.js')).default;
      const {APIService} = await import('/src/lib/api.js');
      const {PlayerPage} = await import('/src/pages/club-console/PlayerPage.jsx');
      await import('/src/index.css');
      await import('/src/App.css');
      await import('/src/pages/club-console/club-home.css');
      const {clubSurfaceColors} = await import('/src/pages/club-console/club-colors.js');
      APIService.userToken = ${JSON.stringify(token)};
      const roster = await APIService.getClubRoster(${pid});
      const access = (await APIService.request('/club/${pid}/access/me')).access;
      const squads = (await APIService.request('/club/${pid}/squads')).squads;
      const root = createRoot(document.getElementById('root'));
      root.render(React.createElement('div', {className:'club-home',style:{gridTemplateColumns:'minmax(0,1fr)','--club-primary':'#0F3D2E','--club-accent':'#CFAE62',...clubSurfaceColors('#0F3D2E','#CFAE62')}}, React.createElement(PlayerPage, {access, program:roster.program, memberId:${mid}, squads, members:roster.members, onReload:()=>{}, onAccessDenied:()=>{}, onClub:()=>{}, onSquad:()=>{}, onScouts:()=>{}})));
    </script></body></html>` }))
    await page.goto('/__uxm2f3-real')
    await page.getByRole('button', { name: 'Edit brief', exact: true }).click({ timeout: 10000 }).catch(error => { expect(errors).toEqual([]); throw error })
    const textbox = page.getByRole('textbox', { name: 'Coach brief', exact: true })
    await textbox.fill('Brannock scans\nCheck shoulders')
    const saved = page.waitForResponse(r => r.url().endsWith(`/roster/${mid}/brief`) && r.request().method() === 'PUT')
    await page.getByRole('button', { name: 'Save brief', exact: true }).click()
    expect((await saved).status()).toBe(200)
    const after = await (await request.get(`/api/__uxm2f3-fixture?width=${width}`)).json()
    expect(after.worker_lines).toEqual(['Check shoulders'])
    await expect(page.locator('.ch-brief-lines')).toContainText('Brannock scans')
    if (process.env.E2E_UXM2_SHOTS) await page.screenshot({ path: `${process.env.E2E_UXM2_SHOTS}/real-hidden-save-${width}.png`, fullPage: true })
    // Each viewport uses a separate scoped account with the same grant.
    for (let index = 0; index < 20; index++) {
      expect((await request.put(url, { headers, data: { body: 'Check shoulders' } })).status()).toBe(200)
      expect((await request.put(url, { headers, data: { body: 'Known scans' } })).status()).toBe(422)
    }
    await page.getByRole('button', { name: 'Edit brief', exact: true }).click()
    await textbox.fill('Known scans')
    const limited = page.waitForResponse(r => r.url().endsWith(`/roster/${mid}/brief`) && r.request().method() === 'PUT')
    await page.getByRole('button', { name: 'Save brief', exact: true }).click()
    const response = await limited
    expect(response.status()).toBe(429)
    expect(await response.json()).toEqual({ error: 'Too many brief updates. Try again later.' })
    expect(response.headers()['cache-control']).toBe('private, no-store')
    expect(Number(response.headers()['retry-after'])).toBeGreaterThan(0)
    await expect(page.getByText('Too many brief updates. Try again later.', { exact: true })).toBeVisible()
    await expect(textbox).toHaveValue('Known scans')
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
    if (process.env.E2E_UXM2_SHOTS) await page.screenshot({ path: `${process.env.E2E_UXM2_SHOTS}/real-429-${width}.png`, fullPage: true })
    expect(errors).toEqual([])
  })
}
