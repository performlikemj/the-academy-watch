import { useEffect, useMemo, useState } from 'react'
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
import { Input } from '@/components/ui/input'
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
    AlertCircle,
    Check,
    CheckCircle2,
    GitMerge,
    Landmark,
    Link2,
    Loader2,
    Search,
    X,
} from 'lucide-react'

const CLUB_STATUS_STYLES = {
    pending: 'bg-amber-50 text-amber-800 border-amber-200',
    verified: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    rejected: 'bg-rose-50 text-rose-800 border-rose-200',
    merged: 'bg-stone-100 text-stone-700 border-stone-200',
}

const AFFILIATION_STATUS_STYLES = {
    pending: 'bg-amber-50 text-amber-800 border-amber-200',
    self_reported: 'bg-sky-50 text-sky-800 border-sky-200',
    club_confirmed: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    rejected: 'bg-rose-50 text-rose-800 border-rose-200',
}

const AFFILIATION_STATUS_LABELS = {
    pending: 'Pending',
    self_reported: 'Self-reported',
    club_confirmed: 'Club-confirmed',
    rejected: 'Rejected',
}

const LEVEL_LABELS = {
    grassroots: 'Grassroots',
    academy: 'Academy',
    youth: 'Youth',
    semi_pro: 'Semi-pro',
    professional: 'Professional',
    other: 'Other',
}

function formatLabel(value) {
    if (!value) return 'Unknown'
    return String(value)
        .split('_')
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
        .join(' ')
}

function formatDate(value) {
    if (!value) return null
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return null
    return date.toLocaleDateString(undefined, {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
    })
}

function locationLabel(club) {
    return [club.city, club.country].filter(Boolean).join(', ') || 'Location not provided'
}

function Loading() {
    return (
        <div className="flex items-center justify-center py-12">
            <Loader2 className="mr-2 h-5 w-5 animate-spin text-muted-foreground/70" />
            <span className="text-sm text-muted-foreground">Loading…</span>
        </div>
    )
}

function StatusBadge({ status, styles, labels }) {
    return (
        <Badge className={styles[status] || 'bg-stone-100 text-stone-700 border-stone-200'}>
            {labels?.[status] || formatLabel(status)}
        </Badge>
    )
}

