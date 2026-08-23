import { useState, useEffect, useCallback, useRef } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Loader2, Inbox, Send } from 'lucide-react'
import { APIService } from '@/lib/api'
import { useAuth, useAuthUI } from '@/context/AuthContext'
import { useContactRail } from '@/hooks/useContactRail.js'
import { ContactThread } from '@/components/contact/ContactThread'
import { statusLabel, counterpartName, canWithdraw, canRespond, previewText, upsertRequest, fetchAllRequests } from '@/lib/introductions'

function formatDate(value) {
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

function RequestList({ box, requests, loading, error, selectedId, onSelect, onAction, busyId }) {
  if (loading) return <p className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Loading…</p>
  if (error) return <p className="text-sm text-rose-600">{error}</p>
  if (!requests.length) {
    return (
      <p className="text-sm text-muted-foreground">
        {box === 'sent' ? <>Nothing sent yet. Find a player on the <Link to="/scout" className="underline">Scout Desk</Link> and introduce yourself.</> : 'No introductions yet. When a verified scout reaches out, it shows up here.'}
      </p>
    )
  }
  return (
    <ul className="space-y-2">
      {requests.map((request) => {
        const selected = request.id === selectedId
        const busy = busyId === request.id
        return (
          <li key={request.id}>
            <button
              type="button"
              onClick={() => onSelect(request.id)}
              className={`w-full rounded-xl border p-3 text-left transition-colors ${selected ? 'border-primary/40 bg-primary/5' : 'border-border bg-card hover:bg-muted/30'}`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="truncate font-semibold text-foreground">{counterpartName(request, box)}</span>
                <Badge variant="secondary">{statusLabel(request.status)}</Badge>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">{formatDate(request.created_at)}{request.participants?.club ? ` · via ${request.participants.club.display_name}` : ''}</p>
              <p className="mt-1 text-sm text-foreground/80">{previewText(request.message)}</p>
            </button>
            {canRespond(request, box) ? (
              <div className="mt-1 flex gap-2">
                <Button size="sm" onClick={() => onAction('accept', request)} disabled={busy}>Accept</Button>
                <Button size="sm" variant="outline" onClick={() => onAction('decline', request)} disabled={busy}>Decline</Button>
              </div>
            ) : null}
            {canWithdraw(request, box) ? (
              <div className="mt-1">
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
  const [box, setBox] = useState('sent')
  const [requests, setRequests] = useState({ sent: [], inbox: [] })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [busyId, setBusyId] = useState(null)
  const [actionError, setActionError] = useState(null)
  // Sent and Inbox share loading/error state; a late result from the other box must not overwrite this one.
  const loadSeq = useRef(0)
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
      const rows = await fetchAllRequests((limit, offset) => APIService.listContactRequests({ box: which, limit, offset }))
      if (seq !== loadSeq.current) return
      setRequests((current) => ({ ...current, [which]: rows }))
    } catch (err) {
      if (seq !== loadSeq.current) return
      setError(err?.body?.error || err?.message || 'Introductions could not be loaded.')
    } finally {
      if (seq === loadSeq.current) setLoading(false)
    }
  }, [auth?.token])

  useEffect(() => {
    actionSeq.current += 1
    setSelectedId(null)
    setActionError(null)
    setBusyId(null)
    load(box)
  }, [box, load])

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
      <div className="min-h-screen bg-background p-4">
        <Card className="mx-auto w-full max-w-md">
          <CardHeader><CardTitle>Introductions</CardTitle><CardDescription>Introductions aren&apos;t available right now. Please check back later.</CardDescription></CardHeader>
          <CardContent><Button asChild variant="outline"><Link to="/">Return to Home</Link></Button></CardContent>
        </Card>
      </div>
    )
  }

  if (!auth?.token) {
    return (
      <div className="min-h-screen bg-background p-4">
        <Card className="mx-auto w-full max-w-md">
          <CardHeader><CardTitle>Introductions</CardTitle><CardDescription>Sign in to see introductions you sent or received.</CardDescription></CardHeader>
          <CardContent><Button onClick={openLoginModal}>Sign in</Button></CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background p-4">
      <div className="mx-auto w-full max-w-6xl space-y-4">
        <header>
          <h1 className="text-2xl font-bold text-foreground">Introductions</h1>
          <p className="text-sm text-muted-foreground">Scout ↔ player introductions. Messaging opens once an introduction is accepted (and, for contracted players, allowed by the club).</p>
        </header>
        <Tabs value={box} onValueChange={setBox}>
          <TabsList>
            <TabsTrigger value="sent"><Send className="mr-1.5 h-4 w-4" /> Sent</TabsTrigger>
            <TabsTrigger value="inbox"><Inbox className="mr-1.5 h-4 w-4" /> Inbox</TabsTrigger>
          </TabsList>
          {['sent', 'inbox'].map((which) => (
            <TabsContent key={which} value={which}>
              <div className="grid items-start gap-4 lg:grid-cols-[22rem_minmax(0,1fr)]">
                <div>
                  <RequestList box={which} requests={requests[which] || []} loading={loading && box === which} error={box === which ? error : null} selectedId={selectedId} onSelect={setSelectedId} onAction={act} busyId={busyId} />
                  {actionError && box === which ? <p className="mt-2 text-sm text-rose-600">{actionError}</p> : null}
                </div>
                <Card>
                  <CardContent className="pt-6">
                    {box === which ? <ContactThread request={selected} onRequestChange={applyUpdate} /> : null}
                  </CardContent>
                </Card>
              </div>
            </TabsContent>
          ))}
        </Tabs>
      </div>
    </div>
  )
}

export default IntroductionsPage
