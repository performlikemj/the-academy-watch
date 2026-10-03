import { useState, useEffect, useCallback, useRef } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Loader2, Inbox, Send } from 'lucide-react'
import { APIService } from '@/lib/api'
import { useAuth, useAuthUI } from '@/context/AuthContext'
import { useContactRail } from '@/hooks/useContactRail.js'
import { ContactThread } from '@/components/contact/ContactThread'
import { ScoutSurface, ScoutHeader } from '@/components/scout/ScoutDesk'
import { statusLabel, counterpartName, canWithdraw, canRespond, previewText, upsertRequest, fetchAllRequests, defaultIntroductionBox } from '@/lib/introductions'

function formatDate(value) {
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

function RequestList({ box, requests, loading, error, selectedId, onSelect, onAction, busyId, onRetry }) {
  if (loading) return <p className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Loading…</p>
  if (error) return <div><p className="text-sm text-[#E9967A]">{error}</p><Button className="mt-2" variant="outline" onClick={onRetry}>Retry</Button></div>
  if (!requests.length) {
    return (
      <p className="border-t border-hairline-dark py-6 text-[15px] leading-relaxed text-muted-dark">
        {box === 'sent' ? <>Nothing sent yet. Find a player on the <Link to="/scout" className="underline">Scout Desk</Link> and introduce yourself.</> : 'No introductions yet. When a verified scout reaches out, it shows up here.'}
      </p>
    )
  }
  return (
    <ul className="flex flex-col border-t border-hairline-dark">
      {requests.map((request) => {
        const selected = request.id === selectedId
        const busy = busyId === request.id
        return (
          <li key={request.id} className="border-b border-hairline-dark">
            <button
              type="button"
              onClick={() => onSelect(request.id)}
              aria-current={selected ? 'true' : undefined}
              className={`w-full px-3 py-4 text-left transition-colors duration-150 ${selected ? 'bg-chalk/[0.05] shadow-[inset_2px_0_0_var(--color-gold)]' : 'hover:bg-chalk/[0.03]'}`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="min-w-0 [overflow-wrap:anywhere] font-serif text-[1.5rem] leading-tight text-chalk">{counterpartName(request, box)}</span>
                <Badge variant="outline" className="border-gold/50 text-gold">{statusLabel(request.status)}</Badge>
              </div>
              <p className="mt-1 [overflow-wrap:anywhere] font-mono text-[10.5px] uppercase tracking-[0.12em] text-[#8C9791]">{formatDate(request.created_at)}{request.participants?.club ? ` · via ${request.participants.club.display_name}` : ''}</p>
              <p className="mt-2 text-sm leading-relaxed text-[#C9CFCB]">{previewText(request.message)}</p>
            </button>
            {canRespond(request, box) ? (
              <div className="flex gap-2 px-3 pb-4">
                <Button size="sm" variant="on-dark" onClick={() => onAction('accept', request)} disabled={busy}>Accept</Button>
                <Button size="sm" variant="outline" onClick={() => onAction('decline', request)} disabled={busy}>Decline</Button>
              </div>
            ) : null}
            {canWithdraw(request, box) ? (
              <div className="px-3 pb-4">
                <Button size="sm" variant="ghost" onClick={() => onAction('withdraw', request)} disabled={busy}>Withdraw</Button>
              </div>
            ) : null}
          </li>
        )
      })}
    </ul>
  )
}

export function IntroductionsPage() {
  const auth = useAuth()
  const contactRail = useContactRail()
  const { openLoginModal } = useAuthUI()
  const [box, setBox] = useState(null)
  const [requests, setRequests] = useState({ sent: [], inbox: [] })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [busyId, setBusyId] = useState(null)
  const [actionError, setActionError] = useState(null)
  // Sent and Inbox share loading/error state; a late result from the other box must not overwrite this one.
  const loadSeq = useRef(0)
  const initialBox = useRef(null)
  // /introductions?request=<id> (e.g. "Open thread" on the watchlist) opens that thread once loaded.
  const [searchParams] = useSearchParams()
  const requestedId = searchParams.get('request')
  const pendingSelection = useRef(null)
  const loadedSelection = useRef(null)
  // Same for actions: a Sent accept/decline/withdraw that finishes after switching to Inbox must not write its
  // error or clear the busy flag there (its data update still lands in the right box via the closure).
  const actionSeq = useRef(0)

  const load = useCallback(async (which) => {
    if (!auth?.token) return
    const seq = loadSeq.current + 1
    loadSeq.current = seq
    setLoading(true)
    setError(null)
    try {
      if (which == null) {
        const [sent, inbox] = await Promise.all(['sent', 'inbox'].map((nextBox) =>
          fetchAllRequests((limit, offset) => APIService.listContactRequests({ box: nextBox, limit, offset }))))
        if (seq !== loadSeq.current) return
        setRequests({ sent, inbox })
        const requestedBox = requestedId
          ? (sent.some((r) => r.id === requestedId) ? 'sent' : inbox.some((r) => r.id === requestedId) ? 'inbox' : null)
          : null
        pendingSelection.current = requestedBox ? requestedId : null
        const chosen = requestedBox || defaultIntroductionBox({ sent, inbox })
        initialBox.current = chosen
        setBox(chosen)
        return
      }
      const rows = await fetchAllRequests((limit, offset) => APIService.listContactRequests({ box: which, limit, offset }))
      if (seq !== loadSeq.current) return
      setRequests((current) => ({ ...current, [which]: rows }))
    } catch (err) {
      if (seq !== loadSeq.current) return
      if (which == null) {
        initialBox.current = 'inbox'
        setBox('inbox')
      }
      setError(err?.body?.error || err?.message || 'Introductions could not be loaded.')
    } finally {
      if (seq === loadSeq.current) setLoading(false)
    }
  }, [auth?.token, requestedId])

  useEffect(() => {
    // Strict Mode replays mount effects; share the pending load for this selection.
    if (loadedSelection.current?.box === box && loadedSelection.current?.token === auth?.token) return
    loadedSelection.current = { box, token: auth?.token }
    actionSeq.current += 1
    setSelectedId(box != null ? pendingSelection.current : null)
    if (box != null) pendingSelection.current = null
    setActionError(null)
    setBusyId(null)
    if (box != null && initialBox.current === box) {
      initialBox.current = null
      return
    }
    load(box)
  }, [box, load, auth?.token])

  const applyUpdate = useCallback((updated) => {
    setRequests((current) => ({ ...current, [box]: upsertRequest(current[box], updated) }))
  }, [box])

  const act = async (action, request) => {
    const seq = actionSeq.current + 1
    actionSeq.current = seq
    setBusyId(request.id)
    setActionError(null)
    try {
      const call = action === 'accept'
        ? APIService.acceptContactRequest(request.id)
        : action === 'decline'
          ? APIService.declineContactRequest(request.id)
          : APIService.withdrawContactRequest(request.id)
      const res = await call
      if (res?.contact_request) applyUpdate(res.contact_request)
    } catch (err) {
      if (seq !== actionSeq.current) return
      setActionError(err?.body?.error || err?.message || 'That action did not go through.')
    } finally {
      if (seq === actionSeq.current) setBusyId(null)
    }
  }

  const list = requests[box] || []
  const selected = list.find((r) => r.id === selectedId) || null

  if (contactRail === false) {
    return (
      <ScoutSurface>
        <div className="floodlight-container py-20">
          <Card className="mx-auto w-full max-w-md">
            <CardHeader><CardTitle>Introductions</CardTitle><CardDescription>Introductions aren&apos;t available right now. Please check back later.</CardDescription></CardHeader>
            <CardContent><Button asChild variant="outline"><Link to="/">Return to Home</Link></Button></CardContent>
          </Card>
        </div>
      </ScoutSurface>
    )
  }

  if (!auth?.token) {
    return (
      <ScoutSurface>
        <div className="floodlight-container py-20">
          <Card className="mx-auto w-full max-w-md">
            <CardHeader><CardTitle>Introductions</CardTitle><CardDescription>Sign in to see introductions you sent or received.</CardDescription></CardHeader>
            <CardContent><Button variant="on-dark" onClick={openLoginModal}>Sign in</Button></CardContent>
          </Card>
        </div>
      </ScoutSurface>
    )
  }

  return (
    <ScoutSurface>
      <div className="floodlight-container pb-24">
        <ScoutHeader
          eyebrow="Introductions · Scout ↔ player"
          title="Introductions,"
          accent="done properly"
          lede="Scout ↔ player introductions. Messaging opens once an introduction is accepted (and, for contracted players, allowed by the club)."
        />
        <Tabs value={box || 'inbox'} onValueChange={setBox}>
          <TabsList className="mb-6">
            <TabsTrigger value="sent"><Send className="mr-1.5 h-4 w-4" /> Sent</TabsTrigger>
            <TabsTrigger value="inbox"><Inbox className="mr-1.5 h-4 w-4" /> Received</TabsTrigger>
          </TabsList>
          {['sent', 'inbox'].map((which) => (
            <TabsContent key={which} value={which}>
              <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-8 lg:grid-cols-[24rem_minmax(0,1fr)]">
                <div className="min-w-0">
                  <RequestList box={which} requests={requests[which] || []} loading={loading && (box || 'inbox') === which} error={(box || 'inbox') === which ? error : null} selectedId={selectedId} onSelect={setSelectedId} onAction={act} busyId={busyId} onRetry={() => load(which)} />
                  {actionError && box === which ? <p className="mt-2 text-sm text-[#E9967A]">{actionError}</p> : null}
                </div>
                <Card className="min-w-0 py-0">
                  <CardContent className="p-6">
                    {box === which ? <ContactThread request={selected} onRequestChange={applyUpdate} viewerRole={box === 'sent' ? 'scout' : 'player'} canReportOutcome={box === 'sent'} /> : null}
                  </CardContent>
                </Card>
              </div>
            </TabsContent>
          ))}
        </Tabs>
      </div>
    </ScoutSurface>
  )
}

export default IntroductionsPage
