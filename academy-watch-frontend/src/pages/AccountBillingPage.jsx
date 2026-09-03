import { useEffect, useMemo, useRef, useState } from 'react'
import { CheckCircle2, CreditCard, Loader2, ShieldCheck } from 'lucide-react'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useAuth, useAuthUI } from '@/context/AuthContext'
import { APIService } from '@/lib/api'
import { track } from '@/lib/track'

function money(amount, currency) {
  if (!Number.isFinite(amount) || !currency) return 'Price unavailable'
  return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(amount / 100)
}

function date(value) {
  if (!value) return null
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? null : parsed.toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' })
}

export function AccountBillingPage() {
  const auth = useAuth()
  const { openLoginModal } = useAuthUI()
  const openedLogin = useRef(false)
  const trackedSuccess = useRef(false)
  const [state, setState] = useState({ loading: true, config: null, billing: null, entitlements: null, unavailable: false, failed: false })
  const [loadAttempt, setLoadAttempt] = useState(0)
  const [portalBusy, setPortalBusy] = useState(false)
  const [portalError, setPortalError] = useState(null)
  const [checkoutSuccess, setCheckoutSuccess] = useState(() => new URLSearchParams(window.location.search).get('checkout') === 'success')

  useEffect(() => {
    if (auth?.token || openedLogin.current) return
    openedLogin.current = true
    openLoginModal()
  }, [auth?.token, openLoginModal])

  useEffect(() => {
    if (!auth?.token) return undefined
    let cancelled = false
    setState({ loading: true, config: null, billing: null, entitlements: null, unavailable: false, failed: false })
    Promise.all([
      APIService.getBillingConfig(),
      APIService.getBillingMe(),
      APIService.getScoutEntitlements(),
    ]).then(([config, billing, entitlementResponse]) => {
      if (cancelled) return
      const unavailable = config === null || billing === null || entitlementResponse === null
      setState({
        loading: false,
        config,
        billing,
        entitlements: entitlementResponse?.entitlements || null,
        unavailable,
        failed: false,
      })
    }).catch(() => {
      if (!cancelled) setState({ loading: false, config: null, billing: null, entitlements: null, unavailable: false, failed: true })
    })
    return () => { cancelled = true }
  }, [auth?.token, loadAttempt])

  useEffect(() => {
    if (!auth?.token || trackedSuccess.current) return
    const params = new URLSearchParams(window.location.search)
    if (params.get('checkout') !== 'success') return
    trackedSuccess.current = true
    track('checkout_completed')
    setCheckoutSuccess(true)
    for (let index = window.sessionStorage.length - 1; index >= 0; index -= 1) {
      const key = window.sessionStorage.key(index)
      if (key?.startsWith('academyWatch.checkout.')) window.sessionStorage.removeItem(key)
    }
    window.history.replaceState({}, '', window.location.pathname)
  }, [auth?.token])

  const productNames = useMemo(() => new Map((state.config?.products || []).map((product) => [product.code, product.name])), [state.config])
  const openPortal = async () => {
    setPortalBusy(true)
    setPortalError(null)
    try {
      const result = await APIService.createBillingPortal()
      window.location.assign(result.portal_url)
    } catch (error) {
      setPortalError(error?.status === 409 && error?.body?.error === 'no_billing_account'
        ? 'Your billing account is still being created. Refresh in a moment.'
        : error?.body?.error || error?.message || 'Billing management is unavailable right now.')
    } finally {
      setPortalBusy(false)
    }
  }

  if (!auth?.token) return null

  if (state.loading) {
    return <div className="flex min-h-[60vh] items-center justify-center text-muted-foreground"><Loader2 className="mr-2 h-5 w-5 animate-spin" />Loading billing…</div>
  }

  if (state.unavailable) {
    return <div className="mx-auto max-w-2xl px-4 py-16"><Card><CardContent className="py-12 text-center"><CreditCard className="mx-auto h-8 w-8 text-muted-foreground" /><h1 className="mt-4 text-2xl font-bold">Billing isn&apos;t available yet.</h1><p className="mt-2 text-sm text-muted-foreground">Scout tools continue to work as usual.</p></CardContent></Card></div>
  }

  if (state.failed) {
    return <div className="mx-auto max-w-2xl px-4 py-16"><Card><CardContent className="py-12 text-center"><CreditCard className="mx-auto h-8 w-8 text-muted-foreground" /><h1 className="mt-4 text-2xl font-bold">We couldn&apos;t load your billing details.</h1><p className="mt-2 text-sm text-muted-foreground">Try again.</p><Button className="mt-5" onClick={() => setLoadAttempt((current) => current + 1)}>Retry</Button></CardContent></Card></div>
  }

  const entitlements = state.entitlements
  const features = entitlements?.features || {}

  return (
    <div className="min-h-screen bg-gradient-to-b from-secondary to-background">
      <main className="mx-auto max-w-4xl space-y-6 px-4 py-10 sm:px-6">
        <header><p className="text-xs font-semibold uppercase tracking-[0.2em] text-primary">Account</p><h1 className="mt-2 text-3xl font-bold tracking-tight">Billing</h1><p className="mt-2 text-muted-foreground">Your Scout Pro access and Stripe subscription details.</p></header>
        {checkoutSuccess ? <div role="status" className="flex items-center gap-3 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-emerald-950"><CheckCircle2 className="h-5 w-5" />Checkout complete. Your access will update as Stripe confirms the subscription.</div> : null}
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><ShieldCheck className="h-5 w-5" />Scout access</CardTitle><CardDescription>Entitlements are confirmed by the server.</CardDescription></CardHeader>
          <CardContent className="space-y-3"><div className="flex flex-wrap items-center gap-2"><Badge>{entitlements?.tier === 'pro' ? 'Scout Pro' : 'Free'}</Badge><span className="text-sm text-muted-foreground">Source: {String(entitlements?.source || 'none').replace('_', ' ')}</span></div><p className="text-sm">{features.gol_chat ? 'GOL chatbot unlocked' : 'GOL chatbot requires Scout Pro'}</p>{entitlements?.grandfathered_until ? <p className="text-xs text-muted-foreground">Grandfathered until {date(entitlements.grandfathered_until)}</p> : null}</CardContent>
        </Card>

        <section className="space-y-3" aria-labelledby="subscriptions-heading">
          <div className="flex items-center justify-between gap-4"><h2 id="subscriptions-heading" className="text-xl font-bold">Subscriptions</h2>{state.billing?.has_billing_account ? <Button onClick={openPortal} disabled={portalBusy}>{portalBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <CreditCard className="mr-2 h-4 w-4" />}Manage billing</Button> : null}</div>
          {portalError ? <p className="text-sm text-destructive">{portalError}</p> : null}
          {(state.billing?.subscriptions || []).length ? state.billing.subscriptions.map((subscription) => (
            <Card key={subscription.id}>
              <CardContent className="flex flex-col justify-between gap-4 p-5 sm:flex-row sm:items-center"><div><div className="flex flex-wrap items-center gap-2"><h3 className="font-semibold">{productNames.get(subscription.product_code) || subscription.product_code}</h3><Badge variant="outline" className="capitalize">{subscription.status}</Badge></div><p className="mt-2 text-sm text-muted-foreground">{money(subscription.unit_amount, subscription.currency)} / {subscription.interval || subscription.price_code}</p>{subscription.current_period_end ? <p className="mt-1 text-sm">{subscription.cancel_at_period_end ? 'Ends' : 'Renews'} on {date(subscription.current_period_end)}</p> : null}</div></CardContent>
            </Card>
          )) : <Card><CardContent className="py-10 text-center text-sm text-muted-foreground">No paid subscriptions yet.</CardContent></Card>}
        </section>
      </main>
    </div>
  )
}

export default AccountBillingPage