function ClubsTab({ setMessage }) {
    const [clubs, setClubs] = useState([])
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

    const [linkClub, setLinkClub] = useState(null)
    const [teamApiId, setTeamApiId] = useState('')
    const [linkError, setLinkError] = useState('')

    useEffect(() => {
        let cancelled = false
        const params = status === 'all' ? {} : { status }
        APIService.adminListLocalClubs(params)
            .then((data) => {
                if (!cancelled) setClubs(Array.isArray(data?.clubs) ? data.clubs : [])
            })
            .catch((err) => {
                if (!cancelled) setMessage({ type: 'error', text: err.message || 'Failed to load local clubs' })
            })
            .finally(() => {
                if (!cancelled) setLoading(false)
            })
        return () => { cancelled = true }
    }, [reloadKey, setMessage, status])

    useEffect(() => {
        if (!mergeSource) return undefined

        let cancelled = false
        APIService.adminListLocalClubs()
            .then((data) => {
                if (!cancelled) setMergeTargets(Array.isArray(data?.clubs) ? data.clubs : [])
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
        return mergeTargets.filter((club) => {
            if (Number(club.id) === Number(mergeSource?.id) || ['merged', 'rejected'].includes(club.status)) return false
            if (!query) return true
            return [club.name, club.city, club.country]
                .filter(Boolean)
                .some((value) => String(value).toLowerCase().includes(query))
        })
    }, [mergeQuery, mergeSource?.id, mergeTargets])

    const reviewClub = async (club, action) => {
        setActingId(club.id)
        try {
            await APIService.adminReviewLocalClub(club.id, {
                action,
                note: notes[club.id]?.trim() || '',
            })
            setMessage({
                type: 'success',
                text: action === 'verify' ? `${club.name} verified` : `${club.name} rejected`,
            })
            setNotes((current) => {
                const next = { ...current }
                delete next[club.id]
                return next
            })
            setLoading(true)
            setReloadKey((key) => key + 1)
        } catch (err) {
            setMessage({ type: 'error', text: err.message || 'Failed to review local club' })
        } finally {
            setActingId(null)
        }
    }

    const openMerge = (club) => {
        setMergeSource(club)
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
        setMergeTargetId('')
        setMergeError('')
    }

    const mergeClub = async () => {
        const targetId = Number(mergeTargetId)
        if (!Number.isInteger(targetId) || targetId <= 0 || targetId === mergeSource?.id) {
            setMergeError('Select a different club as the merge target')
            return
        }

        setActingId(mergeSource.id)
        setMergeError('')
        try {
            await APIService.adminMergeLocalClub(mergeSource.id, { into_local_club_id: targetId })
            setMessage({ type: 'success', text: `${mergeSource.name} merged successfully` })
            closeMerge()
            setLoading(true)
            setReloadKey((key) => key + 1)
        } catch (err) {
            setMergeError(err.message || 'Failed to merge local club')
        } finally {
            setActingId(null)
        }
    }

    const openLink = (club) => {
        setLinkClub(club)
        setTeamApiId(club.api_team_id != null ? String(club.api_team_id) : '')
        setLinkError('')
    }

    const closeLink = () => {
        setLinkClub(null)
        setTeamApiId('')
        setLinkError('')
    }

    const linkApiClub = async () => {
        const parsedTeamApiId = Number(teamApiId)
        if (!Number.isInteger(parsedTeamApiId) || parsedTeamApiId <= 0) {
            setLinkError('Enter a valid positive API-Football team ID')
            return
        }

        setActingId(linkClub.id)
        setLinkError('')
        try {
            await APIService.adminLinkLocalClubApi(linkClub.id, { team_api_id: parsedTeamApiId })
            setMessage({ type: 'success', text: `${linkClub.name} linked to API team #${parsedTeamApiId}` })
            closeLink()
            setLoading(true)
            setReloadKey((key) => key + 1)
        } catch (err) {
            setLinkError(err.message || 'Failed to link API-Football team')
        } finally {
            setActingId(null)
        }
    }

    return (
        <>
            <Card>
                <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                        <CardTitle>Community clubs</CardTitle>
                        <CardDescription>Review, deduplicate and connect community-created clubs</CardDescription>
                    </div>
                    <Select value={status} onValueChange={(value) => { setLoading(true); setStatus(value) }}>
                        <SelectTrigger className="w-40" aria-label="Filter local clubs by status">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="pending">Pending</SelectItem>
                            <SelectItem value="verified">Verified</SelectItem>
                            <SelectItem value="rejected">Rejected</SelectItem>
                            <SelectItem value="merged">Merged</SelectItem>
                            <SelectItem value="all">All</SelectItem>
                        </SelectContent>
                    </Select>
                </CardHeader>
                <CardContent>
                    {loading ? (
                        <Loading />
                    ) : clubs.length === 0 ? (
                        <p className="py-8 text-center text-sm text-muted-foreground">
                            No {status === 'all' ? '' : status} local clubs.
                        </p>
                    ) : (
                        <div className="space-y-3">
                            {clubs.map((club) => {
                                const isActing = actingId === club.id
                                const canReview = club.status === 'pending'
                                const canMerge = club.status === 'pending' || club.status === 'verified'
                                const canLink = club.status !== 'merged'
                                const hasActions = canReview || canMerge || canLink
                                return (
                                    <div key={club.id} className="flex flex-col gap-4 rounded-lg border bg-card p-4 xl:flex-row xl:items-start">
                                        <div className="min-w-0 flex-1 space-y-2">
                                            <div className="flex flex-wrap items-center gap-2">
                                                <StatusBadge status={club.status} styles={CLUB_STATUS_STYLES} />
                                                <span className="text-sm font-semibold text-foreground">{club.name}</span>
                                                <Badge variant="outline">Club #{club.id}</Badge>
                                            </div>
                                            <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
                                                <span>{locationLabel(club)}</span>
                                                <span>Level: <span className="text-foreground">{LEVEL_LABELS[club.level] || formatLabel(club.level)}</span></span>
                                                <span>Provenance: <span className="text-foreground">{formatLabel(club.provenance)}</span></span>
                                                {club.api_team_id != null && (
                                                    <span className="font-medium text-emerald-700">API team #{club.api_team_id}</span>
                                                )}
                                            </div>
                                            {club.review_note && (
                                                <p className="text-xs text-muted-foreground">Review note: {club.review_note}</p>
                                            )}
                                        </div>

                                        {hasActions && (
                                            <div className="flex w-full shrink-0 flex-col gap-2 xl:w-[31rem]">
                                                {canReview && (
                                                    <Input
                                                        value={notes[club.id] || ''}
                                                        onChange={(event) => setNotes((current) => ({ ...current, [club.id]: event.target.value }))}
                                                        placeholder="Review note (optional)"
                                                        aria-label={`Review note for ${club.name}`}
                                                        maxLength={1000}
                                                        disabled={isActing}
                                                    />
                                                )}
                                                <div className="flex flex-wrap justify-end gap-2">
                                                    {canReview && (
                                                        <Button
                                                            size="sm"
                                                            variant="outline"
                                                            className="border-emerald-600 text-emerald-600 hover:bg-emerald-50"
                                                            disabled={isActing}
                                                            onClick={() => reviewClub(club, 'verify')}
                                                        >
                                                            {isActing ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Check className="mr-1 h-4 w-4" />}
                                                            Verify
                                                        </Button>
                                                    )}
                                                    {canReview && (
                                                        <Button
                                                            size="sm"
                                                            variant="outline"
                                                            className="border-rose-600 text-rose-600 hover:bg-rose-50"
                                                            disabled={isActing}
                                                            onClick={() => reviewClub(club, 'reject')}
                                                        >
                                                            {isActing ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <X className="mr-1 h-4 w-4" />}
                                                            Reject
                                                        </Button>
                                                    )}
                                                    {canMerge && (
                                                        <Button size="sm" variant="outline" disabled={isActing} onClick={() => openMerge(club)}>
                                                            <GitMerge className="mr-1 h-4 w-4" />
                                                            Merge
                                                        </Button>
                                                    )}
                                                    {canLink && (
                                                        <Button size="sm" variant="outline" disabled={isActing} onClick={() => openLink(club)}>
                                                            <Link2 className="mr-1 h-4 w-4" />
                                                            {club.api_team_id != null ? 'Edit API link' : 'Link API'}
                                                        </Button>
                                                    )}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                )
                            })}
                        </div>
                    )}
                </CardContent>
            </Card>

            <Dialog open={Boolean(mergeSource)} onOpenChange={(open) => { if (!open) closeMerge() }}>
                <DialogContent className="sm:max-w-xl">
                    <DialogHeader>
                        <DialogTitle>Merge {mergeSource?.name}</DialogTitle>
                        <DialogDescription>
                            Choose the canonical community club. Affiliations will move to the selected club.
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-3">
                        <div className="space-y-2">
                            <Label htmlFor="merge-club-search">Find target club</Label>
                            <div className="relative">
                                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                                <Input
                                    id="merge-club-search"
                                    value={mergeQuery}
                                    onChange={(event) => setMergeQuery(event.target.value)}
                                    placeholder="Search by club or location"
                                    className="pl-9"
                                    autoComplete="off"
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
                            <div className="max-h-64 space-y-1 overflow-y-auto rounded-md border p-1" role="listbox" aria-label="Merge target clubs">
                                {filteredMergeTargets.map((club) => {
                                    const selected = mergeTargetId === String(club.id)
                                    return (
                                        <button
                                            key={club.id}
                                            type="button"
                                            role="option"
                                            aria-selected={selected}
                                            className={`flex w-full items-center justify-between gap-3 rounded px-3 py-2 text-left transition-colors ${selected ? 'bg-primary/10 text-primary' : 'hover:bg-accent'}`}
                                            onClick={() => setMergeTargetId(String(club.id))}
                                        >
                                            <span className="min-w-0">
                                                <span className="block truncate text-sm font-medium">{club.name}</span>
                                                <span className="block truncate text-xs text-muted-foreground">{locationLabel(club)}</span>
                                            </span>
                                            <StatusBadge status={club.status} styles={CLUB_STATUS_STYLES} />
                                        </button>
                                    )
                                })}
                            </div>
                        )}

                        {mergeError && <p className="text-sm text-rose-700" role="alert">{mergeError}</p>}
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={closeMerge} disabled={actingId === mergeSource?.id}>Cancel</Button>
                        <Button onClick={mergeClub} disabled={!mergeTargetId || actingId === mergeSource?.id}>
                            {actingId === mergeSource?.id && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            Merge club
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            <Dialog open={Boolean(linkClub)} onOpenChange={(open) => { if (!open) closeLink() }}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Link {linkClub?.name} to API-Football</DialogTitle>
                        <DialogDescription>
                            Enter the official API-Football team ID that represents this community club.
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-2">
                        <Label htmlFor="local-club-team-api-id">Team API ID</Label>
                        <Input
                            id="local-club-team-api-id"
                            type="number"
                            min="1"
                            step="1"
                            inputMode="numeric"
                            value={teamApiId}
                            onChange={(event) => setTeamApiId(event.target.value)}
                            placeholder="e.g. 42"
                        />
                        {linkError && <p className="text-sm text-rose-700" role="alert">{linkError}</p>}
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={closeLink} disabled={actingId === linkClub?.id}>Cancel</Button>
                        <Button onClick={linkApiClub} disabled={!teamApiId || actingId === linkClub?.id}>
                            {actingId === linkClub?.id && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            Save API link
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </>
    )
}

function AffiliationsTab({ setMessage }) {
    const [affiliations, setAffiliations] = useState([])
    const [loading, setLoading] = useState(true)
    const [status, setStatus] = useState('pending')
    const [reloadKey, setReloadKey] = useState(0)
    const [actingId, setActingId] = useState(null)
    const [notes, setNotes] = useState({})

    useEffect(() => {
        let cancelled = false
        const params = status === 'all' ? {} : { status }
        APIService.adminListAffiliations(params)
            .then((data) => {
                if (!cancelled) setAffiliations(Array.isArray(data?.affiliations) ? data.affiliations : [])
            })
            .catch((err) => {
                if (!cancelled) setMessage({ type: 'error', text: err.message || 'Failed to load affiliations' })
            })
            .finally(() => {
                if (!cancelled) setLoading(false)
            })
        return () => { cancelled = true }
    }, [reloadKey, setMessage, status])

    const reviewAffiliation = async (affiliation, action) => {
        setActingId(affiliation.id)
        try {
            await APIService.adminReviewAffiliation(affiliation.id, {
                action,
                note: notes[affiliation.id]?.trim() || '',
            })
            setMessage({
                type: 'success',
                text: action === 'approve' ? 'Affiliation approved' : 'Affiliation rejected',
            })
            setNotes((current) => {
                const next = { ...current }
                delete next[affiliation.id]
                return next
            })
            setLoading(true)
            setReloadKey((key) => key + 1)
        } catch (err) {
            setMessage({ type: 'error', text: err.message || 'Failed to review affiliation' })
        } finally {
            setActingId(null)
        }
    }

    return (
        <Card>
            <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                    <CardTitle>Player affiliations</CardTitle>
                    <CardDescription>Moderate player-submitted club relationships before they appear publicly</CardDescription>
                </div>
                <Select value={status} onValueChange={(value) => { setLoading(true); setStatus(value) }}>
                    <SelectTrigger className="w-44" aria-label="Filter affiliations by status">
                        <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="pending">Pending</SelectItem>
                        <SelectItem value="self_reported">Self-reported</SelectItem>
                        <SelectItem value="club_confirmed">Club-confirmed</SelectItem>
                        <SelectItem value="rejected">Rejected</SelectItem>
                        <SelectItem value="all">All</SelectItem>
                    </SelectContent>
                </Select>
            </CardHeader>
            <CardContent>
                {loading ? (
                    <Loading />
                ) : affiliations.length === 0 ? (
                    <p className="py-8 text-center text-sm text-muted-foreground">
                        No {status === 'all' ? '' : formatLabel(status).toLowerCase()} affiliations.
                    </p>
                ) : (
                    <div className="space-y-3">
                        {affiliations.map((affiliation) => {
                            const isActing = actingId === affiliation.id
                            const isReviewable = affiliation.status === 'pending'
                            return (
                                <div key={affiliation.id} className="flex flex-col gap-4 rounded-lg border bg-card p-4 lg:flex-row lg:items-start">
                                    <div className="min-w-0 flex-1 space-y-2">
                                        <div className="flex flex-wrap items-center gap-2">
                                            <StatusBadge
                                                status={affiliation.status}
                                                styles={AFFILIATION_STATUS_STYLES}
                                                labels={AFFILIATION_STATUS_LABELS}
                                            />
                                            <span className="text-sm font-semibold text-foreground">{affiliation.club_name || 'Unknown club'}</span>
                                            <Badge variant="outline">Player #{affiliation.player_api_id}</Badge>
                                        </div>
                                        <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
                                            <span>Season: <span className="text-foreground">{affiliation.season || 'Not provided'}</span></span>
                                            {formatDate(affiliation.created_at) && (
                                                <span>Submitted {formatDate(affiliation.created_at)}</span>
                                            )}
                                        </div>
                                        {affiliation.review_note && (
                                            <p className="text-xs text-muted-foreground">Review note: {affiliation.review_note}</p>
                                        )}
                                    </div>

                                    {isReviewable && (
                                        <div className="flex w-full shrink-0 flex-col gap-2 lg:w-80">
                                            <Input
                                                value={notes[affiliation.id] || ''}
                                                onChange={(event) => setNotes((current) => ({ ...current, [affiliation.id]: event.target.value }))}
                                                placeholder="Review note (optional)"
                                                aria-label={`Review note for affiliation ${affiliation.id}`}
                                                maxLength={1000}
                                                disabled={isActing}
                                            />
                                            <div className="flex justify-end gap-2">
                                                <Button
                                                    size="sm"
                                                    variant="outline"
                                                    className="border-emerald-600 text-emerald-600 hover:bg-emerald-50"
                                                    disabled={isActing}
                                                    onClick={() => reviewAffiliation(affiliation, 'approve')}
                                                >
                                                    {isActing ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Check className="mr-1 h-4 w-4" />}
                                                    Approve
                                                </Button>
                                                <Button
                                                    size="sm"
                                                    variant="outline"
                                                    className="border-rose-600 text-rose-600 hover:bg-rose-50"
                                                    disabled={isActing}
                                                    onClick={() => reviewAffiliation(affiliation, 'reject')}
                                                >
                                                    {isActing ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <X className="mr-1 h-4 w-4" />}
                                                    Reject
                                                </Button>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            )
                        })}
                    </div>
                )}
            </CardContent>
        </Card>
    )
}

export function AdminLocalClubs() {
    const [message, setMessage] = useState(null)
    const [tab, setTab] = useState('clubs')

    return (
        <div className="space-y-6">
            <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10">
                    <Landmark className="h-5 w-5 text-primary" />
                </div>
                <div>
                    <h2 className="text-3xl font-bold tracking-tight">Local Clubs</h2>
                    <p className="text-muted-foreground">Moderate community clubs and player affiliations</p>
                </div>
            </div>

            {message && (
                <Alert className={message.type === 'error' ? 'border-rose-500 bg-rose-50' : 'border-emerald-500 bg-emerald-50'}>
                    {message.type === 'error' ? (
                        <AlertCircle className="h-4 w-4 text-rose-600" />
                    ) : (
                        <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                    )}
                    <AlertDescription className={message.type === 'error' ? 'text-rose-800' : 'text-emerald-800'}>
                        {message.text}
                    </AlertDescription>
                </Alert>
            )}

            <Tabs value={tab} onValueChange={setTab}>
                <TabsList className="h-auto flex-wrap justify-start">
                    <TabsTrigger value="clubs">
                        <Landmark className="mr-1.5 h-4 w-4" />
                        Clubs
                    </TabsTrigger>
                    <TabsTrigger value="affiliations">
                        <Link2 className="mr-1.5 h-4 w-4" />
                        Affiliations
                    </TabsTrigger>
                </TabsList>

                <TabsContent value="clubs" className="mt-4">
                    {tab === 'clubs' && <ClubsTab setMessage={setMessage} />}
                </TabsContent>
                <TabsContent value="affiliations" className="mt-4">
                    {tab === 'affiliations' && <AffiliationsTab setMessage={setMessage} />}
                </TabsContent>
            </Tabs>
        </div>
    )
}

export default AdminLocalClubs
