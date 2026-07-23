import { useState, useEffect, useCallback, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { APIService } from '@/lib/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'
import {
    AlertCircle,
    CheckCircle2,
    Loader2,
    Check,
    X,
    Undo2,
    Search,
    Film,
    Star,
    Inbox,
    UserSquare,
    Link2,
    Image as ImageIcon,
    RefreshCw,
    GitMerge,
} from 'lucide-react'

const CLAIM_STATUS_COLORS = {
    pending: 'bg-amber-50 text-amber-800 border-amber-200',
    approved: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    rejected: 'bg-rose-50 text-rose-800 border-rose-200',
    revoked: 'bg-stone-100 text-stone-700 border-stone-200',
}

const VERIFICATION_STATUS = {
    unverified: {
        label: 'Unverified',
        className: 'bg-amber-50 text-amber-800 border-amber-200',
    },
    code_found: {
        label: 'Code detected',
        className: 'bg-emerald-50 text-emerald-800 border-emerald-300',
    },
    code_not_found: {
        label: 'Code not found',
        className: 'bg-rose-50 text-rose-800 border-rose-200',
    },
}

const IDENTITY_COLORS = {
    human_confirmed: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    high: 'bg-sky-50 text-sky-800 border-sky-200',
    low: 'bg-amber-50 text-amber-800 border-amber-200',
    unverified: 'bg-stone-100 text-stone-700 border-stone-200',
}

const LOCAL_PLAYER_STATUS_COLORS = {
    pending: 'bg-amber-50 text-amber-800 border-amber-200',
    approved: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    rejected: 'bg-rose-50 text-rose-800 border-rose-200',
    merged: 'bg-stone-100 text-stone-700 border-stone-200',
}

const RELATIONSHIP_LABELS = {
    player: 'Player',
    agent: 'Agent',
    guardian: 'Parent / Guardian',
    club_official: 'Club official',
}

const CONTRACT_STATUS_LABELS = {
    under_contract: 'Under contract',
    expiring: 'Contract expiring',
    free_agent: 'Free agent',
}

const AVAILABILITY_LABELS = {
    open_to_moves: 'Open to moves',
    not_looking: 'Not looking',
    trial_available: 'Available for trials',
}

function formatDate(value) {
    if (!value) return null
    const d = new Date(value)
    if (Number.isNaN(d.getTime())) return null
    return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

function formatDateOnly(value) {
    if (!value) return null
    const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})/)
    if (!match) return formatDate(value)
    const d = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]))
    return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

