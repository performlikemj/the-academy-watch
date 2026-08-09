import { useEffect, useState } from 'react'
import { APIService } from '@/lib/api'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table'
import { Textarea } from '@/components/ui/textarea'
import {
    AlertCircle,
    Check,
    CheckCircle2,
    ChevronLeft,
    ChevronRight,
    ClipboardCheck,
    ExternalLink,
    FileWarning,
    Loader2,
    MessagesSquare,
    ShieldAlert,
    ShieldCheck,
    X,
} from 'lucide-react'

const STATUS_COLORS = {
    pending: 'bg-amber-50 text-amber-800 border-amber-200',
    approved: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    rejected: 'bg-rose-50 text-rose-800 border-rose-200',
    revoked: 'bg-stone-100 text-stone-700 border-stone-200',
    open: 'bg-rose-50 text-rose-800 border-rose-200',
    reviewing: 'bg-sky-50 text-sky-800 border-sky-200',
    resolved: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    dismissed: 'bg-stone-100 text-stone-700 border-stone-200',
    accepted: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    declined: 'bg-rose-50 text-rose-800 border-rose-200',
    withdrawn: 'bg-stone-100 text-stone-700 border-stone-200',
    expired: 'bg-slate-100 text-slate-700 border-slate-200',
    granted: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    denied: 'bg-rose-50 text-rose-800 border-rose-200',
    not_required: 'bg-slate-100 text-slate-700 border-slate-200',
}

const ROUTING_COLORS = {
    direct: 'bg-violet-50 text-violet-800 border-violet-200',
    club_notified: 'bg-sky-50 text-sky-800 border-sky-200',
    club_included: 'bg-indigo-50 text-indigo-800 border-indigo-200',
}

