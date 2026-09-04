import { useEffect, useMemo, useRef, useState } from 'react'
import { CheckCircle2, Coins, CreditCard, Loader2, ReceiptText, ShieldCheck } from 'lucide-react'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useAuth, useAuthUI } from '@/context/AuthContext'
import { APIService } from '@/lib/api'
import { track } from '@/lib/track'

const PURCHASE_POLL_ATTEMPTS = 6
const PURCHASE_POLL_DELAY_MS = 2400

function money(amount, currency) {
  if (!Number.isFinite(amount) || !currency) return 'Amount unavailable'
  return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(amount / 100)
}

function date(value) {
  if (!value) return null
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? null : parsed.toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' })
}

function checkoutSessionFromLocation() {
  const params = new URLSearchParams(window.location.search)
  return params.get('checkout') === 'success' ? params.get('session_id') : null
}

function choosePack(packs, purchases) {
  const preferredId = purchases.length ? 'gol_topup' : 'gol_starter'
  return packs.find((pack) => pack.pack_id === preferredId) || packs[0] || null
}

function clearCheckoutKeys() {
  for (let index = window.sessionStorage.length - 1; index >= 0; index -= 1) {
    const key = window.sessionStorage.key(index)
    if (key?.startsWith('academyWatch.checkout.')) window.sessionStorage.removeItem(key)
  }
}

function stripCheckoutQuery() {
  window.history.replaceState({}, '', window.location.pathname)
}