function formatBytes(value) {
    const bytes = Number(value)
    if (!Number.isFinite(bytes) || bytes < 0) return 'Size unavailable'
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(bytes < 10 * 1024 ? 1 : 0)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(bytes < 10 * 1024 * 1024 ? 1 : 0)} MB`
}

function asArray(data, ...keys) {
    if (Array.isArray(data)) return data
    for (const k of keys) {
        if (Array.isArray(data?.[k])) return data[k]
    }
    return []
}

function Loading() {
    return (
        <div className="flex items-center justify-center py-12">
            <Loader2 className="mr-2 h-5 w-5 animate-spin text-muted-foreground/70" />
            <span className="text-sm text-muted-foreground">Loading…</span>
        </div>
    )
}

function localPlayerLocation(player) {
    return [player.city, player.country].filter(Boolean).join(', ') || 'Location not provided'
}

// ---------------------------------------------------------------------------
// Claims
// ---------------------------------------------------------------------------

function ClaimsTab({ setMessage }) {
    const [claims, setClaims] = useState([])
    const [loading, setLoading] = useState(true)
    const [status, setStatus] = useState('pending')
    const [reloadKey, setReloadKey] = useState(0)
    const [actingId, setActingId] = useState(null)

    useEffect(() => {
        let cancelled = false
        setLoading(true)
        const params = status === 'all' ? {} : { status }
        APIService.adminListShowcaseClaims(params)
            .then((data) => { if (!cancelled) setClaims(asArray(data, 'claims')) })
            .catch((err) => {
                if (!cancelled) setMessage({ type: 'error', text: err.message || 'Failed to load claims' })
            })
            .finally(() => { if (!cancelled) setLoading(false) })
        return () => { cancelled = true }
    }, [status, reloadKey, setMessage])

    const act = async (claim, action) => {
        setActingId(claim.id)
        try {
            await APIService.adminReviewShowcaseClaim(claim.id, { action })
            setMessage({ type: 'success', text: `Claim ${action}d` })
            setReloadKey((k) => k + 1)
        } catch (err) {
            setMessage({ type: 'error', text: err.message || 'Failed to update claim' })
        } finally {
            setActingId(null)
        }
    }

    const recheckProof = async (claim) => {
        setActingId(claim.id)
        try {
            await APIService.adminRecheckClaim(claim.id)
            setMessage({ type: 'success', text: 'Social profile check refreshed' })
            setReloadKey((k) => k + 1)
        } catch (err) {
            setMessage({ type: 'error', text: err.message || 'Failed to re-check social profile' })
        } finally {
            setActingId(null)
        }
    }

    return (
        <Card>
            <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                    <CardTitle>Profile claims</CardTitle>
                    <CardDescription>Players, agents and guardians requesting ownership of a profile</CardDescription>
                </div>
                <Select value={status} onValueChange={setStatus}>
                    <SelectTrigger className="w-40">
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
                    <Loading />
                ) : claims.length === 0 ? (
                    <p className="py-8 text-center text-sm text-muted-foreground">No {status === 'all' ? '' : status} claims.</p>
                ) : (
                    <div className="space-y-3">
                        {claims.map((claim) => {
                            const claimant = claim.claimant_display_name || claim.claimant_email || claim.user_email || `User #${claim.user_account_id ?? '—'}`
                            const verification = VERIFICATION_STATUS[claim.verification_status] || VERIFICATION_STATUS.unverified
                            return (
                                <div key={claim.id} className="flex flex-col justify-between gap-4 rounded-lg border bg-card p-4 sm:flex-row sm:items-start">
                                    <div className="min-w-0 flex-1 space-y-1">
                                        <div className="flex flex-wrap items-center gap-2">
                                            <Badge className={CLAIM_STATUS_COLORS[claim.status] || CLAIM_STATUS_COLORS.revoked}>
                                                {claim.status}
                                            </Badge>
                                            <Badge variant="secondary">{RELATIONSHIP_LABELS[claim.relationship_type] || claim.relationship_type}</Badge>
                                            <Badge variant="outline">
                                                {claim.player_name ? claim.player_name : `Player #${claim.player_api_id}`}
                                                {claim.player_name ? ` · #${claim.player_api_id}` : ''}
                                            </Badge>
                                        </div>
                                        <p className="text-sm font-medium text-foreground">{claimant}</p>
                                        {claim.message && (
                                            <p className="text-sm text-muted-foreground">“{claim.message}”</p>
                                        )}
                                        {formatDate(claim.created_at) && (
                                            <p className="text-xs text-muted-foreground">Submitted {formatDate(claim.created_at)}</p>
                                        )}
                                        <div className="mt-3 rounded-md border border-border/70 bg-secondary/30 p-3">
                                            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                                                <div className="flex flex-wrap items-center gap-2">
                                                    <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                                                        Social profile check
                                                    </span>
                                                    <Badge className={verification.className}>{verification.label}</Badge>
                                                </div>
                                                <Button
                                                    size="sm"
                                                    variant="outline"
                                                    className="self-start sm:self-auto"
                                                    disabled={!claim.verification_proof_url || actingId === claim.id}
                                                    onClick={() => recheckProof(claim)}
                                                    title={claim.verification_proof_url ? 'Run the automated check again' : 'No proof URL has been submitted'}
                                                >
                                                    {actingId === claim.id ? (
                                                        <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                                                    ) : (
                                                        <RefreshCw className="mr-1 h-4 w-4" />
                                                    )}
                                                    Re-check
                                                </Button>
                                            </div>
                                            <dl className="mt-3 grid gap-x-6 gap-y-2 text-xs sm:grid-cols-2">
                                                <div>
                                                    <dt className="text-muted-foreground">Verification code</dt>
                                                    <dd className="mt-0.5 font-mono font-semibold tracking-wide text-foreground">
                                                        {claim.verification_code || '—'}
                                                    </dd>
                                                </div>
                                                <div>
                                                    <dt className="text-muted-foreground">Last checked</dt>
                                                    <dd className="mt-0.5 text-foreground">
                                                        {formatDate(claim.verification_checked_at) || 'Not checked yet'}
                                                    </dd>
                                                </div>
                                                <div className="sm:col-span-2">
                                                    <dt className="text-muted-foreground">Public profile</dt>
                                                    <dd className="mt-0.5 min-w-0">
                                                        {claim.verification_proof_url ? (
                                                            <a
                                                                href={claim.verification_proof_url}
                                                                target="_blank"
                                                                rel="noreferrer"
                                                                className="break-all font-medium text-primary hover:underline"
                                                            >
                                                                {claim.verification_proof_url}
                                                            </a>
                                                        ) : (
                                                            <span className="text-foreground">No profile URL submitted</span>
                                                        )}
                                                    </dd>
                                                </div>
                                                {claim.verification_note && (
                                                    <div className="sm:col-span-2">
                                                        <dt className="text-muted-foreground">Check note</dt>
                                                        <dd className="mt-0.5 text-foreground">{claim.verification_note}</dd>
                                                    </div>
                                                )}
                                            </dl>
                                        </div>
                                    </div>
                                    <div className="flex shrink-0 items-center gap-2">
                                        {claim.status === 'pending' && (
                                            <>
                                                <Button size="sm" variant="outline" className="border-emerald-600 text-emerald-600 hover:bg-emerald-50" disabled={actingId === claim.id} onClick={() => act(claim, 'approve')}>
                                                    {actingId === claim.id ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Check className="mr-1 h-4 w-4" />}
                                                    Approve
                                                </Button>
                                                <Button size="sm" variant="outline" className="border-rose-600 text-rose-600 hover:bg-rose-50" disabled={actingId === claim.id} onClick={() => act(claim, 'reject')}>
                                                    <X className="mr-1 h-4 w-4" />
                                                    Reject
                                                </Button>
                                            </>
                                        )}
                                        {claim.status === 'approved' && (
                                            <Button size="sm" variant="outline" className="border-stone-400 text-stone-600 hover:bg-stone-50" disabled={actingId === claim.id} onClick={() => act(claim, 'revoke')}>
                                                {actingId === claim.id ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Undo2 className="mr-1 h-4 w-4" />}
                                                Revoke
                                            </Button>
                                        )}
                                        {(claim.status === 'rejected' || claim.status === 'revoked') && (
                                            <Button size="sm" variant="outline" className="border-emerald-600 text-emerald-600 hover:bg-emerald-50" disabled={actingId === claim.id} onClick={() => act(claim, 'approve')}>
                                                {actingId === claim.id ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Check className="mr-1 h-4 w-4" />}
                                                Approve
                                            </Button>
                                        )}
                                    </div>
                                </div>
                            )
                        })}
                    </div>
                )}
            </CardContent>
        </Card>
    )
}

// ---------------------------------------------------------------------------
// Profile edits
// ---------------------------------------------------------------------------

