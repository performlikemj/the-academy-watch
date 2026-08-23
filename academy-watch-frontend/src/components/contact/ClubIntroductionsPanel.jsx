import { useState, useEffect, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Loader2 } from 'lucide-react'
import { APIService } from '@/lib/api'
import { ContactThread } from '@/components/contact/ContactThread'
import { participantName } from '@/lib/contact-thread'

export function consentLabel(status) {
  if (status === 'granted') return 'Allowed'
  if (status === 'declined') return 'Declined'
  if (status === 'pending') return 'Needs your decision'
  return '—'
}

export function upsertById(list, updated) {
  if (!updated?.id) return list
  return list.some((r) => r.id === updated.id) ? list.map((r) => (r.id === updated.id ? updated : r)) : [updated, ...list]
}

export function ClubIntroductionsPanel({ programId, onAccessDenied }) {
  const [requests, setRequests] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [busyId, setBusyId] = useState(null)
  const [actionError, setActionError] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await APIService.listContactRequests({ box: 'club', limit: 100 })
      const rows = Array.isArray(res?.requests) ? res.requests : []
      setRequests(programId ? rows.filter((r) => r.club_program_id === programId) : rows)
    } catch (err) {
      if (err?.status === 403 && onAccessDenied) {
        onAccessDenied()
        return
      }
      setError(err?.body?.error || err?.message || 'Introductions could not be loaded.')
    } finally {
      setLoading(false)
    }
  }, [programId, onAccessDenied])

  useEffect(() => { load() }, [load])

  const applyUpdate = useCallback((updated) => setRequests((current) => upsertById(current, updated)), [])

  const decide = async (request, action) => {
    setBusyId(request.id)
    setActionError(null)
    try {
      const res = await APIService.setClubConsent(request.id, { action })
      if (res?.contact_request) applyUpdate(res.contact_request)
    } catch (err) {
      setActionError(err?.body?.error || err?.message || 'That decision did not go through.')
    } finally {
      setBusyId(null)
    }
  }

  const selected = requests.find((r) => r.id === selectedId) || null

  return (
    <div className="grid items-start gap-4 lg:grid-cols-[22rem_minmax(0,1fr)]" data-testid="club-introductions-panel">
      <div className="space-y-2">
        {loading ? (
          <p className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Loading…</p>
        ) : error ? (
          <p className="text-sm text-rose-600">{error}</p>
        ) : requests.length === 0 ? (
          <p className="text-sm text-muted-foreground">No introductions involve your club yet. When a verified scout asks to contact one of your contracted players, it appears here for your decision.</p>
        ) : (
          <ul className="space-y-2">
            {requests.map((request) => {
              const pending = request.club_consent_status === 'pending'
              const busy = busyId === request.id
              return (
                <li key={request.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedId(request.id)}
                    className={`w-full rounded-xl border p-3 text-left transition-colors ${request.id === selectedId ? 'border-primary/40 bg-primary/5' : 'border-border bg-card hover:bg-muted/30'}`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate font-semibold text-foreground">{participantName(request, 'scout')} → {participantName(request, 'player')}</span>
                      <Badge variant={pending ? 'default' : 'secondary'}>{consentLabel(request.club_consent_status)}</Badge>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">Player status: {request.status}</p>
                  </button>
                  {pending ? (
                    <div className="mt-1 flex gap-2">
                      <Button size="sm" onClick={() => decide(request, 'grant')} disabled={busy}>Allow</Button>
                      <Button size="sm" variant="outline" onClick={() => decide(request, 'decline')} disabled={busy}>Decline</Button>
                    </div>
                  ) : null}
                </li>
              )
            })}
          </ul>
        )}
        {actionError ? <p className="text-sm text-rose-600">{actionError}</p> : null}
      </div>
      <Card>
        <CardContent className="pt-6">
          <ContactThread request={selected} onRequestChange={applyUpdate} canReportOutcome={false} />
        </CardContent>
      </Card>
    </div>
  )
}

export default ClubIntroductionsPanel
