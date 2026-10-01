/* global document, innerWidth, window */
import { expect, test } from '@playwright/test'
import fs from 'node:fs/promises'
import path from 'node:path'

const oid = 'aca5d722-e50d-571e-aef8-51e214ec69ee'
const ageOid = '3afc7728-b628-5778-84db-eb50b4a1c9ea'
const localId = 260932641, programId = 126905366
const personasPath = process.env.UXB_PERSONAS, shots = process.env.UXB_SCREENSHOTS
async function signIn(page, role) {
  const personas = JSON.parse(await fs.readFile(personasPath, 'utf8'))
  await page.addInitScript(({ token, name }) => {
    localStorage.setItem('academy_watch_user_token', token)
    localStorage.setItem('academyWatch.playerOnboardingPromptDismissed.v1', 'true')
    localStorage.setItem('academy_watch_display_name', name)
    localStorage.setItem('academy_watch_display_name_confirmed', 'true')
  }, personas[role])
}
async function capture(page, name, size) {
  if (!shots) return
  await fs.mkdir(shots, { recursive: true })
  await page.evaluate(() => document.fonts.ready)
  await page.screenshot({ path: path.join(shots, `${name}-${size}.png`), fullPage: !name.startsWith('account-menu') })
  await page.screenshot({ path: path.join(shots, `${name}-${size}-viewport.png`) })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
}
const program = {id:7,name:'Synthetic UXB',slug:'synthetic-uxb',brand:{},provenance:{label:'Self-reported'},updates:[]}
for (const [width, height, size] of [[1440,900,'desktop'],[390,844,'mobile']]) {
  test.describe(`UXB ${size}`, () => {
    test.use({ viewport: { width, height } })
    test('signed-out player home makes no authenticated requests or 401s', async ({ page }) => {
      const privateRequests = [], unauthorized = []
      page.on('response', r => { if (r.status() === 401) unauthorized.push(new URL(r.url()).pathname) })
      await page.route('**/api/**', route => {
        const p = new URL(route.request().url()).pathname
        if (p.startsWith('/api/me/') || route.request().headers().authorization) { privateRequests.push(p); return route.fulfill({status:401,json:{error:'Sign in required'}}) }
        if (p === '/api/opportunities/features') return route.fulfill({json:{opportunities:true,applications:true}})
        if (p === '/api/meta/data-mode') return route.fulfill({json:{api_football_frozen:true}})
        return route.fulfill({json:{}})
      })
      await page.goto('/onboarding/player')
      await expect(page.getByText('Sign in to see your applications and next steps.')).toBeVisible()
      await expect(page.getByRole('heading', {name:'Are you a player?'})).toBeVisible()
      await page.waitForLoadState('networkidle')
      expect(privateRequests).toEqual([]); expect(unauthorized).toEqual([])
      await capture(page,'player-home-signed-out',size)
    })
    test('flags off preserve discovery and teasers without business API calls', async ({ page }) => {
      const calls = []
      await page.addInitScript(() => { localStorage.setItem('academy_watch_user_token','uxb-off-parity'); localStorage.setItem('academyWatch.playerOnboardingPromptDismissed.v1','true') })
      await page.route('**/api/**', route => {
        const p = new URL(route.request().url()).pathname
        if (p === '/api/opportunities/features') return route.fulfill({status:404,json:{error:'Not found'}})
        if (p.startsWith('/api/me/application') || p === '/api/opportunities') calls.push(p)
        if (p === '/api/programs/synthetic-uxb') return route.fulfill({json:{program}})
        if (p === '/api/meta/data-mode') return route.fulfill({json:{api_football_frozen:true}})
        return route.fulfill({json:{}})
      })
      await page.goto('/onboarding/player')
      await expect(page.getByRole('heading',{name:'Are you a player?'})).toBeVisible()
      await expect(page.getByRole('heading',{name:'Your next chapter.'})).toBeVisible()
      await page.goto('/programs/synthetic-uxb')
      await expect(page.getByRole('heading',{name:'Straight from the club, soon.'})).toBeVisible()
      expect(calls).toEqual([])
      await page.goto('/clubs')
      await expect(page.getByText('Find a club · coming soon')).toBeVisible()
    })
    test('club has a calm empty state with opportunities enabled', async ({ page }) => {
      await page.route('**/api/**', route => {
        const p=new URL(route.request().url()).pathname
        if(p==='/api/opportunities/features') return route.fulfill({json:{opportunities:true,applications:false}})
        if(p==='/api/programs/synthetic-uxb') return route.fulfill({json:{program}})
        if(p==='/api/opportunities') return route.fulfill({json:{opportunities:[],has_more:false}})
        return route.fulfill({json:{}})
      })
      await page.goto('/programs/synthetic-uxb')
      await expect(page.getByText('No open opportunities at this club right now.')).toBeVisible()
      await expect(page.getByText('Straight from the club, soon.')).toHaveCount(0)
      await capture(page,'club-opportunities-empty',size)
    })
    test('location and text replace each other, including late geolocation', async ({ page, context }) => {
      await context.grantPermissions(['geolocation']); await context.setGeolocation({ latitude:50.8,longitude:-1.1 })
      const searches=[]
      await page.route('**/api/**',route=>{
        const p=new URL(route.request().url()).pathname
        if(p==='/api/features') return route.fulfill({json:{club_directory:true}})
        if(p==='/api/club-directory/search') { searches.push(route.request().postDataJSON()); return route.fulfill({json:{clubs:[],total:0,has_more:false}}) }
        return route.fulfill({json:{}})
      })
      await page.goto('/clubs')
      await page.getByLabel('Near',{exact:true}).fill('Quillmere'); await page.getByRole('search').getByRole('button',{name:'Search',exact:true}).click()
      await expect(page.getByText('Searching for “Quillmere”')).toBeVisible()
      await expect.poll(()=>searches.at(-1)?.q).toBe('Quillmere')
      await page.getByRole('button',{name:'Use my location',exact:true}).click()
      await expect(page.getByText('Nearest first, from roughly where you are.')).toBeVisible()
      await expect(page.getByLabel('Near',{exact:true})).toHaveValue('')
      await expect.poll(()=>searches.at(-1)?.lat).toBe(50.8)
      expect(searches.at(-1)).not.toHaveProperty('q'); await capture(page,'directory-location',size)
      await page.getByLabel('Near',{exact:true}).fill('Thrandby'); await page.getByRole('search').getByRole('button',{name:'Search',exact:true}).click()
      await expect.poll(()=>searches.at(-1)?.q).toBe('Thrandby'); expect(searches.at(-1)).not.toHaveProperty('lat')
      await expect(page.getByText('Nearest first, from roughly where you are.')).toHaveCount(0); await capture(page,'directory-text',size)
      await page.evaluate(()=> { navigator.geolocation.getCurrentPosition = callback => { window.uxbGeoCallback=callback } })
      await page.getByRole('button',{name:'Use my location',exact:true}).click(); await page.getByLabel('Near',{exact:true}).fill('Keep this text')
      await page.evaluate(()=>window.uxbGeoCallback({coords:{latitude:1,longitude:2}}))
      await expect(page.getByLabel('Near',{exact:true})).toHaveValue('Keep this text'); await expect(page.getByText('Nearest first, from roughly where you are.')).toHaveCount(0)
    })
    test('real backend: directory replaces text with location and back', async ({ page, context }) => {
      test.skip(!personasPath,'UXB_PERSONAS enables disposable aw_uxb HTTP checks')
      await context.grantPermissions(['geolocation']); await context.setGeolocation({latitude:52.874,longitude:0.046})
      await page.goto('/clubs')
      await page.getByLabel('Near',{exact:true}).fill('Quillmere'); await page.getByRole('search').getByRole('button',{name:'Search',exact:true}).click()
      await expect(page.getByTestId('club-count')).toHaveText('1 verified club')
      await page.getByRole('button',{name:'Use my location',exact:true}).click()
      await expect(page.getByLabel('Near',{exact:true})).toHaveValue('')
      await expect(page.getByTestId('club-count')).toHaveText('2 verified clubs')
      await expect(page.getByText('Nearest first, from roughly where you are.')).toBeVisible()
      await capture(page,'directory-location-real',size)
      await page.getByLabel('Near',{exact:true}).fill('Quillmere'); await page.getByRole('search').getByRole('button',{name:'Search',exact:true}).click()
      await expect(page.getByTestId('club-count')).toHaveText('1 verified club')
      await expect(page.getByText('Nearest first, from roughly where you are.')).toHaveCount(0)
      await capture(page,'directory-text-real',size)
    })
    test('real backend: club opportunity links contain no applicants', async ({ page }) => {
      test.skip(!personasPath,'UXB_PERSONAS enables disposable aw_uxb HTTP checks')
      const unauthorized=[];page.on('response',r=>{if(r.status()===401) unauthorized.push(r.url())})
      await page.goto('/programs/quillmere-athletic')
      await expect(page.getByRole('link',{name:/Open training night with the Reserves/})).toBeVisible(); await expect(page.getByText('Straight from the club, soon.')).toHaveCount(0)
      const data=await (await page.request.get(`/api/opportunities?program_id=${programId}`)).json()
      for(const row of data.opportunities) for(const key of ['application','claim_id','applicant_name','application_count']) expect(row).not.toHaveProperty(key)
      expect(unauthorized).toEqual([]); await capture(page,'club-opportunities',size)
    })
    test('real backend: approved player home, profile summary and account entries', async ({ page }) => {
      test.skip(!personasPath,'UXB_PERSONAS enables disposable aw_uxb HTTP checks')
      await signIn(page,'player'); await page.goto('/onboarding/player')
      await expect(page.getByRole('heading',{name:'Your next step.'})).toBeVisible(); await expect(page.getByRole('heading',{name:'Are you a player?'})).toHaveCount(0)
      await expect(page.getByRole('heading',{name:'My applications'})).toBeVisible(); await capture(page,'player-home',size)
      if(width===390) await page.getByRole('button',{name:'Toggle navigation menu'}).click()
      else await page.getByRole('button',{name:'Reuben Castellane'}).click()
      await expect(page.locator('a').filter({hasText:/^My profile$/})).toHaveAttribute('href',`/local-players/${localId}`)
      await expect(page.locator('a').filter({hasText:/^My applications$/})).toHaveAttribute('href','/onboarding/player#my-applications'); await capture(page,'account-menu',size)
      await page.locator('a').filter({hasText:/^My profile$/}).click()
      await expect(page.getByRole('heading',{name:'Your applications',exact:true})).toBeVisible(); await expect(page.getByRole('link',{name:'View my applications →',exact:true})).toBeVisible()
      await capture(page,'player-own-profile',size)
    })
    test('real backend: owner summary is dark when off and absent for visitors', async ({ page }) => {
      test.skip(!personasPath,'UXB_PERSONAS enables disposable aw_uxb HTTP checks')
      const privateCalls=[]
      page.on('request',r=>{if(new URL(r.url()).pathname.startsWith('/api/me/application')) privateCalls.push(r.url())})
      await page.goto(`/local-players/${localId}`)
      await expect(page.getByRole('heading',{name:'Reuben Castellane',exact:true})).toBeVisible()
      await expect(page.getByRole('heading',{name:'Your applications',exact:true})).toHaveCount(0)
      expect(privateCalls).toEqual([])
      await signIn(page,'player')
      await page.route('**/api/opportunities/features',route=>route.fulfill({status:404,json:{error:'Not found'}}))
      await page.goto(`/local-players/${localId}`)
      await expect(page.getByRole('heading',{name:'Your next chapter.',exact:true})).toBeVisible()
      await expect(page.getByRole('heading',{name:'Your applications',exact:true})).toHaveCount(0)
      expect(privateCalls).toEqual([])
      await capture(page,'player-applications-dark',size)
    })
    test('real backend: existing trial and age note agree with server rules', async ({ page }) => {
      test.skip(!personasPath,'UXB_PERSONAS enables disposable aw_uxb HTTP checks')
      await signIn(page,'player'); await page.goto(`/opportunities/${oid}`)
      await expect(page.getByRole('heading',{name:'You applied — Invited to trial'})).toBeVisible(); await expect(page.getByText('Your trial place is confirmed.',{exact:true})).toBeVisible()
      await expect(page.getByRole('button',{name:'Send application'})).toHaveCount(0); await capture(page,'opportunity-already-applied',size)
      await page.goto(`/opportunities/${ageOid}`)
      await expect(page.getByText('Your profile is outside the age range for this opportunity.')).toBeVisible(); await expect(page.getByRole('button',{name:'Send application'})).toHaveCount(0)
      await expect(page.getByText('Men',{exact:true})).toBeVisible(); await capture(page,'opportunity-outside-age',size)
      const personas=JSON.parse(await fs.readFile(personasPath,'utf8'))
      const claims=await page.request.get(`/api/me/application-claims?opportunity_id=${ageOid}`,{headers:{Authorization:'Bearer '+personas.player.token}})
      const claim=(await claims.json()).claims[0]
      expect(claim.outside_age_band).toBe(true)
      // Refused writes run only against the disposable lane backend, proving the UI/server disagreement is fixed.
      const headers={Authorization:'Bearer '+personas.player.token}
      for (const [id, status, error] of [[oid,409,'already_applied'],[ageOid,403,'outside_age_band']]) {
        const response=await page.request.post(`/api/opportunities/${id}/applications`,{headers,data:{claim_id:claim.claim_id,position:'Midfielder',current_club:'',contact_consent:true,client_request_id:crypto.randomUUID()}})
        expect(response.status()).toBe(status); expect((await response.json()).error).toBe(error)
      }
    })
    test('real backend: recruiting defaults to a published active posting', async ({ page }) => {
      test.skip(!personasPath,'UXB_PERSONAS enables disposable aw_uxb HTTP checks')
      await signIn(page,'owner'); await page.goto('/my-club?view=recruiting')
      const personas=JSON.parse(await fs.readFile(personasPath,'utf8'))
      const r=await page.request.get(`/api/club/${programId}/opportunities`,{headers:{Authorization:'Bearer '+personas.owner.token}})
      const rows=(await r.json()).opportunities
      expect(rows[0].status).toBe('published'); expect(rows.at(-1).status).toBe('draft')
      await expect(page.getByRole('heading',{name:rows[0].title,exact:true})).toBeVisible(); await capture(page,'recruiting-default',size)
    })
  })
}