function ProfilesTab({ setMessage }) {
    const [profiles, setProfiles] = useState([])
    const [loading, setLoading] = useState(true)
    const [status, setStatus] = useState('pending')
    const [reloadKey, setReloadKey] = useState(0)
    const [actingId, setActingId] = useState(null)

    useEffect(() => {
        let cancelled = false
        setLoading(true)
        APIService.adminListShowcaseProfiles({ status })
            .then((data) => { if (!cancelled) setProfiles(asArray(data, 'profiles')) })
            .catch((err) => {
                if (!cancelled) setMessage({ type: 'error', text: err.message || 'Failed to load profiles' })
            })
            .finally(() => { if (!cancelled) setLoading(false) })
        return () => { cancelled = true }
    }, [status, reloadKey, setMessage])

    const act = async (profile, action) => {
        setActingId(profile.id)
        try {
            await APIService.adminReviewShowcaseProfile(profile.player_api_id, { action })
            setMessage({ type: 'success', text: `Profile ${action}d` })
            setReloadKey((k) => k + 1)
        } catch (err) {
            setMessage({ type: 'error', text: err.message || 'Failed to update profile' })
        } finally {
            setActingId(null)
        }
    }

    return (
        <Card>
            <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                    <CardTitle>Profile edits</CardTitle>
                    <CardDescription>Self-reported profile and availability details awaiting review</CardDescription>
                </div>
                <Select value={status} onValueChange={setStatus}>
                    <SelectTrigger className="w-40">
                        <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="pending">Pending</SelectItem>
                        <SelectItem value="approved">Approved</SelectItem>
                    </SelectContent>
                </Select>
            </CardHeader>
            <CardContent>
                {loading ? (
                    <Loading />
                ) : profiles.length === 0 ? (
                    <p className="py-8 text-center text-sm text-muted-foreground">No {status} profile edits.</p>
                ) : (
                    <div className="space-y-3">
                        {profiles.map((profile) => (
                            <div key={profile.id} className="flex flex-col justify-between gap-4 rounded-lg border bg-card p-4 sm:flex-row sm:items-start">
                                <div className="min-w-0 flex-1 space-y-2">
                                    <div className="flex flex-wrap items-center gap-2">
                                        <Badge className={CLAIM_STATUS_COLORS[profile.status] || CLAIM_STATUS_COLORS.revoked}>{profile.status}</Badge>
                                        <Badge variant="outline">
                                            {profile.player_name ? `${profile.player_name} · #${profile.player_api_id}` : `Player #${profile.player_api_id}`}
                                        </Badge>
                                    </div>
                                    {profile.bio && <p className="text-sm text-foreground/90">{profile.bio}</p>}
                                    <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
                                        {profile.positions && <span>Positions: <span className="text-foreground">{profile.positions}</span></span>}
                                        {profile.preferred_foot && <span>Foot: <span className="capitalize text-foreground">{profile.preferred_foot}</span></span>}
                                        {profile.height_cm != null && <span>Height: <span className="text-foreground">{profile.height_cm} cm</span></span>}
                                        {profile.contract_status && <span>Contract: <span className="text-foreground">{CONTRACT_STATUS_LABELS[profile.contract_status] || profile.contract_status}</span></span>}
                                        {profile.contract_until && <span>Contract until: <span className="text-foreground">{formatDateOnly(profile.contract_until)}</span></span>}
                                        {profile.availability && <span>Availability: <span className="text-foreground">{AVAILABILITY_LABELS[profile.availability] || profile.availability}</span></span>}
                                        {profile.nationality_secondary && <span>Second nationality: <span className="text-foreground">{profile.nationality_secondary}</span></span>}
                                        {profile.languages && <span>Languages: <span className="text-foreground">{profile.languages}</span></span>}
                                        {profile.agent_name && <span>Agent: <span className="text-foreground">{profile.agent_name}</span></span>}
                                        {profile.agent_contact_email && <span>Agent email: <span className="text-foreground">{profile.agent_contact_email}</span></span>}
                                    </div>
                                    {formatDate(profile.updated_at) && (
                                        <p className="text-xs text-muted-foreground">Updated {formatDate(profile.updated_at)}</p>
                                    )}
                                </div>
                                {profile.status === 'pending' && (
                                    <div className="flex shrink-0 items-center gap-2">
                                        <Button size="sm" variant="outline" className="border-emerald-600 text-emerald-600 hover:bg-emerald-50" disabled={actingId === profile.id} onClick={() => act(profile, 'approve')}>
                                            {actingId === profile.id ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Check className="mr-1 h-4 w-4" />}
                                            Approve
                                        </Button>
                                        <Button size="sm" variant="outline" className="border-rose-600 text-rose-600 hover:bg-rose-50" disabled={actingId === profile.id} onClick={() => act(profile, 'reject')}>
                                            <X className="mr-1 h-4 w-4" />
                                            Reject
                                        </Button>
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                )}
            </CardContent>
        </Card>
    )
}

// ---------------------------------------------------------------------------
// Photo moderation
// ---------------------------------------------------------------------------

function MediaTab({ setMessage }) {
    const [media, setMedia] = useState([])
    const [loading, setLoading] = useState(true)
    const [status, setStatus] = useState('pending')
    const [reloadKey, setReloadKey] = useState(0)
    const [actingId, setActingId] = useState(null)
    const [notes, setNotes] = useState({})

    useEffect(() => {
        let cancelled = false
        setLoading(true)
        const params = status === 'all' ? {} : { status }
        APIService.adminListShowcaseMedia(params)
            .then((data) => { if (!cancelled) setMedia(asArray(data, 'media')) })
            .catch((err) => {
                if (!cancelled) setMessage({ type: 'error', text: err.message || 'Failed to load showcase media' })
            })
            .finally(() => { if (!cancelled) setLoading(false) })
        return () => { cancelled = true }
    }, [status, reloadKey, setMessage])

    const act = async (item, action) => {
        setActingId(item.id)
        try {
            await APIService.adminReviewShowcaseMedia(item.id, {
                action,
                note: notes[item.id]?.trim() || undefined,
            })
            setMessage({ type: 'success', text: `Photo ${action === 'approve' ? 'approved' : 'rejected'}` })
            setNotes((current) => {
                const next = { ...current }
                delete next[item.id]
                return next
            })
            setReloadKey((k) => k + 1)
        } catch (err) {
            setMessage({ type: 'error', text: err.message || 'Failed to review photo' })
        } finally {
            setActingId(null)
        }
    }

    return (
        <Card>
            <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                    <CardTitle>Showcase photos</CardTitle>
                    <CardDescription>Review player-uploaded photos before they appear publicly</CardDescription>
                </div>
                <Select value={status} onValueChange={setStatus}>
                    <SelectTrigger className="w-40">
                        <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="pending">Pending</SelectItem>
                        <SelectItem value="approved">Approved</SelectItem>
                        <SelectItem value="rejected">Rejected</SelectItem>
                        <SelectItem value="all">All</SelectItem>
                    </SelectContent>
                </Select>
            </CardHeader>
            <CardContent>
                {loading ? (
                    <Loading />
                ) : media.length === 0 ? (
                    <p className="py-8 text-center text-sm text-muted-foreground">No {status === 'all' ? '' : status} photos.</p>
                ) : (
                    <div className="space-y-3">
                        {media.map((item) => {
                            const thumbnail = item.pending_preview_url || item.public_url
                            const isActing = actingId === item.id
                            return (
                                <div key={item.id} className="flex flex-col gap-4 rounded-lg border bg-card p-4 lg:flex-row lg:items-start">
                                    <div className="flex min-w-0 flex-1 flex-col gap-4 sm:flex-row">
                                        <div className="flex aspect-[4/3] w-full shrink-0 items-center justify-center overflow-hidden rounded-md border bg-muted sm:w-36">
                                            {thumbnail ? (
                                                <img
                                                    src={thumbnail}
                                                    alt={`Showcase photo for player ${item.player_api_id}`}
                                                    className="h-full w-full object-cover"
                                                    loading="lazy"
                                                />
                                            ) : (
                                                <ImageIcon className="h-8 w-8 text-muted-foreground/50" aria-hidden="true" />
                                            )}
                                        </div>
                                        <div className="min-w-0 flex-1 space-y-2">
                                            <div className="flex flex-wrap items-center gap-2">
                                                <Badge className={CLAIM_STATUS_COLORS[item.status] || CLAIM_STATUS_COLORS.revoked}>
                                                    {String(item.status || 'unknown').replace('_', ' ')}
                                                </Badge>
                                                <Badge variant="outline">Player #{item.player_api_id}</Badge>
                                            </div>
                                            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                                                <span>{formatBytes(item.size_bytes)}</span>
                                                {item.content_type && <span>{item.content_type}</span>}
                                                {formatDate(item.created_at) && <span>Uploaded {formatDate(item.created_at)}</span>}
                                            </div>
                                            {item.review_note && (
                                                <p className="text-xs text-muted-foreground">Review note: {item.review_note}</p>
                                            )}
                                        </div>
                                    </div>
                                    <div className="flex w-full shrink-0 flex-col gap-2 lg:w-72">
                                        <Input
                                            value={notes[item.id] || ''}
                                            onChange={(event) => setNotes((current) => ({ ...current, [item.id]: event.target.value }))}
                                            placeholder="Review note (optional)"
                                            aria-label={`Review note for photo ${item.id}`}
                                            maxLength={1000}
                                            disabled={isActing}
                                        />
                                        <div className="flex items-center justify-end gap-2">
                                            {item.status !== 'approved' && (
                                                <Button
                                                    size="sm"
                                                    variant="outline"
                                                    className="border-emerald-600 text-emerald-600 hover:bg-emerald-50"
                                                    disabled={isActing}
                                                    onClick={() => act(item, 'approve')}
                                                >
                                                    {isActing ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Check className="mr-1 h-4 w-4" />}
                                                    Approve
                                                </Button>
                                            )}
                                            {item.status !== 'rejected' && (
                                                <Button
                                                    size="sm"
                                                    variant="outline"
                                                    className="border-rose-600 text-rose-600 hover:bg-rose-50"
                                                    disabled={isActing}
                                                    onClick={() => act(item, 'reject')}
                                                >
                                                    {isActing ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <X className="mr-1 h-4 w-4" />}
                                                    Reject
                                                </Button>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            )
                        })}
                    </div>
                )}
            </CardContent>
        </Card>
    )
}

// ---------------------------------------------------------------------------
// Local players
// ---------------------------------------------------------------------------

function LocalPlayersTab({ setMessage }) {
    const [players, setPlayers] = useState([])
    const [loading, setLoading] = useState(true)
    const [status, setStatus] = useState('pending')
    const [reloadKey, setReloadKey] = useState(0)
    const [actingId, setActingId] = useState(null)
    const [notes, setNotes] = useState({})

    const [mergeSource, setMergeSource] = useState(null)
    const [mergeQuery, setMergeQuery] = useState('')
    const [mergeTargets, setMergeTargets] = useState([])
    const [mergeTargetsLoading, setMergeTargetsLoading] = useState(false)
    const [mergeTargetId, setMergeTargetId] = useState('')
    const [mergeError, setMergeError] = useState('')

    const [linkPlayer, setLinkPlayer] = useState(null)
    const [playerApiId, setPlayerApiId] = useState('')
    const [linkError, setLinkError] = useState('')

    useEffect(() => {
        let cancelled = false
        const params = status === 'all' ? {} : { status }
        APIService.adminListLocalPlayers(params)
            .then((data) => {
                if (!cancelled) setPlayers(asArray(data, 'players'))
            })
            .catch((err) => {
                if (!cancelled) setMessage({ type: 'error', text: err.message || 'Failed to load local players' })
            })
            .finally(() => {
                if (!cancelled) setLoading(false)
            })
        return () => { cancelled = true }
    }, [reloadKey, setMessage, status])

    useEffect(() => {
        if (!mergeSource) return undefined

        let cancelled = false
        APIService.adminListLocalPlayers({})
            .then((data) => {
                if (!cancelled) setMergeTargets(asArray(data, 'players'))
            })
            .catch((err) => {
                if (!cancelled) setMergeError(err.message || 'Failed to load merge targets')
            })
            .finally(() => {
                if (!cancelled) setMergeTargetsLoading(false)
            })

        return () => { cancelled = true }
    }, [mergeSource])

    const filteredMergeTargets = useMemo(() => {
        const query = mergeQuery.trim().toLowerCase()
        return mergeTargets.filter((player) => {
            if (Number(player.id) === Number(mergeSource?.id)) return false
            if (!query) return true
            return [player.display_name, player.position, player.city, player.country, player.birth_year]
                .filter((value) => value != null && value !== '')
                .some((value) => String(value).toLowerCase().includes(query))
        })
    }, [mergeQuery, mergeSource?.id, mergeTargets])

    const reviewPlayer = async (player, action) => {
        setActingId(player.id)
        try {
            await APIService.adminReviewLocalPlayer(player.id, {
                action,
                note: notes[player.id]?.trim() || undefined,
            })
            setMessage({
                type: 'success',
                text: `${player.display_name || 'Local player'} ${action === 'approve' ? 'approved' : 'rejected'}`,
            })
            setNotes((current) => {
                const next = { ...current }
                delete next[player.id]
                return next
            })
            setLoading(true)
            setReloadKey((key) => key + 1)
        } catch (err) {
            setMessage({ type: 'error', text: err.message || 'Failed to review local player' })
        } finally {
            setActingId(null)
        }
    }

    const openMerge = (player) => {
        setMergeSource(player)
        setMergeQuery('')
        setMergeTargets([])
        setMergeTargetsLoading(true)
        setMergeTargetId('')
        setMergeError('')
    }

    const closeMerge = () => {
        setMergeSource(null)
        setMergeQuery('')
        setMergeTargets([])
        setMergeTargetsLoading(false)
        setMergeTargetId('')
        setMergeError('')
    }

    const mergePlayer = async () => {
        const targetId = Number(mergeTargetId)
        if (!mergeSource || !Number.isInteger(targetId) || targetId <= 0 || targetId === Number(mergeSource.id)) {
            setMergeError('Select a different player as the merge target')
            return
        }

        setActingId(mergeSource.id)
        setMergeError('')
        try {
            await APIService.adminMergeLocalPlayer(mergeSource.id, { into_local_player_id: targetId })
            setMessage({ type: 'success', text: `${mergeSource.display_name || 'Local player'} merged successfully` })
            closeMerge()
            setLoading(true)
            setReloadKey((key) => key + 1)
        } catch (err) {
            setMergeError(err.message || 'Failed to merge local player')
        } finally {
            setActingId(null)
        }
    }

    const openLink = (player) => {
        setLinkPlayer(player)
        setPlayerApiId(player.api_player_id != null ? String(player.api_player_id) : '')
        setLinkError('')
    }

    const closeLink = () => {
        setLinkPlayer(null)
        setPlayerApiId('')
        setLinkError('')
    }

    const linkApiPlayer = async () => {
        const parsedPlayerApiId = Number(playerApiId)
        if (!linkPlayer || !Number.isInteger(parsedPlayerApiId) || parsedPlayerApiId <= 0) {
            setLinkError('Enter a valid positive API-Football player ID')
            return
        }

        setActingId(linkPlayer.id)
        setLinkError('')
        try {
            await APIService.adminLinkLocalPlayerApi(linkPlayer.id, { player_api_id: parsedPlayerApiId })
            setMessage({
                type: 'success',
                text: `${linkPlayer.display_name || 'Local player'} linked to API player #${parsedPlayerApiId}`,
            })
            closeLink()
            setLoading(true)
            setReloadKey((key) => key + 1)
        } catch (err) {
            setLinkError(err.message || 'Failed to link API-Football player')
        } finally {
            setActingId(null)
        }
    }

    return (
        <>
            <Card>
                <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                        <CardTitle>Local players</CardTitle>
                        <CardDescription>Review, deduplicate and connect community-created player profiles</CardDescription>
                    </div>
                    <Select
                        value={status}
                        onValueChange={(value) => { setLoading(true); setStatus(value) }}
                        disabled={loading || actingId !== null}
                    >
                        <SelectTrigger className="w-40" aria-label="Filter local players by status">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="pending">Pending</SelectItem>
                            <SelectItem value="approved">Approved</SelectItem>
                            <SelectItem value="rejected">Rejected</SelectItem>
                            <SelectItem value="merged">Merged</SelectItem>
                            <SelectItem value="all">All</SelectItem>
                        </SelectContent>
                    </Select>
                </CardHeader>
                <CardContent>
                    {loading ? (
                        <Loading />
                    ) : players.length === 0 ? (
                        <p className="py-8 text-center text-sm text-muted-foreground">
                            No {status === 'all' ? '' : status} local players.
                        </p>
                    ) : (
                        <div className="space-y-3">
                            {players.map((player) => {
                                const playerName = player.display_name || `Local player #${player.id}`
                                const creatorEmail = player.creator_email
                                    || player.created_by_email
                                    || player.user_email
                                    || player.creator?.email
                                const isActing = actingId === player.id
                                const isBusy = actingId !== null
                                const canReview = player.status === 'pending'
                                const canManage = player.status !== 'merged'
                                return (
                                    <div key={player.id} className="flex flex-col gap-4 rounded-lg border bg-card p-4 xl:flex-row xl:items-start">
                                        <div className="min-w-0 flex-1 space-y-2">
                                            <div className="flex flex-wrap items-center gap-2">
                                                <Badge className={LOCAL_PLAYER_STATUS_COLORS[player.status] || 'bg-stone-100 text-stone-700 border-stone-200'}>
                                                    {String(player.status || 'unknown').replace(/_/g, ' ')}
                                                </Badge>
                                                <span className="text-sm font-semibold text-foreground">{playerName}</span>
                                                <Badge variant="outline">Local player #{player.id}</Badge>
                                            </div>
                                            <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
                                                {player.birth_year != null && (
                                                    <span>Birth year: <span className="text-foreground">{player.birth_year}</span></span>
                                                )}
                                                {player.position && (
                                                    <span>Position: <span className="text-foreground">{player.position}</span></span>
                                                )}
                                                <span>{localPlayerLocation(player)}</span>
                                                {creatorEmail && (
                                                    <span>Created by: <span className="text-foreground">{creatorEmail}</span></span>
                                                )}
                                                {player.api_player_id != null && (
                                                    <span className="font-medium text-emerald-700">API player #{player.api_player_id}</span>
                                                )}
                                            </div>
                                            {player.review_note && (
                                                <p className="text-xs text-muted-foreground">Review note: {player.review_note}</p>
                                            )}
                                        </div>

                                        {canReview || canManage ? (
                                            <div className="flex w-full shrink-0 flex-col gap-2 xl:w-[31rem]">
                                                {canReview && (
                                                    <Input
                                                        value={notes[player.id] || ''}
                                                        onChange={(event) => setNotes((current) => ({ ...current, [player.id]: event.target.value }))}
                                                        placeholder="Review note (optional)"
                                                        aria-label={`Review note for ${playerName}`}
                                                        maxLength={1000}
                                                        disabled={isBusy}
                                                    />
                                                )}
                                                <div className="flex flex-wrap justify-end gap-2">
                                                    {canReview && (
                                                        <Button
                                                            size="sm"
                                                            variant="outline"
                                                            className="border-emerald-600 text-emerald-600 hover:bg-emerald-50"
                                                            disabled={isBusy}
                                                            onClick={() => reviewPlayer(player, 'approve')}
                                                        >
                                                            {isActing ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Check className="mr-1 h-4 w-4" />}
                                                            Approve
                                                        </Button>
                                                    )}
                                                    {canReview && (
                                                        <Button
                                                            size="sm"
                                                            variant="outline"
                                                            className="border-rose-600 text-rose-600 hover:bg-rose-50"
                                                            disabled={isBusy}
                                                            onClick={() => reviewPlayer(player, 'reject')}
                                                        >
                                                            {isActing ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <X className="mr-1 h-4 w-4" />}
                                                            Reject
                                                        </Button>
                                                    )}
                                                    {canManage && (
                                                        <Button size="sm" variant="outline" disabled={isBusy} onClick={() => openMerge(player)}>
                                                            <GitMerge className="mr-1 h-4 w-4" />
                                                            Merge
                                                        </Button>
                                                    )}
                                                    {canManage && (
                                                        <Button size="sm" variant="outline" disabled={isBusy} onClick={() => openLink(player)}>
                                                            <Link2 className="mr-1 h-4 w-4" />
                                                            {player.api_player_id != null ? 'Edit API link' : 'Link API'}
                                                        </Button>
                                                    )}
                                                </div>
                                            </div>
                                        ) : null}
                                    </div>
                                )
                            })}
                        </div>
                    )}
                </CardContent>
            </Card>

            <Dialog open={Boolean(mergeSource)} onOpenChange={(open) => { if (!open && actingId !== mergeSource?.id) closeMerge() }}>
                <DialogContent className="sm:max-w-xl">
                    <DialogHeader>
                        <DialogTitle>Merge {mergeSource?.display_name || 'local player'}</DialogTitle>
                        <DialogDescription>
                            Choose the canonical community player profile. The source profile will be merged into it.
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-3">
                        <div className="space-y-2">
                            <Label htmlFor="merge-local-player-search">Find target player</Label>
                            <div className="relative">
                                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                                <Input
                                    id="merge-local-player-search"
                                    value={mergeQuery}
                                    onChange={(event) => setMergeQuery(event.target.value)}
                                    placeholder="Search by name, position or location"
                                    className="pl-9"
                                    autoComplete="off"
                                    disabled={actingId === mergeSource?.id}
                                />
                            </div>
                        </div>

                        {mergeTargetsLoading ? (
                            <Loading />
                        ) : filteredMergeTargets.length === 0 ? (
                            <p className="rounded-md border border-dashed p-5 text-center text-sm text-muted-foreground">
                                No matching merge targets.
                            </p>
                        ) : (
                            <div className="max-h-64 space-y-1 overflow-y-auto rounded-md border p-1" aria-label="Merge target players">
                                {filteredMergeTargets.map((player) => {
                                    const selected = mergeTargetId === String(player.id)
                                    return (
                                        <button
                                            key={player.id}
                                            type="button"
                                            aria-pressed={selected}
                                            disabled={actingId === mergeSource?.id}
                                            className={`flex w-full items-center justify-between gap-3 rounded px-3 py-2 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${selected ? 'bg-primary/10 text-primary' : 'hover:bg-accent'}`}
                                            onClick={() => setMergeTargetId(String(player.id))}
                                        >
                                            <span className="min-w-0">
                                                <span className="block truncate text-sm font-medium">
                                                    {player.display_name || `Local player #${player.id}`}
                                                </span>
                                                <span className="block truncate text-xs text-muted-foreground">
                                                    {[player.position, player.birth_year, localPlayerLocation(player)].filter(Boolean).join(' · ')}
                                                </span>
                                            </span>
                                            <Badge className={LOCAL_PLAYER_STATUS_COLORS[player.status] || 'bg-stone-100 text-stone-700 border-stone-200'}>
                                                {String(player.status || 'unknown').replace(/_/g, ' ')}
                                            </Badge>
                                        </button>
                                    )
                                })}
                            </div>
                        )}

                        {mergeError && <p className="text-sm text-rose-700" role="alert">{mergeError}</p>}
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={closeMerge} disabled={actingId === mergeSource?.id}>Cancel</Button>
                        <Button onClick={mergePlayer} disabled={!mergeTargetId || mergeTargetsLoading || actingId === mergeSource?.id}>
                            {actingId === mergeSource?.id && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            Merge player
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            <Dialog open={Boolean(linkPlayer)} onOpenChange={(open) => { if (!open && actingId !== linkPlayer?.id) closeLink() }}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Link {linkPlayer?.display_name || 'local player'} to API-Football</DialogTitle>
                        <DialogDescription>
                            Enter the official API-Football player ID that represents this community profile.
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-2">
                        <Label htmlFor="local-player-api-id">Player API ID</Label>
                        <Input
                            id="local-player-api-id"
                            type="number"
                            min="1"
                            step="1"
                            inputMode="numeric"
                            value={playerApiId}
                            onChange={(event) => setPlayerApiId(event.target.value)}
                            placeholder="e.g. 284324"
                            disabled={actingId === linkPlayer?.id}
                        />
                        {linkError && <p className="text-sm text-rose-700" role="alert">{linkError}</p>}
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={closeLink} disabled={actingId === linkPlayer?.id}>Cancel</Button>
                        <Button onClick={linkApiPlayer} disabled={!playerApiId.trim() || actingId === linkPlayer?.id}>
                            {actingId === linkPlayer?.id && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            Save API link
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </>
    )
}

// ---------------------------------------------------------------------------
// Film Room links — link finalized-match roster entries to a tracked player
// ---------------------------------------------------------------------------

function RosterLinkRow({ entry, setMessage, onChanged }) {
    const rosterId = entry.id ?? entry.roster_id
    const linkedApiId = entry.player_api_id ?? entry.linked_player_api_id
    const linkedName = entry.linked_player_name ?? entry.tracked_player_name

    const [query, setQuery] = useState('')
    const [results, setResults] = useState([])
    const [searching, setSearching] = useState(false)
    const [open, setOpen] = useState(false)
    const [busy, setBusy] = useState(false)

    useEffect(() => {
        const q = query.trim()
        if (q.length < 2) { setResults([]); return }
        let cancelled = false
        setSearching(true)
        const t = setTimeout(() => {
            APIService.adminShowcasePlayerSearch(q)
                .then((data) => { if (!cancelled) { setResults(asArray(data, 'results', 'players')); setOpen(true) } })
                .catch(() => { if (!cancelled) setResults([]) })
                .finally(() => { if (!cancelled) setSearching(false) })
        }, 300)
        return () => { cancelled = true; clearTimeout(t) }
    }, [query])

    const link = async (playerApiId) => {
        setBusy(true)
        try {
            await APIService.adminLinkVideoRoster(rosterId, { player_api_id: playerApiId })
            setMessage({ type: 'success', text: playerApiId ? 'Roster entry linked' : 'Link cleared' })
            setQuery('')
            setResults([])
            setOpen(false)
            onChanged()
        } catch (err) {
            setMessage({ type: 'error', text: err.message || 'Failed to update link' })
        } finally {
            setBusy(false)
        }
    }

    const identity = entry.identity_confidence

    return (
        <div className="flex flex-col gap-3 rounded-lg border bg-card p-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0 flex-1 space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-foreground">
                        {entry.player_name || 'Unknown player'}
                    </span>
                    {entry.jersey_number != null && (
                        <Badge variant="secondary">#{entry.jersey_number}</Badge>
                    )}
                    {identity && (
                        <Badge className={IDENTITY_COLORS[identity] || IDENTITY_COLORS.unverified}>
                            {String(identity).replace('_', ' ')}
                        </Badge>
                    )}
                </div>
                {linkedApiId ? (
                    <p className="text-xs text-emerald-700">
                        Linked to {linkedName ? `${linkedName} · ` : ''}#{linkedApiId}
                    </p>
                ) : (
                    <p className="text-xs text-muted-foreground">Not linked to a tracked player</p>
                )}
            </div>
            <div className="relative w-full shrink-0 sm:w-72">
                <div className="flex items-center gap-2">
                    <div className="relative flex-1">
                        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                        <Input
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            onFocus={() => results.length > 0 && setOpen(true)}
                            placeholder="Search tracked player…"
                            className="pl-8"
                            disabled={busy}
                        />
                        {searching && <Loader2 className="absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 animate-spin text-muted-foreground" />}
                        {open && results.length > 0 && (
                            <div className="absolute z-20 mt-1 max-h-64 w-full overflow-auto rounded-md border bg-popover shadow-md">
                                {results.map((r) => (
                                    <button
                                        key={r.player_api_id}
                                        type="button"
                                        className="flex w-full flex-col items-start gap-0.5 px-3 py-2 text-left text-sm hover:bg-accent"
                                        onClick={() => link(r.player_api_id)}
                                    >
                                        <span className="font-medium text-foreground">{r.player_name} · #{r.player_api_id}</span>
                                        <span className="text-xs text-muted-foreground">
                                            {[r.team_name, r.status].filter(Boolean).join(' · ')}
                                        </span>
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>
                    {linkedApiId && (
                        <Button size="sm" variant="ghost" className="shrink-0 text-muted-foreground hover:text-destructive" disabled={busy} onClick={() => link(null)}>
                            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <X className="h-4 w-4" />}
                            Unlink
                        </Button>
                    )}
                </div>
            </div>
        </div>
    )
}

function RostersTab({ setMessage }) {
    const [entries, setEntries] = useState([])
    const [loading, setLoading] = useState(true)
    const [reloadKey, setReloadKey] = useState(0)

    const reload = useCallback(() => setReloadKey((k) => k + 1), [])

    useEffect(() => {
        let cancelled = false
        setLoading(true)
        APIService.adminListVideoRosters()
            .then((data) => { if (!cancelled) setEntries(asArray(data, 'rosters', 'entries')) })
            .catch((err) => {
                if (!cancelled) setMessage({ type: 'error', text: err.message || 'Failed to load roster entries' })
            })
            .finally(() => { if (!cancelled) setLoading(false) })
        return () => { cancelled = true }
    }, [reloadKey, setMessage])

    // Group roster entries by match for readability.
    const groups = entries.reduce((acc, entry) => {
        const matchId = entry.match_id ?? entry.match?.id ?? 'unknown'
        if (!acc[matchId]) {
            acc[matchId] = {
                matchId,
                label: entry.opponent_name
                    ? `${entry.team_name || 'Match'} vs ${entry.opponent_name}`
                    : entry.match?.label || entry.team_name || `Match ${matchId}`,
                date: entry.match_date ?? entry.match?.match_date,
                items: [],
            }
        }
        acc[matchId].items.push(entry)
        return acc
    }, {})
    const groupList = Object.values(groups)

    return (
        <Card>
            <CardHeader>
                <CardTitle>Film Room links</CardTitle>
                <CardDescription>
                    Link finalized-match roster entries to a tracked player. Human-confirmed identities then surface
                    as club-verified footage on that player&apos;s public showcase.
                </CardDescription>
            </CardHeader>
            <CardContent>
                {loading ? (
                    <Loading />
                ) : groupList.length === 0 ? (
                    <p className="py-8 text-center text-sm text-muted-foreground">No finalized-match roster entries yet.</p>
                ) : (
                    <div className="space-y-6">
                        {groupList.map((group) => (
                            <div key={group.matchId} className="space-y-3">
                                <div className="flex items-center gap-2">
                                    <Film className="h-4 w-4 text-muted-foreground" />
                                    <span className="text-sm font-semibold text-foreground">{group.label}</span>
                                    {formatDate(group.date) && (
                                        <span className="text-xs text-muted-foreground">{formatDate(group.date)}</span>
                                    )}
                                </div>
                                <div className="space-y-2">
                                    {group.items.map((entry) => (
                                        <RosterLinkRow
                                            key={entry.id ?? entry.roster_id}
                                            entry={entry}
                                            setMessage={setMessage}
                                            onChanged={reload}
                                        />
                                    ))}
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </CardContent>
        </Card>
    )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function AdminShowcase() {
    const [message, setMessage] = useState(null)
    const [tab, setTab] = useState('claims')

    return (
        <div className="space-y-6">
            <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10">
                    <Star className="h-5 w-5 text-primary" />
                </div>
                <div>
                    <h2 className="text-3xl font-bold tracking-tight">Talent Showcase</h2>
                    <p className="text-muted-foreground">Moderate profile claims, self-reported edits, photos and Film Room evidence</p>
                </div>
            </div>

            {message && (
                <Alert className={message.type === 'error' ? 'border-rose-500 bg-rose-50' : 'border-emerald-500 bg-emerald-50'}>
                    {message.type === 'error' ? <AlertCircle className="h-4 w-4 text-rose-600" /> : <CheckCircle2 className="h-4 w-4 text-emerald-600" />}
                    <AlertDescription className={message.type === 'error' ? 'text-rose-800' : 'text-emerald-800'}>
                        {message.text}
                    </AlertDescription>
                </Alert>
            )}

            <div className="flex items-center gap-2 rounded-md border border-border/70 bg-secondary/40 px-3 py-2 text-sm text-muted-foreground">
                <Inbox className="h-4 w-4 shrink-0" />
                <span>
                    Highlight-reel videos are moderated in the{' '}
                    <Link to="/admin/inbox?tab=links" className="font-medium text-primary hover:underline">Inbox → Player links</Link>{' '}
                    queue.
                </span>
            </div>

            <Tabs value={tab} onValueChange={setTab}>
                <TabsList className="h-auto flex-wrap justify-start">
                    <TabsTrigger value="claims">
                        <UserSquare className="mr-1.5 h-4 w-4" />
                        Claims
                    </TabsTrigger>
                    <TabsTrigger value="profiles">
                        <Link2 className="mr-1.5 h-4 w-4" />
                        Profile edits
                    </TabsTrigger>
                    <TabsTrigger value="rosters">
                        <Film className="mr-1.5 h-4 w-4" />
                        Film Room links
                    </TabsTrigger>
                    <TabsTrigger value="media">
                        <ImageIcon className="mr-1.5 h-4 w-4" />
                        Media
                    </TabsTrigger>
                    <TabsTrigger value="local-players">
                        <UserSquare className="mr-1.5 h-4 w-4" />
                        Local players
                    </TabsTrigger>
                </TabsList>

                <TabsContent value="claims" className="mt-4">
                    {tab === 'claims' && <ClaimsTab setMessage={setMessage} />}
                </TabsContent>
                <TabsContent value="profiles" className="mt-4">
                    {tab === 'profiles' && <ProfilesTab setMessage={setMessage} />}
                </TabsContent>
                <TabsContent value="rosters" className="mt-4">
                    {tab === 'rosters' && <RostersTab setMessage={setMessage} />}
                </TabsContent>
                <TabsContent value="media" className="mt-4">
                    {tab === 'media' && <MediaTab setMessage={setMessage} />}
                </TabsContent>
                <TabsContent value="local-players" className="mt-4">
                    {tab === 'local-players' && <LocalPlayersTab setMessage={setMessage} />}
                </TabsContent>
            </Tabs>
        </div>
    )
}

export default AdminShowcase