export function AccountBillingPage() {
  const auth = useAuth()
  const { openLoginModal } = useAuthUI()
  const openedLogin = useRef(false)
  const trackedSuccess = useRef(false)
  const startedPurchasePoll = useRef(false)
  const billingAtLoad = useRef(null)
  const [initialCheckoutSessionId] = useState(checkoutSessionFromLocation)
  const checkoutSessionId = useRef(initialCheckoutSessionId)
  const [state, setState] = useState({ loading: true, config: null, billing: null, entitlements: null, unavailable: false, failed: false })
  const [loadAttempt, setLoadAttempt] = useState(0)
  const [portalBusy, setPortalBusy] = useState(false)
  const [portalError, setPortalError] = useState(null)
  const [checkoutBusy, setCheckoutBusy] = useState(false)
  const [checkoutError, setCheckoutError] = useState(null)
  const [checkoutNotice, setCheckoutNotice] = useState(initialCheckoutSessionId ? { type: 'waiting' } : null)

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
      billingAtLoad.current = billing
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
    if (!auth?.token || trackedSuccess.current || !checkoutSessionId.current) return
    trackedSuccess.current = true
    track('checkout_completed')
    clearCheckoutKeys()
  }, [auth?.token])

  const products = useMemo(() => state.config?.products || [], [state.config?.products])
  const packs = useMemo(() => state.config?.packs || [], [state.config?.packs])
  const subscriptions = useMemo(() => state.billing?.subscriptions || [], [state.billing?.subscriptions])
  const purchases = useMemo(() => state.billing?.gol?.purchases || [], [state.billing?.gol?.purchases])
  const creditOnly = Boolean(state.config?.enabled && packs.length > 0 && products.length === 0)
  const creditUiLit = auth.scoutPro?.enabled === true && !auth.isAdmin
  const showGol = creditUiLit && Boolean(state.billing?.gol)
  const showLegacyBilling = products.length > 0 || subscriptions.length > 0
  const visibleCheckoutNotice = checkoutNotice?.type === 'waiting' && !creditOnly
    ? { type: 'subscription' }
    : checkoutNotice

  useEffect(() => {
    const targetSessionId = checkoutSessionId.current
    if (!targetSessionId || state.loading || state.failed || state.unavailable || startedPurchasePoll.current) return undefined
    startedPurchasePoll.current = true

    if (!creditOnly) {
      stripCheckoutQuery()
      return undefined
    }

    let cancelled = false
    let timeoutId = null
    const wait = () => new Promise((resolve) => {
      timeoutId = window.setTimeout(resolve, PURCHASE_POLL_DELAY_MS)
    })

    const finishPurchase = async (purchase) => {
      setCheckoutNotice({ type: 'added', credits: purchase.credits })
      try { await APIService.getProfile() } catch { /* the confirmed balance remains visible */ }
      if (!cancelled) stripCheckoutQuery()
    }

    const poll = async () => {
      let billing = billingAtLoad.current
      for (let attempt = 0; attempt < PURCHASE_POLL_ATTEMPTS; attempt += 1) {
        const purchase = billing?.gol?.purchases?.find((entry) => entry.stripe_session_id === targetSessionId)
        if (purchase) {
          await finishPurchase(purchase)
          return
        }
        if (attempt === PURCHASE_POLL_ATTEMPTS - 1) break
        await wait()
        if (cancelled) return
        try {
          billing = await APIService.getBillingMe()
          if (billing && !cancelled) setState((current) => ({ ...current, billing }))
        } catch {
          // A transient poll failure still consumes this bounded attempt.
        }
      }
      if (!cancelled) {
        setCheckoutNotice({ type: 'pending' })
        stripCheckoutQuery()
      }
    }

    poll()
    return () => {
      cancelled = true
      if (timeoutId !== null) window.clearTimeout(timeoutId)
    }
  }, [creditOnly, state.failed, state.loading, state.unavailable])

  const productNames = useMemo(() => new Map(products.map((product) => [product.code, product.name])), [products])
  const packNames = useMemo(() => new Map(packs.map((pack) => [pack.pack_id, pack.label])), [packs])
  const selectedPack = choosePack(packs, purchases)

  const openPortal = async () => {
    setPortalBusy(true)
    setPortalError(null)
    try {
      const result = await APIService.createBillingPortal()
      window.location.assign(result.portal_url)
    } catch (error) {
      setPortalError(error?.status === 409 && error?.body?.error === 'no_billing_account'
        ? 'Your billing account is still being created. Refresh in a moment.'
        : 'Billing management is unavailable right now.')
    } finally {
      setPortalBusy(false)
    }
  }

  const buyCredits = async () => {
    if (!selectedPack || checkoutBusy) return
    setCheckoutBusy(true)
    setCheckoutError(null)
    try {
      const storageKey = `academyWatch.checkout.gol.${selectedPack.pack_id}`
      let clientKey = window.sessionStorage.getItem(storageKey)
      if (!clientKey) {
        clientKey = crypto.randomUUID()
        window.sessionStorage.setItem(storageKey, clientKey)
      }
      const result = await APIService.createBillingCheckout({
        pack_id: selectedPack.pack_id,
        client_key: clientKey,
      })
      track('checkout_started', { product_code: 'gol', price_code: selectedPack.pack_id })
      window.location.assign(result.checkout_url)
    } catch {
      setCheckoutError('Checkout could not be started. Try again.')
    } finally {
      setCheckoutBusy(false)
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
  const gol = state.billing?.gol

  return (
    <div className="min-h-screen bg-gradient-to-b from-secondary to-background">
      <main className="mx-auto max-w-4xl space-y-6 px-4 py-10 sm:px-6">
        <header><p className="text-xs font-semibold uppercase tracking-[0.2em] text-primary">Account</p><h1 className="mt-2 text-3xl font-bold tracking-tight">Billing</h1><p className="mt-2 text-muted-foreground">Your purchases, credits, and subscription details.</p></header>

        {visibleCheckoutNotice?.type === 'waiting' ? <div role="status" className="flex items-center gap-3 rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 text-sky-950"><Loader2 className="h-5 w-5 animate-spin" />Confirming your GOL credits…</div> : null}
        {visibleCheckoutNotice?.type === 'added' ? <div role="status" className="flex items-center gap-3 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-emerald-950"><CheckCircle2 className="h-5 w-5" />Added {visibleCheckoutNotice.credits} credits</div> : null}
        {visibleCheckoutNotice?.type === 'pending' ? <div role="status" className="flex items-center gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-amber-950"><Loader2 className="h-5 w-5" />Payment received. Credits are still being confirmed.</div> : null}
        {visibleCheckoutNotice?.type === 'subscription' ? <div role="status" className="flex items-center gap-3 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-emerald-950"><CheckCircle2 className="h-5 w-5" />Checkout complete. Your access will update as Stripe confirms the subscription.</div> : null}

        {showGol ? (
          <section className="space-y-3" aria-labelledby="gol-credits-heading">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <h2 id="gol-credits-heading" className="flex items-center gap-2 text-xl font-bold"><Coins className="h-5 w-5 text-primary" />GOL credits</h2>
                <p className="mt-1 text-sm text-muted-foreground">Free questions are used first, then prepaid credits.</p>
              </div>
              {selectedPack ? <Button onClick={buyCredits} disabled={checkoutBusy}>{checkoutBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <CreditCard className="mr-2 h-4 w-4" />}{purchases.length ? 'Top up GOL credits' : 'Buy GOL credits'}</Button> : null}
            </div>
            {checkoutError ? <p className="text-sm text-destructive">{checkoutError}</p> : null}
            <Card className="overflow-hidden border-primary/25">
              <CardContent className="grid gap-4 p-5 sm:grid-cols-2">
                <div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Free questions remaining</p><p className="mt-1 text-3xl font-bold tabular-nums">{gol.free_questions_remaining}<span className="ml-1 text-sm font-normal text-muted-foreground">of {gol.free_allowance}</span></p></div>
                <div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Credit balance</p><p className="mt-1 text-3xl font-bold tabular-nums">{gol.credit_balance}</p></div>
              </CardContent>
            </Card>

            <div className="space-y-2">
              <h3 className="flex items-center gap-2 text-sm font-semibold"><ReceiptText className="h-4 w-4" />Purchases</h3>
              {purchases.length ? purchases.map((purchase) => (
                <Card key={purchase.stripe_session_id}>
                  <CardContent className="flex flex-col justify-between gap-3 p-4 sm:flex-row sm:items-center">
                    <div><p className="font-semibold">{packNames.get(purchase.pack_id) || 'GOL credit pack'}</p><p className="mt-1 text-sm text-muted-foreground">{date(purchase.created_at) || 'Date unavailable'} · {purchase.credits} credits</p></div>
                    <div className="sm:text-right"><p className="font-medium tabular-nums">{money(purchase.amount_paid_cents, purchase.currency)} {purchase.currency?.toUpperCase()}</p>{purchase.refunded_credits > 0 ? <p className="mt-1 text-xs text-muted-foreground">{purchase.refunded_credits} credits refunded</p> : null}</div>
                  </CardContent>
                </Card>
              )) : <Card><CardContent className="py-8 text-center text-sm text-muted-foreground">No credit purchases yet.</CardContent></Card>}
            </div>
          </section>
        ) : null}

        {showLegacyBilling ? (
          <>
            <Card>
              <CardHeader><CardTitle className="flex items-center gap-2"><ShieldCheck className="h-5 w-5" />Scout access</CardTitle><CardDescription>Entitlements are confirmed by the server.</CardDescription></CardHeader>
              <CardContent className="space-y-3"><div className="flex flex-wrap items-center gap-2"><Badge>{entitlements?.tier === 'pro' ? 'Scout Pro' : 'Free'}</Badge><span className="text-sm text-muted-foreground">Source: {String(entitlements?.source || 'none').replace('_', ' ')}</span></div><p className="text-sm">{features.gol_chat ? 'GOL chatbot unlocked' : 'GOL chatbot unavailable'}</p>{entitlements?.grandfathered_until ? <p className="text-xs text-muted-foreground">Grandfathered until {date(entitlements.grandfathered_until)}</p> : null}</CardContent>
            </Card>

            <section className="space-y-3" aria-labelledby="subscriptions-heading">
              <div className="flex items-center justify-between gap-4"><h2 id="subscriptions-heading" className="text-xl font-bold">Subscriptions</h2>{state.billing?.has_billing_account ? <Button onClick={openPortal} disabled={portalBusy}>{portalBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <CreditCard className="mr-2 h-4 w-4" />}Manage billing</Button> : null}</div>
              {portalError ? <p className="text-sm text-destructive">{portalError}</p> : null}
              {subscriptions.length ? subscriptions.map((subscription) => (
                <Card key={subscription.id}>
                  <CardContent className="flex flex-col justify-between gap-4 p-5 sm:flex-row sm:items-center"><div><div className="flex flex-wrap items-center gap-2"><h3 className="font-semibold">{productNames.get(subscription.product_code) || 'Paid plan'}</h3><Badge variant="outline" className="capitalize">{subscription.status}</Badge></div><p className="mt-2 text-sm text-muted-foreground">{money(subscription.unit_amount, subscription.currency)} / {subscription.interval || subscription.price_code}</p>{subscription.current_period_end ? <p className="mt-1 text-sm">{subscription.cancel_at_period_end ? 'Ends' : 'Renews'} on {date(subscription.current_period_end)}</p> : null}</div></CardContent>
                </Card>
              )) : <Card><CardContent className="py-10 text-center text-sm text-muted-foreground">No paid subscriptions yet.</CardContent></Card>}
            </section>
          </>
        ) : null}
      </main>
    </div>
  )
}

export default AccountBillingPage