function title(value) {
    if (!value) return '—'
    return String(value).replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function formatDate(value, withTime = false) {
    if (!value) return '—'
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return '—'
    return withTime
        ? date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
        : date.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

function StatusBadge({ status, className = '' }) {
    return (
        <Badge className={`${STATUS_COLORS[status] || STATUS_COLORS.revoked} ${className}`}>
            {title(status)}
        </Badge>
    )
}

function Loading({ label }) {
    return (
        <div className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            {label}
        </div>
    )
}

function DecisionDialog({ decision, note, setNote, busy, onClose, onConfirm }) {
    const isVerification = decision?.kind === 'verification'
    const isReject = decision?.action === 'reject'
    const actionLabel = {
        approve: 'Approve',
        reject: 'Reject',
        resolved: 'Resolve',
        dismissed: 'Dismiss',
    }[decision?.action] || title(decision?.action)
    const subject = isVerification
        ? decision?.item?.full_name
        : `report #${decision?.item?.id || ''}`

    return (
        <Dialog open={Boolean(decision)} onOpenChange={(open) => { if (!open && !busy) onClose() }}>
            <DialogContent>
                <DialogHeader>
                    <DialogTitle>{actionLabel} {subject}</DialogTitle>
                    <DialogDescription>
                        {isVerification
                            ? `${actionLabel} this scout verification application.`
                            : `${actionLabel} this content report and record the moderation outcome.`}
                    </DialogDescription>
                </DialogHeader>
                <div className="space-y-2">
                    <Label htmlFor="trust-decision-note">
                        {isVerification ? 'Review note' : 'Resolution note'}
                    </Label>
                    <Textarea
                        id="trust-decision-note"
                        value={note}
                        onChange={(event) => setNote(event.target.value)}
                        placeholder={isVerification ? 'Record the reason for this decision…' : 'Record what was reviewed and why…'}
                        maxLength={2000}
                        disabled={busy}
                    />
                    <p className="text-xs text-muted-foreground">
                        Required by the Trust Desk API.
                        {isVerification && isReject ? ' This note is emailed to the applicant.' : ''}
                    </p>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
                    <Button
                        variant={isReject || decision?.action === 'dismissed' ? 'destructive' : 'default'}
                        onClick={onConfirm}
                        disabled={busy || !note.trim()}
                    >
                        {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                        {isVerification ? `${actionLabel} application` : `${actionLabel} report`}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}

function VerificationsTab({ setMessage }) {
    const [verifications, setVerifications] = useState([])
    const [status, setStatus] = useState('pending')
    const [loading, setLoading] = useState(true)
    const [reloadKey, setReloadKey] = useState(0)
    const [decision, setDecision] = useState(null)
    const [note, setNote] = useState('')
    const [busy, setBusy] = useState(false)

    useEffect(() => {
        let cancelled = false
        APIService.adminListScoutVerifications({ status })
            .then((data) => { if (!cancelled) setVerifications(data?.verifications || []) })
            .catch((error) => {
                if (!cancelled) setMessage({ type: 'error', text: error.message || 'Failed to load verifications' })
            })
            .finally(() => { if (!cancelled) setLoading(false) })
        return () => { cancelled = true }
    }, [reloadKey, setMessage, status])

    const openDecision = (verification, action) => {
        setNote('')
        setDecision({ kind: 'verification', item: verification, action })
    }

    const submitDecision = async () => {
        if (!decision || !note.trim()) return
        setBusy(true)
        try {
            await APIService.adminReviewScoutVerification(decision.item.id, {
                action: decision.action,
                review_notes: note.trim(),
            })
            const outcome = decision.action === 'approve' ? 'approved' : 'rejected'
            setMessage({ type: 'success', text: `${decision.item.full_name}'s application was ${outcome}.` })
            setDecision(null)
            setNote('')
            setLoading(true)
            setReloadKey((key) => key + 1)
        } catch (error) {
            setMessage({ type: 'error', text: error.message || 'Failed to review verification' })
        } finally {
            setBusy(false)
        }
    }

    return (
        <>
            <Card>
                <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                        <CardTitle>Scout verifications</CardTitle>
                        <CardDescription>Review identity, role and professional evidence before granting scout access</CardDescription>
                    </div>
                    <Select value={status} onValueChange={(value) => { setLoading(true); setStatus(value) }}>
                        <SelectTrigger className="w-44" aria-label="Verification status">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="pending">Pending</SelectItem>
                            <SelectItem value="approved">Approved</SelectItem>
                            <SelectItem value="rejected">Rejected</SelectItem>
                            <SelectItem value="revoked">Revoked</SelectItem>
                            <SelectItem value="all">All</SelectItem>
                        </SelectContent>
                    </Select>
                </CardHeader>
                <CardContent>
                    {loading ? (
                        <Loading label="Loading verification queue…" />
                    ) : verifications.length === 0 ? (
                        <p className="py-10 text-center text-sm text-muted-foreground">No {status === 'all' ? '' : status} verification applications.</p>
                    ) : (
                        <div className="space-y-3">
                            {verifications.map((verification) => (
                                <div key={verification.id} className="rounded-lg border bg-card p-4">
                                    <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                                        <div className="min-w-0 flex-1 space-y-1">
                                            <div className="flex flex-wrap items-center gap-2">
                                                <StatusBadge status={verification.status} />
                                                <Badge variant="outline">{verification.role_title || 'Role not provided'}</Badge>
                                            </div>
                                            <p className="font-medium text-foreground">{verification.full_name}</p>
                                            <p className="text-sm text-muted-foreground">
                                                {verification.user_email || 'No email'} · {verification.organization || 'No organization'}
                                            </p>
                                            <p className="text-xs text-muted-foreground">Submitted {formatDate(verification.submitted_at)}</p>
                                        </div>
                                        {verification.status === 'pending' ? (
                                            <div className="flex shrink-0 flex-wrap gap-2">
                                                <Button size="sm" onClick={() => openDecision(verification, 'approve')}>
                                                    <Check className="mr-1.5 h-4 w-4" /> Approve
                                                </Button>
                                                <Button size="sm" variant="destructive" onClick={() => openDecision(verification, 'reject')}>
                                                    <X className="mr-1.5 h-4 w-4" /> Reject
                                                </Button>
                                            </div>
                                        ) : null}
                                    </div>
                                    <details className="mt-4 rounded-md border border-border/70 bg-secondary/30 px-3 py-2 text-sm">
                                        <summary className="cursor-pointer font-medium">Application detail</summary>
                                        <div className="mt-3 space-y-3 border-t pt-3">
                                            <div>
                                                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Statement</p>
                                                <p className="mt-1 whitespace-pre-wrap text-foreground">{verification.statement || 'No statement supplied.'}</p>
                                            </div>
                                            <div>
                                                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Evidence</p>
                                                {verification.evidence_urls?.length ? (
                                                    <ul className="mt-1 space-y-1">
                                                        {verification.evidence_urls.map((url) => (
                                                            <li key={url}>
                                                                <a className="inline-flex max-w-full items-center gap-1 break-all text-primary hover:underline" href={url} target="_blank" rel="noopener noreferrer">
                                                                    {url}<ExternalLink className="h-3.5 w-3.5 shrink-0" />
                                                                </a>
                                                            </li>
                                                        ))}
                                                    </ul>
                                                ) : <p className="mt-1 text-muted-foreground">No evidence links supplied.</p>}
                                            </div>
                                            {verification.review_notes ? (
                                                <div>
                                                    <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Review note</p>
                                                    <p className="mt-1 whitespace-pre-wrap">{verification.review_notes}</p>
                                                </div>
                                            ) : null}
                                        </div>
                                    </details>
                                </div>
                            ))}
                        </div>
                    )}
                </CardContent>
            </Card>
            <DecisionDialog
                decision={decision}
                note={note}
                setNote={setNote}
                busy={busy}
                onClose={() => { setDecision(null); setNote('') }}
                onConfirm={submitDecision}
            />
        </>
    )
}

function ReportsTab({ setMessage }) {
    const [reports, setReports] = useState([])
    const [status, setStatus] = useState('open')
    const [loading, setLoading] = useState(true)
    const [reloadKey, setReloadKey] = useState(0)
    const [decision, setDecision] = useState(null)
    const [note, setNote] = useState('')
    const [busy, setBusy] = useState(false)

    useEffect(() => {
        let cancelled = false
        APIService.adminListContentReports({ status })
            .then((data) => { if (!cancelled) setReports(data?.reports || []) })
            .catch((error) => {
                if (!cancelled) setMessage({ type: 'error', text: error.message || 'Failed to load reports' })
            })
            .finally(() => { if (!cancelled) setLoading(false) })
        return () => { cancelled = true }
    }, [reloadKey, setMessage, status])

    const openDecision = (report, action) => {
        setNote('')
        setDecision({ kind: 'report', item: report, action })
    }

    const submitDecision = async () => {
        if (!decision || !note.trim()) return
        setBusy(true)
        try {
            await APIService.adminResolveContentReport(decision.item.id, {
                status: decision.action,
                resolution_notes: note.trim(),
            })
            setMessage({ type: 'success', text: `Report #${decision.item.id} was ${decision.action}.` })
            setDecision(null)
            setNote('')
            setLoading(true)
            setReloadKey((key) => key + 1)
        } catch (error) {
            setMessage({ type: 'error', text: error.message || 'Failed to update report' })
        } finally {
            setBusy(false)
        }
    }

    return (
        <>
            <Card>
                <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                        <CardTitle>Content reports</CardTitle>
                        <CardDescription>Review reported profiles, showcase content, programs and conversations</CardDescription>
                    </div>
                    <Select value={status} onValueChange={(value) => { setLoading(true); setStatus(value) }}>
                        <SelectTrigger className="w-44" aria-label="Report status">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="open">Open</SelectItem>
                            <SelectItem value="reviewing">Reviewing</SelectItem>
                            <SelectItem value="resolved">Resolved</SelectItem>
                            <SelectItem value="dismissed">Dismissed</SelectItem>
                            <SelectItem value="all">All</SelectItem>
                        </SelectContent>
                    </Select>
                </CardHeader>
                <CardContent>
                    {loading ? (
                        <Loading label="Loading report queue…" />
                    ) : reports.length === 0 ? (
                        <p className="py-10 text-center text-sm text-muted-foreground">No {status === 'all' ? '' : status} reports.</p>
                    ) : (
                        <div className="space-y-3">
                            {reports.map((report) => {
                                const target = report.target || {}
                                const reporter = report.reporter || {}
                                const actionable = !['resolved', 'dismissed'].includes(report.status)
                                return (
                                    <div key={report.id} className="rounded-lg border bg-card p-4">
                                        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                                            <div className="min-w-0 flex-1 space-y-2">
                                                <div className="flex flex-wrap items-center gap-2">
                                                    <StatusBadge status={report.status} />
                                                    <Badge variant="outline">{title(report.reason || report.reason_code)}</Badge>
                                                    <Badge variant="secondary">{title(target.content_type || report.subject_type)}</Badge>
                                                </div>
                                                <p className="text-sm font-medium text-foreground">
                                                    Target {target.id || report.subject_id || '—'}
                                                </p>
                                                {target.excerpt ? (
                                                    <blockquote className="border-l-2 border-primary/40 pl-3 text-sm text-muted-foreground">“{target.excerpt}”</blockquote>
                                                ) : null}
                                                {report.details ? <p className="whitespace-pre-wrap text-sm text-muted-foreground">{report.details}</p> : null}
                                                <p className="text-xs text-muted-foreground">
                                                    Reported by {reporter.display_name || reporter.email || `account #${reporter.account_id || report.reporter_user_id || '—'}`}
                                                    {reporter.display_name && reporter.email ? ` · ${reporter.email}` : ''}
                                                    {' · '}{formatDate(report.created_at)}
                                                </p>
                                            </div>
                                            {actionable ? (
                                                <div className="flex shrink-0 flex-wrap gap-2">
                                                    <Button size="sm" onClick={() => openDecision(report, 'resolved')}>
                                                        <Check className="mr-1.5 h-4 w-4" /> Resolve
                                                    </Button>
                                                    <Button size="sm" variant="outline" onClick={() => openDecision(report, 'dismissed')}>
                                                        <X className="mr-1.5 h-4 w-4" /> Dismiss
                                                    </Button>
                                                </div>
                                            ) : null}
                                        </div>
                                        {report.resolution_notes ? (
                                            <div className="mt-3 rounded-md bg-secondary/50 p-3 text-sm">
                                                <span className="font-medium">Resolution note: </span>{report.resolution_notes}
                                            </div>
                                        ) : null}
                                    </div>
                                )
                            })}
                        </div>
                    )}
                </CardContent>
            </Card>
            <DecisionDialog
                decision={decision}
                note={note}
                setNote={setNote}
                busy={busy}
                onClose={() => { setDecision(null); setNote('') }}
                onConfirm={submitDecision}
            />
        </>
    )
}

function Participant({ label, participant }) {
    return (
        <div className="rounded-md border bg-secondary/30 p-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{label}</p>
            <p className="mt-1 text-sm font-medium">{participant?.display_name || 'Not included'}</p>
            {participant?.user_id ? <p className="text-xs text-muted-foreground">User #{participant.user_id}</p> : null}
            {participant?.club_program_id ? <p className="text-xs text-muted-foreground">Program #{participant.club_program_id}</p> : null}
        </div>
    )
}

function ContactDetailDialog({ requestId, onClose, setMessage }) {
    const [request, setRequest] = useState(null)

    useEffect(() => {
        if (!requestId) return undefined
        let cancelled = false
        APIService.adminGetContactRequest(requestId)
            .then((data) => { if (!cancelled) setRequest(data?.request || null) })
            .catch((error) => {
                if (!cancelled) {
                    setMessage({ type: 'error', text: error.message || 'Failed to load contact request' })
                    onClose()
                }
            })
        return () => { cancelled = true }
    }, [onClose, requestId, setMessage])

    return (
        <Dialog open={Boolean(requestId)} onOpenChange={(open) => { if (!open) onClose() }}>
            <DialogContent className="sm:max-w-3xl">
                <DialogHeader>
                    <DialogTitle>Contact request {requestId}</DialogTitle>
                    <DialogDescription>Read-only participant, consent and audit history.</DialogDescription>
                </DialogHeader>
                {!request ? (
                    <Loading label="Loading contact request…" />
                ) : (
                    <div className="space-y-5">
                        <div className="flex flex-wrap gap-2">
                            <StatusBadge status={request.status} />
                            <Badge className={ROUTING_COLORS[request.routing_mode] || ROUTING_COLORS.direct}>{title(request.routing_mode)}</Badge>
                            {request.status_contradiction ? <Badge variant="destructive">Contradiction</Badge> : null}
                            <Badge variant="outline">Messaging {request.messaging_open ? 'open' : 'closed'}</Badge>
                        </div>

                        <section>
                            <h3 className="mb-2 text-sm font-semibold">Participants</h3>
                            <div className="grid gap-2 sm:grid-cols-3">
                                <Participant label="Scout" participant={request.participants?.scout} />
                                <Participant label="Player" participant={request.participants?.player} />
                                <Participant label="Club" participant={request.participants?.club} />
                            </div>
                        </section>

                        <section>
                            <h3 className="mb-2 text-sm font-semibold">Request message</h3>
                            <div className="whitespace-pre-wrap rounded-md border bg-secondary/30 p-3 text-sm">{request.message || 'No message supplied.'}</div>
                        </section>

                        <div className="grid gap-4 sm:grid-cols-2">
                            <section className="rounded-md border p-3">
                                <h3 className="text-sm font-semibold">Permission attestation</h3>
                                <p className="mt-1 text-sm">{request.permission_attestation ? 'Attested' : 'Not attested'}</p>
                                <p className="text-xs text-muted-foreground">{formatDate(request.permission_attested_at, true)}</p>
                            </section>
                            <section className="rounded-md border p-3">
                                <h3 className="text-sm font-semibold">Club consent</h3>
                                <div className="mt-1"><StatusBadge status={request.club_consent_status} /></div>
                                <p className="mt-1 text-xs text-muted-foreground">{formatDate(request.club_consent_at, true)}</p>
                                {request.club_consent_note ? <p className="mt-2 whitespace-pre-wrap text-sm">{request.club_consent_note}</p> : null}
                            </section>
                        </div>

                        <section>
                            <h3 className="mb-2 text-sm font-semibold">Latest outcome</h3>
                            {request.latest_outcome ? (
                                <div className="rounded-md border bg-secondary/30 p-3 text-sm">
                                    <div className="flex flex-wrap items-center justify-between gap-2">
                                        <span className="font-medium">{title(request.latest_outcome.stage)}</span>
                                        <span className="text-xs text-muted-foreground">{formatDate(request.latest_outcome.occurred_at, true)}</span>
                                    </div>
                                    {request.latest_outcome.notes ? <p className="mt-2 whitespace-pre-wrap">{request.latest_outcome.notes}</p> : null}
                                </div>
                            ) : <p className="text-sm text-muted-foreground">No outcome recorded.</p>}
                        </section>

                        <section>
                            <h3 className="mb-3 text-sm font-semibold">Audit timeline</h3>
                            {request.audit_events?.length ? (
                                <ol className="space-y-4 border-l border-border pl-4">
                                    {request.audit_events.map((event, index) => (
                                        <li key={`${event.event_type}-${event.created_at}-${index}`} className="relative">
                                            <span className="absolute -left-[1.31rem] top-1 h-2 w-2 rounded-full bg-primary ring-4 ring-background" />
                                            <div className="flex flex-wrap items-baseline justify-between gap-2">
                                                <p className="text-sm font-medium">{title(event.event_type)}</p>
                                                <time className="text-xs text-muted-foreground">{formatDate(event.created_at, true)}</time>
                                            </div>
                                            <pre className="mt-2 max-w-full overflow-x-auto whitespace-pre-wrap break-words rounded-md bg-slate-950 p-3 text-xs text-slate-100">{JSON.stringify(event.metadata ?? {}, null, 2)}</pre>
                                        </li>
                                    ))}
                                </ol>
                            ) : <p className="text-sm text-muted-foreground">No audit events recorded.</p>}
                        </section>
                    </div>
                )}
            </DialogContent>
        </Dialog>
    )
}

function ContactOversightTab({ setMessage }) {
    const [requests, setRequests] = useState([])
    const [status, setStatus] = useState('all')
    const [routingMode, setRoutingMode] = useState('all')
    const [contradictionOnly, setContradictionOnly] = useState(false)
    const [page, setPage] = useState(1)
    const [pages, setPages] = useState(0)
    const [total, setTotal] = useState(0)
    const [loading, setLoading] = useState(true)
    const [selectedId, setSelectedId] = useState(null)

    useEffect(() => {
        let cancelled = false
        const params = { page, per_page: 25 }
        if (status !== 'all') params.status = status
        if (routingMode !== 'all') params.routing_mode = routingMode
        if (contradictionOnly) params.contradiction = 'true'
        APIService.adminListContactRequests(params)
            .then((data) => {
                if (cancelled) return
                setRequests(data?.requests || [])
                setPages(data?.pages || 0)
                setTotal(data?.total || 0)
            })
            .catch((error) => {
                if (!cancelled) setMessage({ type: 'error', text: error.message || 'Failed to load contact requests' })
            })
            .finally(() => { if (!cancelled) setLoading(false) })
        return () => { cancelled = true }
    }, [contradictionOnly, page, routingMode, setMessage, status])

    const updateStatus = (value) => { setLoading(true); setStatus(value); setPage(1) }
    const updateRoutingMode = (value) => { setLoading(true); setRoutingMode(value); setPage(1) }
    const toggleContradictions = () => { setLoading(true); setContradictionOnly((current) => !current); setPage(1) }
    const selectRow = (event, id) => {
        if (event.type === 'keydown' && event.key !== 'Enter' && event.key !== ' ') return
        if (event.type === 'keydown') event.preventDefault()
        setSelectedId(id)
    }

    return (
        <>
            <Card>
                <CardHeader>
                    <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
                        <div>
                            <CardTitle>Contact oversight</CardTitle>
                            <CardDescription>Read-only visibility into routing, consent and message activity</CardDescription>
                        </div>
                        <div className="flex flex-wrap items-end gap-2">
                            <div className="space-y-1">
                                <Label className="text-xs" htmlFor="contact-status-filter">Status</Label>
                                <Select value={status} onValueChange={updateStatus}>
                                    <SelectTrigger id="contact-status-filter" className="w-40">
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="all">All statuses</SelectItem>
                                        <SelectItem value="pending">Pending</SelectItem>
                                        <SelectItem value="accepted">Accepted</SelectItem>
                                        <SelectItem value="declined">Declined</SelectItem>
                                        <SelectItem value="withdrawn">Withdrawn</SelectItem>
                                        <SelectItem value="expired">Expired</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                            <div className="space-y-1">
                                <Label className="text-xs" htmlFor="contact-routing-filter">Routing mode</Label>
                                <Select value={routingMode} onValueChange={updateRoutingMode}>
                                    <SelectTrigger id="contact-routing-filter" className="w-44">
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="all">All routing</SelectItem>
                                        <SelectItem value="direct">Direct</SelectItem>
                                        <SelectItem value="club_notified">Club notified</SelectItem>
                                        <SelectItem value="club_included">Club included</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                            <Button
                                variant={contradictionOnly ? 'destructive' : 'outline'}
                                onClick={toggleContradictions}
                                aria-pressed={contradictionOnly}
                            >
                                <ShieldAlert className="mr-1.5 h-4 w-4" />
                                Contradictions only
                            </Button>
                        </div>
                    </div>
                </CardHeader>
                <CardContent className="space-y-4">
                    {loading ? (
                        <Loading label="Loading contact requests…" />
                    ) : requests.length === 0 ? (
                        <p className="py-10 text-center text-sm text-muted-foreground">No contact requests match these filters.</p>
                    ) : (
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Created</TableHead>
                                    <TableHead>Scout</TableHead>
                                    <TableHead>Player</TableHead>
                                    <TableHead>Routing</TableHead>
                                    <TableHead>Status</TableHead>
                                    <TableHead>Consent</TableHead>
                                    <TableHead className="text-right">Messages</TableHead>
                                    <TableHead>Last activity</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {requests.map((request) => (
                                    <TableRow
                                        key={request.id}
                                        className="cursor-pointer focus-visible:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                                        tabIndex={0}
                                        onClick={(event) => selectRow(event, request.id)}
                                        onKeyDown={(event) => selectRow(event, request.id)}
                                        aria-label={`Open contact request for ${request.player_name}`}
                                    >
                                        <TableCell>{formatDate(request.created_at)}</TableCell>
                                        <TableCell className="whitespace-normal">
                                            <p className="font-medium">{request.scout?.name || `Account #${request.scout?.account_id || '—'}`}</p>
                                            {request.scout?.organization ? <p className="text-xs text-muted-foreground">{request.scout.organization}</p> : null}
                                        </TableCell>
                                        <TableCell className="whitespace-normal">
                                            <p className="font-medium">{request.player_name || `Player #${request.player_api_id}`}</p>
                                            {request.status_contradiction ? (
                                                <Badge variant="destructive" className="mt-1">
                                                    <ShieldAlert className="mr-1 h-3 w-3" /> Contradiction
                                                </Badge>
                                            ) : null}
                                        </TableCell>
                                        <TableCell>
                                            <Badge className={ROUTING_COLORS[request.routing_mode] || ROUTING_COLORS.direct}>{title(request.routing_mode)}</Badge>
                                        </TableCell>
                                        <TableCell><StatusBadge status={request.status} /></TableCell>
                                        <TableCell><StatusBadge status={request.club_consent_status} /></TableCell>
                                        <TableCell className="text-right tabular-nums">{request.message_count ?? 0}</TableCell>
                                        <TableCell>{formatDate(request.last_activity, true)}</TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    )}

                    <div className="flex flex-col gap-2 border-t pt-4 sm:flex-row sm:items-center sm:justify-between">
                        <p className="text-sm text-muted-foreground">{total.toLocaleString()} request{total === 1 ? '' : 's'}</p>
                        <div className="flex items-center gap-2">
                            <Button variant="outline" size="sm" disabled={loading || page <= 1} onClick={() => { setLoading(true); setPage((current) => current - 1) }}>
                                <ChevronLeft className="mr-1 h-4 w-4" /> Previous
                            </Button>
                            <span className="min-w-24 text-center text-sm text-muted-foreground">Page {page} of {Math.max(pages, 1)}</span>
                            <Button variant="outline" size="sm" disabled={loading || pages === 0 || page >= pages} onClick={() => { setLoading(true); setPage((current) => current + 1) }}>
                                Next <ChevronRight className="ml-1 h-4 w-4" />
                            </Button>
                        </div>
                    </div>
                </CardContent>
            </Card>
            <ContactDetailDialog key={selectedId || 'closed'} requestId={selectedId} onClose={() => setSelectedId(null)} setMessage={setMessage} />
        </>
    )
}

export function AdminTrust() {
    const [message, setMessage] = useState(null)
    const [tab, setTab] = useState('verifications')

    return (
        <div className="space-y-6">
            <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10">
                    <ShieldCheck className="h-5 w-5 text-primary" />
                </div>
                <div>
                    <h2 className="text-3xl font-bold tracking-tight">Trust Desk</h2>
                    <p className="text-muted-foreground">Identity review, content safety and contact-route oversight</p>
                </div>
            </div>

            {message ? (
                <Alert className={message.type === 'error' ? 'border-rose-500 bg-rose-50' : 'border-emerald-500 bg-emerald-50'}>
                    {message.type === 'error'
                        ? <AlertCircle className="h-4 w-4 text-rose-600" />
                        : <CheckCircle2 className="h-4 w-4 text-emerald-600" />}
                    <AlertDescription className={message.type === 'error' ? 'text-rose-800' : 'text-emerald-800'}>
                        {message.text}
                    </AlertDescription>
                </Alert>
            ) : null}

            <Tabs value={tab} onValueChange={setTab}>
                <TabsList className="h-auto flex-wrap justify-start">
                    <TabsTrigger value="verifications">
                        <ClipboardCheck className="mr-1.5 h-4 w-4" /> Verifications
                    </TabsTrigger>
                    <TabsTrigger value="reports">
                        <FileWarning className="mr-1.5 h-4 w-4" /> Reports
                    </TabsTrigger>
                    <TabsTrigger value="contact">
                        <MessagesSquare className="mr-1.5 h-4 w-4" /> Contact oversight
                    </TabsTrigger>
                </TabsList>

                <TabsContent value="verifications" className="mt-4">
                    {tab === 'verifications' ? <VerificationsTab setMessage={setMessage} /> : null}
                </TabsContent>
                <TabsContent value="reports" className="mt-4">
                    {tab === 'reports' ? <ReportsTab setMessage={setMessage} /> : null}
                </TabsContent>
                <TabsContent value="contact" className="mt-4">
                    {tab === 'contact' ? <ContactOversightTab setMessage={setMessage} /> : null}
                </TabsContent>
            </Tabs>
        </div>
    )
}

export default AdminTrust
