import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { APIService } from '@/lib/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Checkbox } from '@/components/ui/checkbox'
import { Skeleton } from '@/components/ui/skeleton'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
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
    Check,
    CheckCircle2,
    ChevronLeft,
    ChevronRight,
    Clock,
    Copy,
    ExternalLink,
    Eye,
    Flag,
    Link2,
    Loader2,
    MessageSquare,
    Plus,
    Search,
    Shield,
    Trash2,
    User,
    X,
    XCircle,
} from 'lucide-react'

// ---------------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------------

const TABS = [
    { value: 'manual', label: 'Manual players' },
    { value: 'takes', label: 'Community takes' },
    { value: 'submissions', label: 'User submissions' },
    { value: 'flags', label: 'Flags' },
    { value: 'tracking', label: 'Tracking requests' },
    { value: 'links', label: 'Player links' },
]

const TAB_VALUES = TABS.map((t) => t.value)

// ---------------------------------------------------------------------------
// fetchInboxCounts — per-tab pending counts. Also consumed by the sidebar
// badge (wired by the lead). Failures degrade to 0 so one broken endpoint
// never blanks the whole badge.
// ---------------------------------------------------------------------------

// eslint-disable-next-line react-refresh/only-export-components
export async function fetchInboxCounts() {
    const [takesStats, manual, flagsStats, tracking, links] = await Promise.allSettled([
        APIService.adminTakesStats(),
        APIService.adminListManualPlayers({ status: 'pending' }),
        APIService.adminFlagsStats(),
        APIService.adminListTrackingRequests({ status: 'pending' }),
        APIService.adminGetPendingPlayerLinks(),
    ])
    const arrLen = (r) => (r.status === 'fulfilled' && Array.isArray(r.value) ? r.value.length : 0)
    const counts = {
        manual: arrLen(manual),
        takes: takesStats.status === 'fulfilled' ? Number(takesStats.value?.takes?.pending) || 0 : 0,
        submissions: takesStats.status === 'fulfilled' ? Number(takesStats.value?.submissions?.pending) || 0 : 0,
        flags: flagsStats.status === 'fulfilled' ? Number(flagsStats.value?.by_status?.pending) || 0 : 0,
        tracking: arrLen(tracking),
        links: arrLen(links),
    }
    counts.total = TAB_VALUES.reduce((sum, key) => sum + counts[key], 0)
    return counts
}

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

function formatDateTime(dateStr) {
    if (!dateStr) return '-'
    return new Date(dateStr).toLocaleDateString('en-GB', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
    })
}

const REVIEW_STATUS_COLORS = {
    pending: 'bg-amber-50 text-amber-800 border-amber-200',
    approved: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    rejected: 'bg-rose-50 text-rose-800 border-rose-200',
}

function ReviewStatusBadge({ status }) {
    return (
        <Badge className={REVIEW_STATUS_COLORS[status] || 'bg-secondary text-muted-foreground'}>
            {status}
        </Badge>
    )
}

const TAKE_SOURCE_COLORS = {
    editor: 'bg-primary/10 text-primary border-primary/20',
    reddit: 'bg-orange-50 text-orange-800 border-orange-200',
    twitter: 'bg-sky-50 text-sky-800 border-sky-200',
    submission: 'bg-emerald-50 text-emerald-800 border-emerald-200',
}

function TakeSourceBadge({ sourceType }) {
    return (
        <Badge className={TAKE_SOURCE_COLORS[sourceType] || 'bg-secondary text-muted-foreground'}>
            {sourceType}
        </Badge>
    )
}

function ListSkeleton({ rows = 3 }) {
    return (
        <div className="space-y-3" data-testid="inbox-skeleton">
            {Array.from({ length: rows }).map((_, i) => (
                <div key={i} className="border rounded-lg p-4 space-y-2">
                    <Skeleton className="h-4 w-1/3" />
                    <Skeleton className="h-3 w-2/3" />
                    <Skeleton className="h-3 w-1/2" />
                </div>
            ))}
        </div>
    )
}

function EmptyState({ icon: Icon, children }) {
    return (
        <div className="text-center py-8 text-muted-foreground">
            <Icon className="h-12 w-12 mx-auto mb-3 opacity-50" />
            <p>{children}</p>
        </div>
    )
}

// ---------------------------------------------------------------------------
// Tab: Manual players (ported from AdminPlayers Submissions tab)
// ---------------------------------------------------------------------------

function ManualPlayersTab({ setMessage, refreshCounts }) {
    const [submissions, setSubmissions] = useState([])
    const [loading, setLoading] = useState(true)
    const [filter, setFilter] = useState('pending')
    const [reloadKey, setReloadKey] = useState(0)
    const [reviewDialog, setReviewDialog] = useState({ open: false, submission: null, action: null })
    const [adminNotes, setAdminNotes] = useState('')
    const [processing, setProcessing] = useState(false)

    useEffect(() => {
        let cancelled = false
        const params = filter === 'all' ? {} : { status: filter }
        APIService.adminListManualPlayers(params)
            .then((data) => { if (!cancelled) setSubmissions(Array.isArray(data) ? data : []) })
            .catch((err) => {
                console.error('Failed to load manual player submissions', err)
                if (!cancelled) setMessage({ type: 'error', text: 'Failed to load manual player submissions' })
            })
            .finally(() => { if (!cancelled) setLoading(false) })
        return () => { cancelled = true }
    }, [filter, reloadKey, setMessage])

    const changeFilter = (f) => {
        setLoading(true)
        setFilter(f)
    }

    const handleReview = async () => {
        if (!reviewDialog.submission || !reviewDialog.action) return
        setProcessing(true)
        try {
            await APIService.adminReviewManualPlayer(reviewDialog.submission.id, {
                status: reviewDialog.action,
                admin_notes: adminNotes,
            })
            setReviewDialog({ open: false, submission: null, action: null })
            setMessage({ type: 'success', text: `Submission ${reviewDialog.action}` })
            setLoading(true)
            setReloadKey((k) => k + 1)
            refreshCounts()
        } catch (error) {
            setMessage({ type: 'error', text: `Review failed: ${error.message}` })
        } finally {
            setProcessing(false)
        }
    }

    const getStatusBadge = (status) => {
        if (status === 'approved') return <Badge className="bg-emerald-600"><CheckCircle2 className="h-3 w-3 mr-1" /> Approved</Badge>
        if (status === 'rejected') return <Badge variant="destructive"><XCircle className="h-3 w-3 mr-1" /> Rejected</Badge>
        return <Badge variant="secondary"><Clock className="h-3 w-3 mr-1" /> Pending</Badge>
    }

    return (
        <Card>
            <CardHeader>
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div>
                        <CardTitle>Manual Player Submissions</CardTitle>
                        <CardDescription>Writer-submitted players awaiting review</CardDescription>
                    </div>
                    <div className="flex gap-2">
                        {['pending', 'approved', 'rejected', 'all'].map((f) => (
                            <Button
                                key={f}
                                variant={filter === f ? 'default' : 'outline'}
                                size="sm"
                                onClick={() => changeFilter(f)}
                                data-testid={`manual-filter-${f}`}
                            >
                                {f.charAt(0).toUpperCase() + f.slice(1)}
                            </Button>
                        ))}
                    </div>
                </div>
            </CardHeader>
            <CardContent>
                {loading ? (
                    <ListSkeleton />
                ) : submissions.length === 0 ? (
                    <EmptyState icon={User}>No {filter === 'all' ? '' : `${filter} `}submissions found</EmptyState>
                ) : (
                    <div className="space-y-3">
                        {submissions.map((sub) => (
                            <div key={sub.id} className="border rounded-lg p-4 flex flex-col sm:flex-row gap-4 justify-between items-start bg-card">
                                <div className="space-y-2 flex-1">
                                    <div className="flex items-center gap-2">
                                        <h3 className="font-semibold">{sub.player_name}</h3>
                                        <Badge variant="outline">{sub.team_name}</Badge>
                                        {getStatusBadge(sub.status)}
                                    </div>
                                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-1 text-sm text-muted-foreground">
                                        <div><User className="h-3 w-3 inline mr-1" />By: <span className="font-medium text-foreground">{sub.user_name}</span></div>
                                        <div><Clock className="h-3 w-3 inline mr-1" />{new Date(sub.created_at).toLocaleDateString()}</div>
                                        {sub.position && <div>Position: {sub.position}</div>}
                                        {sub.league_name && <div>League: {sub.league_name}</div>}
                                    </div>
                                    {sub.notes && (
                                        <div className="bg-muted/50 p-2 rounded text-sm mt-1">{sub.notes}</div>
                                    )}
                                    {sub.admin_notes && (
                                        <div className="bg-primary/5 text-primary p-2 rounded text-sm mt-1 border border-primary/20">
                                            <Shield className="h-3 w-3 inline mr-1" /> {sub.admin_notes}
                                        </div>
                                    )}
                                </div>
                                {sub.status === 'pending' && (
                                    <div className="flex flex-col gap-2 min-w-[120px]">
                                        <Button
                                            className="w-full bg-emerald-600 hover:bg-emerald-700"
                                            size="sm"
                                            onClick={() => { setReviewDialog({ open: true, submission: sub, action: 'approved' }); setAdminNotes('') }}
                                            data-testid={`manual-approve-${sub.id}`}
                                        >
                                            <CheckCircle2 className="h-4 w-4 mr-1" /> Approve
                                        </Button>
                                        <Button
                                            variant="destructive"
                                            size="sm"
                                            className="w-full"
                                            onClick={() => { setReviewDialog({ open: true, submission: sub, action: 'rejected' }); setAdminNotes('') }}
                                            data-testid={`manual-reject-${sub.id}`}
                                        >
                                            <XCircle className="h-4 w-4 mr-1" /> Reject
                                        </Button>
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                )}

                <Dialog open={reviewDialog.open} onOpenChange={(open) => !open && setReviewDialog({ ...reviewDialog, open: false })}>
                    <DialogContent>
                        <DialogHeader>
                            <DialogTitle>{reviewDialog.action === 'approved' ? 'Approve' : 'Reject'} Submission</DialogTitle>
                            <DialogDescription>
                                {reviewDialog.action === 'approved' ? 'This player will be added to tracking.' : 'Provide a reason for rejection.'}
                            </DialogDescription>
                        </DialogHeader>
                        <div className="py-4">
                            <Label htmlFor="manual-admin-notes">Admin Notes (Optional)</Label>
                            <Textarea
                                id="manual-admin-notes"
                                value={adminNotes}
                                onChange={(e) => setAdminNotes(e.target.value)}
                                placeholder="Optional notes..."
                                className="mt-2"
                            />
                        </div>
                        <DialogFooter>
                            <Button variant="outline" onClick={() => setReviewDialog({ ...reviewDialog, open: false })}>Cancel</Button>
                            <Button
                                variant={reviewDialog.action === 'approved' ? 'default' : 'destructive'}
                                onClick={handleReview}
                                disabled={processing}
                                className={reviewDialog.action === 'approved' ? 'bg-emerald-600 hover:bg-emerald-700' : ''}
                                data-testid="manual-review-confirm"
                            >
                                {processing && <Loader2 className="h-4 w-4 mr-1 animate-spin" />}
                                Confirm
                            </Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>
            </CardContent>
        </Card>
    )
}

// ---------------------------------------------------------------------------
// Tab: Community takes (ported from AdminCuration takes tab)
// ---------------------------------------------------------------------------

const EMPTY_TAKE = {
    source_type: 'editor',
    source_author: '',
    source_url: '',
    source_platform: '',
    content: '',
    player_name: '',
    player_id: '',
}

function CommunityTakesTab({ setMessage, refreshCounts }) {
    const [takes, setTakes] = useState([])
    const [loading, setLoading] = useState(true)
    const [filter, setFilter] = useState('pending')
    const [reloadKey, setReloadKey] = useState(0)

    const [createDialogOpen, setCreateDialogOpen] = useState(false)
    const [createLoading, setCreateLoading] = useState(false)
    const [newTake, setNewTake] = useState(EMPTY_TAKE)

    const [rejectTarget, setRejectTarget] = useState(null)
    const [rejectReason, setRejectReason] = useState('')
    const [rejectLoading, setRejectLoading] = useState(false)

    useEffect(() => {
        let cancelled = false
        APIService.adminListCommunityTakes({ status: filter })
            .then((data) => { if (!cancelled) setTakes(data?.takes || []) })
            .catch((err) => {
                console.error('Failed to load takes', err)
                if (!cancelled) setMessage({ type: 'error', text: 'Failed to load community takes' })
            })
            .finally(() => { if (!cancelled) setLoading(false) })
        return () => { cancelled = true }
    }, [filter, reloadKey, setMessage])

    const reload = () => setReloadKey((k) => k + 1)

    const changeFilter = (f) => {
        setLoading(true)
        setFilter(f)
    }

    const handleApprove = async (takeId) => {
        try {
            await APIService.adminApproveTake(takeId)
            setMessage({ type: 'success', text: 'Take approved' })
            reload()
            refreshCounts()
        } catch (err) {
            setMessage({ type: 'error', text: err.message || 'Failed to approve take' })
        }
    }

    const handleReject = async () => {
        if (!rejectTarget) return
        setRejectLoading(true)
        try {
            await APIService.adminRejectTake(rejectTarget.id, { reason: rejectReason })
            setMessage({ type: 'success', text: 'Take rejected' })
            setRejectTarget(null)
            setRejectReason('')
            reload()
            refreshCounts()
        } catch (err) {
            setMessage({ type: 'error', text: err.message || 'Failed to reject' })
        } finally {
            setRejectLoading(false)
        }
    }

    const handleDelete = async (takeId) => {
        try {
            await APIService.adminDeleteTake(takeId)
            setMessage({ type: 'success', text: 'Take deleted' })
            reload()
            refreshCounts()
        } catch (err) {
            setMessage({ type: 'error', text: err.message || 'Failed to delete take' })
        }
    }

    const handleCreate = async () => {
        if (!newTake.source_author.trim() || !newTake.content.trim()) {
            setMessage({ type: 'error', text: 'Author and content are required' })
            return
        }
        setCreateLoading(true)
        try {
            await APIService.adminCreateTake({
                source_type: newTake.source_type,
                source_author: newTake.source_author.trim(),
                source_url: newTake.source_url.trim() || null,
                source_platform: newTake.source_platform.trim() || null,
                content: newTake.content.trim(),
                player_name: newTake.player_name.trim() || null,
                player_id: newTake.player_id ? parseInt(newTake.player_id) : null,
                status: 'approved',
            })
            setMessage({ type: 'success', text: 'Take created' })
            setCreateDialogOpen(false)
            setNewTake(EMPTY_TAKE)
            reload()
            refreshCounts()
        } catch (err) {
            setMessage({ type: 'error', text: err.message || 'Failed to create take' })
        } finally {
            setCreateLoading(false)
        }
    }

    return (
        <Card>
            <CardHeader>
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div>
                        <CardTitle>Community Takes</CardTitle>
                        <CardDescription>Curated takes from various sources</CardDescription>
                    </div>
                    <div className="flex items-center gap-2">
                        <Select value={filter} onValueChange={changeFilter}>
                            <SelectTrigger className="w-32" data-testid="takes-filter">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="pending">Pending</SelectItem>
                                <SelectItem value="approved">Approved</SelectItem>
                                <SelectItem value="rejected">Rejected</SelectItem>
                            </SelectContent>
                        </Select>
                        <Button onClick={() => setCreateDialogOpen(true)} data-testid="inbox-add-take">
                            <Plus className="h-4 w-4 mr-2" />
                            Add Take
                        </Button>
                    </div>
                </div>
            </CardHeader>
            <CardContent>
                {loading ? (
                    <ListSkeleton />
                ) : takes.length === 0 ? (
                    <EmptyState icon={MessageSquare}>No {filter} takes found</EmptyState>
                ) : (
                    <div className="space-y-4">
                        {takes.map((take) => (
                            <div key={take.id} className="border rounded-lg p-4">
                                <div className="flex items-start justify-between gap-4">
                                    <div className="flex-1">
                                        <div className="flex items-center gap-2 mb-2">
                                            <TakeSourceBadge sourceType={take.source_type} />
                                            <ReviewStatusBadge status={take.status} />
                                            {take.player_name && (
                                                <Badge variant="outline">{take.player_name}</Badge>
                                            )}
                                        </div>
                                        <p className="text-sm text-muted-foreground mb-2">
                                            <User className="h-3 w-3 inline mr-1" />
                                            {take.source_author}
                                            {take.source_platform && ` on ${take.source_platform}`}
                                            {take.source_url && (
                                                <a
                                                    href={take.source_url}
                                                    target="_blank"
                                                    rel="noopener noreferrer"
                                                    className="ml-2 text-primary hover:underline"
                                                >
                                                    <ExternalLink className="h-3 w-3 inline" />
                                                </a>
                                            )}
                                        </p>
                                        <p className="text-sm">{take.content}</p>
                                        <p className="text-xs text-muted-foreground mt-2">
                                            Created: {formatDateTime(take.created_at)}
                                        </p>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        {take.status === 'pending' && (
                                            <>
                                                <Button
                                                    size="sm"
                                                    variant="outline"
                                                    className="text-emerald-600 border-emerald-600 hover:bg-emerald-50"
                                                    onClick={() => handleApprove(take.id)}
                                                    data-testid={`take-approve-${take.id}`}
                                                >
                                                    <Check className="h-4 w-4" />
                                                </Button>
                                                <Button
                                                    size="sm"
                                                    variant="outline"
                                                    className="text-rose-600 border-rose-600 hover:bg-rose-50"
                                                    onClick={() => { setRejectTarget(take); setRejectReason('') }}
                                                    data-testid={`take-reject-${take.id}`}
                                                >
                                                    <X className="h-4 w-4" />
                                                </Button>
                                            </>
                                        )}
                                        <Button
                                            size="sm"
                                            variant="destructive"
                                            onClick={() => handleDelete(take.id)}
                                            data-testid={`take-delete-${take.id}`}
                                        >
                                            <Trash2 className="h-4 w-4" />
                                        </Button>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}

                {/* Create Take Dialog */}
                <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
                    <DialogContent className="max-w-lg">
                        <DialogHeader>
                            <DialogTitle>Add Community Take</DialogTitle>
                            <DialogDescription>Create a new community take directly</DialogDescription>
                        </DialogHeader>
                        <div className="space-y-4 py-4">
                            <div className="grid grid-cols-2 gap-4">
                                <div className="space-y-2">
                                    <Label htmlFor="take-source-type">Source Type</Label>
                                    <Select
                                        value={newTake.source_type}
                                        onValueChange={(value) => setNewTake({ ...newTake, source_type: value })}
                                    >
                                        <SelectTrigger id="take-source-type">
                                            <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent>
                                            <SelectItem value="editor">Editor</SelectItem>
                                            <SelectItem value="reddit">Reddit</SelectItem>
                                            <SelectItem value="twitter">Twitter</SelectItem>
                                        </SelectContent>
                                    </Select>
                                </div>
                                <div className="space-y-2">
                                    <Label htmlFor="take-author">Author</Label>
                                    <Input
                                        id="take-author"
                                        value={newTake.source_author}
                                        onChange={(e) => setNewTake({ ...newTake, source_author: e.target.value })}
                                        placeholder="e.g., u/username or @handle"
                                    />
                                </div>
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div className="space-y-2">
                                    <Label htmlFor="take-platform">Platform (optional)</Label>
                                    <Input
                                        id="take-platform"
                                        value={newTake.source_platform}
                                        onChange={(e) => setNewTake({ ...newTake, source_platform: e.target.value })}
                                        placeholder="e.g., r/reddevils"
                                    />
                                </div>
                                <div className="space-y-2">
                                    <Label htmlFor="take-url">Source URL (optional)</Label>
                                    <Input
                                        id="take-url"
                                        value={newTake.source_url}
                                        onChange={(e) => setNewTake({ ...newTake, source_url: e.target.value })}
                                        placeholder="https://..."
                                    />
                                </div>
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="take-player-name">Player Name (optional)</Label>
                                <Input
                                    id="take-player-name"
                                    value={newTake.player_name}
                                    onChange={(e) => setNewTake({ ...newTake, player_name: e.target.value })}
                                    placeholder="e.g., Kobbie Mainoo"
                                />
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="take-content">Content</Label>
                                <Textarea
                                    id="take-content"
                                    value={newTake.content}
                                    onChange={(e) => setNewTake({ ...newTake, content: e.target.value })}
                                    placeholder="The take content (1-3 sentences)"
                                    rows={3}
                                />
                                <p className="text-xs text-muted-foreground">
                                    {newTake.content.length}/280 characters
                                </p>
                            </div>
                        </div>
                        <DialogFooter>
                            <Button variant="outline" onClick={() => setCreateDialogOpen(false)}>
                                Cancel
                            </Button>
                            <Button onClick={handleCreate} disabled={createLoading} data-testid="create-take-confirm">
                                {createLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                Create Take
                            </Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>

                {/* Reject Take Dialog */}
                <Dialog open={!!rejectTarget} onOpenChange={(v) => { if (!v) setRejectTarget(null) }}>
                    <DialogContent>
                        <DialogHeader>
                            <DialogTitle>Reject Take?</DialogTitle>
                            <DialogDescription>Optionally provide a reason for rejection.</DialogDescription>
                        </DialogHeader>
                        <div className="py-4">
                            <Label htmlFor="take-reject-reason">Rejection Reason (optional)</Label>
                            <Textarea
                                id="take-reject-reason"
                                value={rejectReason}
                                onChange={(e) => setRejectReason(e.target.value)}
                                placeholder="e.g., Off-topic, spam, inappropriate content"
                                className="mt-2"
                            />
                        </div>
                        <DialogFooter>
                            <Button variant="outline" onClick={() => setRejectTarget(null)}>
                                Cancel
                            </Button>
                            <Button variant="destructive" onClick={handleReject} disabled={rejectLoading} data-testid="take-reject-confirm">
                                {rejectLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                Reject
                            </Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>
            </CardContent>
        </Card>
    )
}

// ---------------------------------------------------------------------------
// Tab: User submissions (ported from AdminCuration submissions tab)
// ---------------------------------------------------------------------------

function UserSubmissionsTab({ setMessage, refreshCounts }) {
    const [submissions, setSubmissions] = useState([])
    const [loading, setLoading] = useState(true)
    const [filter, setFilter] = useState('pending')
    const [reloadKey, setReloadKey] = useState(0)

    const [rejectTarget, setRejectTarget] = useState(null)
    const [rejectReason, setRejectReason] = useState('')
    const [rejectLoading, setRejectLoading] = useState(false)

    useEffect(() => {
        let cancelled = false
        APIService.adminListSubmissions({ status: filter })
            .then((data) => { if (!cancelled) setSubmissions(data?.submissions || []) })
            .catch((err) => {
                console.error('Failed to load submissions', err)
                if (!cancelled) setMessage({ type: 'error', text: 'Failed to load submissions' })
            })
            .finally(() => { if (!cancelled) setLoading(false) })
        return () => { cancelled = true }
    }, [filter, reloadKey, setMessage])

    const reload = () => setReloadKey((k) => k + 1)

    const changeFilter = (f) => {
        setLoading(true)
        setFilter(f)
    }

    const handleApprove = async (submissionId) => {
        try {
            await APIService.adminApproveSubmission(submissionId)
            setMessage({ type: 'success', text: 'Submission approved and take created' })
            reload()
            refreshCounts()
        } catch (err) {
            setMessage({ type: 'error', text: err.message || 'Failed to approve submission' })
        }
    }

    const handleReject = async () => {
        if (!rejectTarget) return
        setRejectLoading(true)
        try {
            await APIService.adminRejectSubmission(rejectTarget.id, { reason: rejectReason })
            setMessage({ type: 'success', text: 'Submission rejected' })
            setRejectTarget(null)
            setRejectReason('')
            reload()
            refreshCounts()
        } catch (err) {
            setMessage({ type: 'error', text: err.message || 'Failed to reject' })
        } finally {
            setRejectLoading(false)
        }
    }

    return (
        <Card>
            <CardHeader>
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div>
                        <CardTitle>User Submissions</CardTitle>
                        <CardDescription>Takes submitted by users for review</CardDescription>
                    </div>
                    <Select value={filter} onValueChange={changeFilter}>
                        <SelectTrigger className="w-32" data-testid="submissions-filter">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="pending">Pending</SelectItem>
                            <SelectItem value="approved">Approved</SelectItem>
                            <SelectItem value="rejected">Rejected</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
            </CardHeader>
            <CardContent>
                {loading ? (
                    <ListSkeleton />
                ) : submissions.length === 0 ? (
                    <EmptyState icon={MessageSquare}>No {filter} submissions found</EmptyState>
                ) : (
                    <div className="space-y-4">
                        {submissions.map((sub) => (
                            <div key={sub.id} className="border rounded-lg p-4">
                                <div className="flex items-start justify-between gap-4">
                                    <div className="flex-1">
                                        <div className="flex items-center gap-2 mb-2">
                                            <ReviewStatusBadge status={sub.status} />
                                            <Badge variant="outline">{sub.player_name}</Badge>
                                        </div>
                                        <p className="text-sm text-muted-foreground mb-2">
                                            <User className="h-3 w-3 inline mr-1" />
                                            {sub.submitter_name || 'Anonymous'}
                                            {sub.submitter_email && ` (${sub.submitter_email})`}
                                        </p>
                                        <p className="text-sm">{sub.content}</p>
                                        <p className="text-xs text-muted-foreground mt-2">
                                            Submitted: {formatDateTime(sub.created_at)}
                                        </p>
                                        {sub.rejection_reason && (
                                            <p className="text-xs text-rose-600 mt-1">
                                                Rejection reason: {sub.rejection_reason}
                                            </p>
                                        )}
                                    </div>
                                    {sub.status === 'pending' && (
                                        <div className="flex items-center gap-2">
                                            <Button
                                                size="sm"
                                                variant="outline"
                                                className="text-emerald-600 border-emerald-600 hover:bg-emerald-50"
                                                onClick={() => handleApprove(sub.id)}
                                                data-testid={`submission-approve-${sub.id}`}
                                            >
                                                <Check className="h-4 w-4 mr-1" />
                                                Approve
                                            </Button>
                                            <Button
                                                size="sm"
                                                variant="outline"
                                                className="text-rose-600 border-rose-600 hover:bg-rose-50"
                                                onClick={() => { setRejectTarget(sub); setRejectReason('') }}
                                                data-testid={`submission-reject-${sub.id}`}
                                            >
                                                <X className="h-4 w-4 mr-1" />
                                                Reject
                                            </Button>
                                        </div>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                )}

                {/* Reject Submission Dialog */}
                <Dialog open={!!rejectTarget} onOpenChange={(v) => { if (!v) setRejectTarget(null) }}>
                    <DialogContent>
                        <DialogHeader>
                            <DialogTitle>Reject Submission?</DialogTitle>
                            <DialogDescription>Optionally provide a reason for rejection.</DialogDescription>
                        </DialogHeader>
                        <div className="py-4">
                            <Label htmlFor="submission-reject-reason">Rejection Reason (optional)</Label>
                            <Textarea
                                id="submission-reject-reason"
                                value={rejectReason}
                                onChange={(e) => setRejectReason(e.target.value)}
                                placeholder="e.g., Off-topic, spam, inappropriate content"
                                className="mt-2"
                            />
                        </div>
                        <DialogFooter>
                            <Button variant="outline" onClick={() => setRejectTarget(null)}>
                                Cancel
                            </Button>
                            <Button variant="destructive" onClick={handleReject} disabled={rejectLoading} data-testid="submission-reject-confirm">
                                {rejectLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                Reject
                            </Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>
            </CardContent>
        </Card>
    )
}

// ---------------------------------------------------------------------------
// Tab: Flags (ported from AdminFlags)
// ---------------------------------------------------------------------------

const FLAG_CATEGORY_LABELS = {
    player_data: 'Player Info',
    stats: 'Stats',
    club_assignment: 'Club Assignment',
    match_result: 'Match Result',
    missing_data: 'Missing Data',
    transfer: 'Transfer',
    other: 'Other',
}

const FLAG_CATEGORY_COLORS = {
    player_data: 'bg-blue-50 text-blue-800 border-blue-200',
    stats: 'bg-amber-50 text-amber-800 border-amber-200',
    club_assignment: 'bg-purple-50 text-purple-800 border-purple-200',
    match_result: 'bg-rose-50 text-rose-800 border-rose-200',
    missing_data: 'bg-orange-50 text-orange-800 border-orange-200',
    transfer: 'bg-teal-50 text-teal-800 border-teal-200',
    other: 'bg-stone-100 text-stone-700 border-stone-200',
}

const FLAG_STATUS_COLORS = {
    pending: 'bg-amber-50 text-amber-800 border-amber-200',
    investigating: 'bg-blue-50 text-blue-800 border-blue-200',
    resolved: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    dismissed: 'bg-stone-100 text-stone-700 border-stone-200',
}

const FLAG_STATUS_TABS = ['all', 'pending', 'investigating', 'resolved', 'dismissed']
const FLAGS_PER_PAGE = 25

function FlagsTab({ setMessage, refreshCounts }) {
    const [flags, setFlags] = useState([])
    const [stats, setStats] = useState(null)
    const [loading, setLoading] = useState(true)
    const [reloadKey, setReloadKey] = useState(0)

    // Filters
    const [statusFilter, setStatusFilter] = useState('pending')
    const [categoryFilter, setCategoryFilter] = useState('')
    const [sourceFilter, setSourceFilter] = useState('')
    const [search, setSearch] = useState('')
    const [page, setPage] = useState(1)
    const [total, setTotal] = useState(0)

    // Detail dialog
    const [selectedFlag, setSelectedFlag] = useState(null)
    const [adminNote, setAdminNote] = useState('')
    const [updating, setUpdating] = useState(false)

    // Bulk selection
    const [selectedIds, setSelectedIds] = useState(new Set())
    const [bulkUpdating, setBulkUpdating] = useState(false)

    useEffect(() => {
        let cancelled = false
        const params = { page, per_page: FLAGS_PER_PAGE }
        if (statusFilter && statusFilter !== 'all') params.status = statusFilter
        if (categoryFilter) params.category = categoryFilter
        if (sourceFilter) params.source = sourceFilter
        if (search) params.search = search
        APIService.adminFlags(params)
            .then((res) => {
                if (cancelled) return
                setFlags(res.flags || [])
                setTotal(res.total || 0)
            })
            .catch((err) => { if (!cancelled) setMessage({ type: 'error', text: err.message }) })
            .finally(() => { if (!cancelled) setLoading(false) })
        return () => { cancelled = true }
    }, [statusFilter, categoryFilter, sourceFilter, search, page, reloadKey, setMessage])

    useEffect(() => {
        let cancelled = false
        APIService.adminFlagsStats()
            .then((res) => { if (!cancelled) setStats(res) })
            .catch(() => { /* non-critical */ })
        return () => { cancelled = true }
    }, [reloadKey])

    const reload = () => setReloadKey((k) => k + 1)

    const changeStatusFilter = (s) => {
        setLoading(true)
        setStatusFilter(s)
        setPage(1)
    }

    const handleStatusUpdate = async (flagId, newStatus) => {
        setUpdating(true)
        try {
            const res = await APIService.adminFlagUpdate(flagId, {
                status: newStatus,
                note: adminNote.trim() || undefined,
            })
            if (selectedFlag?.id === flagId) {
                setSelectedFlag(res.flag)
            }
            setMessage({ type: 'success', text: `Flag ${newStatus}` })
            reload()
            refreshCounts()
        } catch (err) {
            setMessage({ type: 'error', text: err.message })
        } finally {
            setUpdating(false)
        }
    }

    const handleBulkAction = async (action) => {
        if (selectedIds.size === 0) return
        setBulkUpdating(true)
        try {
            await APIService.adminFlagsBulk({
                flag_ids: [...selectedIds],
                action,
            })
            setSelectedIds(new Set())
            setMessage({ type: 'success', text: `${selectedIds.size} flags ${action}` })
            reload()
            refreshCounts()
        } catch (err) {
            setMessage({ type: 'error', text: err.message })
        } finally {
            setBulkUpdating(false)
        }
    }

    const toggleSelect = (id) => {
        setSelectedIds((prev) => {
            const next = new Set(prev)
            if (next.has(id)) {
                next.delete(id)
            } else {
                next.add(id)
            }
            return next
        })
    }

    const toggleSelectAll = () => {
        if (selectedIds.size === flags.length) {
            setSelectedIds(new Set())
        } else {
            setSelectedIds(new Set(flags.map((f) => f.id)))
        }
    }

    const copyApiFootballEmail = (flag) => {
        const text = [
            `Subject: Data Correction - Player ID ${flag.player_api_id || 'N/A'} / ${flag.player_name || 'Unknown'}`,
            `To: contact@api-football.com`,
            ``,
            `Player API ID: ${flag.player_api_id || 'N/A'}`,
            `Team API ID: ${flag.primary_team_api_id || 'N/A'}`,
            `Season: ${flag.season || 'N/A'}`,
            `Category: ${FLAG_CATEGORY_LABELS[flag.category] || flag.category}`,
            ``,
            `Issue: ${flag.reason}`,
            ``,
            `Reported via The Academy Watch`,
        ].join('\n')
        navigator.clipboard.writeText(text)
        setMessage({ type: 'success', text: 'Correction email copied to clipboard' })
    }

    const totalPages = Math.ceil(total / FLAGS_PER_PAGE)

    return (
        <Card>
            <CardHeader>
                <CardTitle>Data Flags</CardTitle>
                <CardDescription>User-reported data errors from the public flag form and newsletters</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
                {/* Stats bar */}
                {stats && (
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        {['pending', 'investigating', 'resolved', 'dismissed'].map((s) => (
                            <Card
                                key={s}
                                className="cursor-pointer hover:ring-1 hover:ring-primary/30"
                                onClick={() => changeStatusFilter(s)}
                                data-testid={`flags-stat-${s}`}
                            >
                                <CardContent className="py-3 px-4">
                                    <p className="text-xs text-muted-foreground capitalize">{s}</p>
                                    <p className="text-2xl font-bold">{stats.by_status?.[s] || 0}</p>
                                </CardContent>
                            </Card>
                        ))}
                    </div>
                )}

                {/* Filters */}
                <div className="flex flex-col sm:flex-row gap-3">
                    <div className="flex gap-1 flex-wrap">
                        {FLAG_STATUS_TABS.map((s) => (
                            <Button
                                key={s}
                                variant={statusFilter === s ? 'default' : 'outline'}
                                size="sm"
                                onClick={() => changeStatusFilter(s)}
                                className="capitalize"
                                data-testid={`flags-status-${s}`}
                            >
                                {s}
                            </Button>
                        ))}
                    </div>
                    <select
                        className="h-8 rounded-md border border-input bg-background px-2 text-sm"
                        value={categoryFilter}
                        onChange={(e) => { setLoading(true); setCategoryFilter(e.target.value); setPage(1) }}
                        data-testid="flags-category-filter"
                    >
                        <option value="">All Categories</option>
                        {Object.entries(FLAG_CATEGORY_LABELS).map(([k, v]) => (
                            <option key={k} value={k}>{v}</option>
                        ))}
                    </select>
                    <select
                        className="h-8 rounded-md border border-input bg-background px-2 text-sm"
                        value={sourceFilter}
                        onChange={(e) => { setLoading(true); setSourceFilter(e.target.value); setPage(1) }}
                        data-testid="flags-source-filter"
                    >
                        <option value="">All Sources</option>
                        <option value="website">Website</option>
                        <option value="newsletter">Newsletter</option>
                    </select>
                    <div className="relative flex-1">
                        <Search className="absolute left-2 top-2 h-4 w-4 text-muted-foreground" />
                        <Input
                            className="pl-8 h-8"
                            placeholder="Search flags..."
                            value={search}
                            onChange={(e) => { setLoading(true); setSearch(e.target.value); setPage(1) }}
                            data-testid="flags-search"
                        />
                    </div>
                </div>

                {/* Bulk actions */}
                {selectedIds.size > 0 && (
                    <div className="flex items-center gap-2 p-2 bg-muted rounded-md">
                        <span className="text-sm text-muted-foreground">{selectedIds.size} selected</span>
                        <Button size="sm" variant="outline" onClick={() => handleBulkAction('resolved')} disabled={bulkUpdating} data-testid="flags-bulk-resolve">
                            Resolve
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => handleBulkAction('dismissed')} disabled={bulkUpdating} data-testid="flags-bulk-dismiss">
                            Dismiss
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setSelectedIds(new Set())}>
                            Clear
                        </Button>
                    </div>
                )}

                {/* Flag list */}
                {loading ? (
                    <ListSkeleton rows={4} />
                ) : flags.length === 0 ? (
                    <EmptyState icon={Flag}>No flags found</EmptyState>
                ) : (
                    <div className="space-y-2">
                        {/* Select all */}
                        <div className="flex items-center gap-2 px-4 py-1">
                            <Checkbox
                                checked={selectedIds.size === flags.length && flags.length > 0}
                                onCheckedChange={toggleSelectAll}
                                data-testid="flags-select-all"
                            />
                            <span className="text-xs text-muted-foreground">Select all</span>
                        </div>

                        {flags.map((flag) => (
                            <div
                                key={flag.id}
                                className="rounded-md border px-4 py-3 bg-card hover:bg-accent/50 transition-colors"
                            >
                                <div className="flex items-start gap-3">
                                    <Checkbox
                                        checked={selectedIds.has(flag.id)}
                                        onCheckedChange={() => toggleSelect(flag.id)}
                                        className="mt-1"
                                    />
                                    <div className="flex-1 min-w-0 cursor-pointer" onClick={() => { setSelectedFlag(flag); setAdminNote(flag.admin_note || '') }}>
                                        <div className="flex flex-wrap items-center gap-1.5 mb-1">
                                            <Badge className={FLAG_CATEGORY_COLORS[flag.category] || FLAG_CATEGORY_COLORS.other}>
                                                {FLAG_CATEGORY_LABELS[flag.category] || flag.category}
                                            </Badge>
                                            <Badge className={FLAG_STATUS_COLORS[flag.status] || FLAG_STATUS_COLORS.pending}>
                                                {flag.status}
                                            </Badge>
                                            {flag.source === 'newsletter' && (
                                                <Badge variant="outline" className="text-xs">Newsletter</Badge>
                                            )}
                                            {flag.forwarded_to_api_football && (
                                                <Badge variant="outline" className="text-xs text-emerald-700 border-emerald-300">Forwarded</Badge>
                                            )}
                                        </div>
                                        <div className="flex flex-wrap items-center gap-2 text-sm">
                                            {flag.player_name && (
                                                <span className="font-medium">{flag.player_name}</span>
                                            )}
                                            {flag.team_name && (
                                                <span className="text-muted-foreground">({flag.team_name})</span>
                                            )}
                                            {!flag.player_name && !flag.team_name && flag.player_api_id && (
                                                <span className="text-muted-foreground">Player #{flag.player_api_id}</span>
                                            )}
                                        </div>
                                        <p className="text-sm text-muted-foreground mt-1 line-clamp-2">{flag.reason}</p>
                                        <div className="flex items-center gap-3 mt-1.5 text-xs text-muted-foreground">
                                            {flag.created_at && <span>{new Date(flag.created_at).toLocaleDateString()}</span>}
                                            {flag.email && <span>{flag.email}</span>}
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-1 shrink-0">
                                        <Button
                                            variant="ghost"
                                            size="sm"
                                            onClick={() => { setSelectedFlag(flag); setAdminNote(flag.admin_note || '') }}
                                            title="View details"
                                            data-testid={`flag-view-${flag.id}`}
                                        >
                                            <Eye className="h-4 w-4" />
                                        </Button>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}

                {/* Pagination */}
                {totalPages > 1 && (
                    <div className="flex items-center justify-center gap-2">
                        <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => { setLoading(true); setPage((p) => p - 1) }} data-testid="flags-prev">
                            <ChevronLeft className="h-4 w-4" />
                        </Button>
                        <span className="text-sm text-muted-foreground">
                            Page {page} of {totalPages}
                        </span>
                        <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => { setLoading(true); setPage((p) => p + 1) }} data-testid="flags-next">
                            <ChevronRight className="h-4 w-4" />
                        </Button>
                    </div>
                )}

                {/* Detail Dialog */}
                <Dialog open={!!selectedFlag} onOpenChange={(v) => { if (!v) setSelectedFlag(null) }}>
                    <DialogContent className="max-w-lg">
                        <DialogHeader>
                            <DialogTitle>Flag #{selectedFlag?.id}</DialogTitle>
                            <DialogDescription>
                                Submitted {selectedFlag?.created_at ? new Date(selectedFlag.created_at).toLocaleString() : 'unknown'}
                                {selectedFlag?.source === 'newsletter' ? ' via newsletter' : ' via website'}
                            </DialogDescription>
                        </DialogHeader>

                        {selectedFlag && (
                            <div className="space-y-4">
                                {/* Badges */}
                                <div className="flex flex-wrap gap-1.5">
                                    <Badge className={FLAG_CATEGORY_COLORS[selectedFlag.category] || FLAG_CATEGORY_COLORS.other}>
                                        {FLAG_CATEGORY_LABELS[selectedFlag.category] || selectedFlag.category}
                                    </Badge>
                                    <Badge className={FLAG_STATUS_COLORS[selectedFlag.status]}>
                                        {selectedFlag.status}
                                    </Badge>
                                </div>

                                {/* Context */}
                                <div className="space-y-1 text-sm">
                                    {selectedFlag.player_name && (
                                        <div><span className="text-muted-foreground">Player:</span> {selectedFlag.player_name}
                                            {selectedFlag.player_api_id && (
                                                <span className="text-muted-foreground ml-1">(#{selectedFlag.player_api_id})</span>
                                            )}
                                        </div>
                                    )}
                                    {selectedFlag.team_name && (
                                        <div><span className="text-muted-foreground">Team:</span> {selectedFlag.team_name}
                                            {selectedFlag.primary_team_api_id && (
                                                <span className="text-muted-foreground ml-1">(#{selectedFlag.primary_team_api_id})</span>
                                            )}
                                        </div>
                                    )}
                                    {selectedFlag.season && (
                                        <div><span className="text-muted-foreground">Season:</span> {selectedFlag.season}</div>
                                    )}
                                    {selectedFlag.email && (
                                        <div><span className="text-muted-foreground">Email:</span> {selectedFlag.email}</div>
                                    )}
                                    {selectedFlag.page_url && (
                                        <div>
                                            <span className="text-muted-foreground">Page:</span>{' '}
                                            <a href={selectedFlag.page_url} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline inline-flex items-center gap-1">
                                                View <ExternalLink className="h-3 w-3" />
                                            </a>
                                        </div>
                                    )}
                                </div>

                                {/* Reason */}
                                <div>
                                    <Label className="text-xs text-muted-foreground">Issue Description</Label>
                                    <div className="mt-1 rounded-md border p-3 bg-muted/50 text-sm whitespace-pre-wrap">
                                        {selectedFlag.reason}
                                    </div>
                                </div>

                                {/* Admin note */}
                                <div>
                                    <Label className="text-xs" htmlFor="flag-admin-note">Admin Note</Label>
                                    <Textarea
                                        id="flag-admin-note"
                                        className="mt-1"
                                        placeholder="Add a note..."
                                        value={adminNote}
                                        onChange={(e) => setAdminNote(e.target.value)}
                                        rows={3}
                                    />
                                </div>

                                {/* Actions */}
                                <div className="flex flex-wrap gap-2">
                                    {selectedFlag.status !== 'investigating' && (
                                        <Button size="sm" variant="outline" onClick={() => handleStatusUpdate(selectedFlag.id, 'investigating')} disabled={updating} data-testid="flag-investigate">
                                            Investigate
                                        </Button>
                                    )}
                                    {selectedFlag.status !== 'resolved' && (
                                        <Button size="sm" onClick={() => handleStatusUpdate(selectedFlag.id, 'resolved')} disabled={updating} data-testid="flag-resolve">
                                            {updating && <Loader2 className="h-4 w-4 mr-1 animate-spin" />}
                                            Resolve
                                        </Button>
                                    )}
                                    {selectedFlag.status !== 'dismissed' && (
                                        <Button size="sm" variant="secondary" onClick={() => handleStatusUpdate(selectedFlag.id, 'dismissed')} disabled={updating} data-testid="flag-dismiss">
                                            Dismiss
                                        </Button>
                                    )}
                                    <Button size="sm" variant="outline" onClick={() => copyApiFootballEmail(selectedFlag)} title="Copy pre-formatted email for API-Football" data-testid="flag-copy-email">
                                        <Copy className="h-4 w-4 mr-1" />
                                        Copy API-Football Email
                                    </Button>
                                </div>
                            </div>
                        )}
                    </DialogContent>
                </Dialog>
            </CardContent>
        </Card>
    )
}

// ---------------------------------------------------------------------------
// Tab: Tracking requests (ported from AdminTeams Tracking Requests tab)
// ---------------------------------------------------------------------------

function TrackingRequestsTab({ setMessage, refreshCounts }) {
    const [requests, setRequests] = useState([])
    const [loading, setLoading] = useState(true)
    const [filter, setFilter] = useState('pending')
    const [reloadKey, setReloadKey] = useState(0)

    const [rejectTarget, setRejectTarget] = useState(null)
    const [rejectNote, setRejectNote] = useState('')
    const [rejectLoading, setRejectLoading] = useState(false)

    useEffect(() => {
        let cancelled = false
        APIService.adminListTrackingRequests({ status: filter === 'all' ? '' : filter })
            .then((data) => { if (!cancelled) setRequests(Array.isArray(data) ? data : []) })
            .catch((err) => {
                console.error('Failed to load tracking requests', err)
                if (!cancelled) setMessage({ type: 'error', text: 'Failed to load tracking requests' })
            })
            .finally(() => { if (!cancelled) setLoading(false) })
        return () => { cancelled = true }
    }, [filter, reloadKey, setMessage])

    const reload = () => setReloadKey((k) => k + 1)

    const changeFilter = (f) => {
        setLoading(true)
        setFilter(f)
    }

    const handleAction = async (requestId, status, note = '') => {
        try {
            await APIService.adminUpdateTrackingRequest(requestId, { status, note })
            setMessage({ type: 'success', text: `Request ${status}` })
            reload()
            refreshCounts()
            return true
        } catch (err) {
            console.error('Failed to update request', err)
            setMessage({ type: 'error', text: 'Failed to update request' })
            return false
        }
    }

    const handleReject = async () => {
        if (!rejectTarget) return
        setRejectLoading(true)
        const ok = await handleAction(rejectTarget.id, 'rejected', rejectNote)
        setRejectLoading(false)
        if (ok) {
            setRejectTarget(null)
            setRejectNote('')
        }
    }

    return (
        <Card>
            <CardHeader>
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div>
                        <CardTitle>Tracking Requests</CardTitle>
                        <CardDescription>User requests to track new teams</CardDescription>
                    </div>
                    <Select value={filter} onValueChange={changeFilter}>
                        <SelectTrigger className="w-full sm:w-40" data-testid="tracking-filter">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="pending">Pending</SelectItem>
                            <SelectItem value="approved">Approved</SelectItem>
                            <SelectItem value="rejected">Rejected</SelectItem>
                            <SelectItem value="all">All</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
            </CardHeader>
            <CardContent>
                {loading ? (
                    <ListSkeleton />
                ) : requests.length === 0 ? (
                    <EmptyState icon={Flag}>No tracking requests found</EmptyState>
                ) : (
                    <div className="space-y-3">
                        {requests.map((req) => (
                            <div key={req.id} className="p-3 sm:p-4 border rounded-lg">
                                <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                                    <div className="flex items-center gap-3">
                                        {req.team_logo && (
                                            <Avatar className="h-10 w-10 sm:h-12 sm:w-12 shrink-0">
                                                <AvatarImage src={req.team_logo} alt={req.team_name} />
                                                <AvatarFallback>{req.team_name?.slice(0, 2).toUpperCase()}</AvatarFallback>
                                            </Avatar>
                                        )}
                                        <div className="min-w-0">
                                            <p className="font-medium truncate">{req.team_name}</p>
                                            <p className="text-sm text-muted-foreground truncate">{req.team_league}</p>
                                            <p className="text-xs text-muted-foreground mt-1">
                                                {new Date(req.created_at).toLocaleDateString()}
                                                {req.email && <span className="hidden sm:inline"> by {req.email}</span>}
                                            </p>
                                        </div>
                                    </div>
                                    <Badge variant={
                                        req.status === 'pending' ? 'secondary' :
                                            req.status === 'approved' ? 'default' : 'destructive'
                                    } className="self-start shrink-0">
                                        {req.status === 'pending' && <Clock className="h-3 w-3 mr-1" />}
                                        {req.status === 'approved' && <CheckCircle2 className="h-3 w-3 mr-1" />}
                                        {req.status === 'rejected' && <XCircle className="h-3 w-3 mr-1" />}
                                        {req.status}
                                    </Badge>
                                </div>
                                {req.reason && (
                                    <p className="text-sm mt-3 p-2 bg-muted rounded">{req.reason}</p>
                                )}
                                {req.admin_note && (
                                    <p className="text-sm mt-2 text-muted-foreground italic">
                                        Admin note: {req.admin_note}
                                    </p>
                                )}
                                {req.status === 'pending' && (
                                    <div className="flex flex-wrap gap-2 mt-3">
                                        <Button
                                            size="sm"
                                            onClick={() => handleAction(req.id, 'approved')}
                                            className="flex-1 sm:flex-none"
                                            data-testid={`tracking-approve-${req.id}`}
                                        >
                                            <CheckCircle2 className="h-4 w-4 mr-1" />
                                            Approve
                                        </Button>
                                        <Button
                                            size="sm"
                                            variant="outline"
                                            onClick={() => { setRejectTarget(req); setRejectNote('') }}
                                            className="flex-1 sm:flex-none"
                                            data-testid={`tracking-reject-${req.id}`}
                                        >
                                            <XCircle className="h-4 w-4 mr-1" />
                                            Reject
                                        </Button>
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                )}

                {/* Reject Tracking Request Dialog */}
                <Dialog open={!!rejectTarget} onOpenChange={(v) => { if (!v) setRejectTarget(null) }}>
                    <DialogContent>
                        <DialogHeader>
                            <DialogTitle>Reject Tracking Request?</DialogTitle>
                            <DialogDescription>
                                Reject the request to track {rejectTarget?.team_name || 'this team'}. Optionally add a note.
                            </DialogDescription>
                        </DialogHeader>
                        <div className="py-4">
                            <Label htmlFor="tracking-reject-note">Admin Note (optional)</Label>
                            <Textarea
                                id="tracking-reject-note"
                                value={rejectNote}
                                onChange={(e) => setRejectNote(e.target.value)}
                                placeholder="e.g., League not covered by API-Football"
                                className="mt-2"
                            />
                        </div>
                        <DialogFooter>
                            <Button variant="outline" onClick={() => setRejectTarget(null)}>
                                Cancel
                            </Button>
                            <Button variant="destructive" onClick={handleReject} disabled={rejectLoading} data-testid="tracking-reject-confirm">
                                {rejectLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                Reject
                            </Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>
            </CardContent>
        </Card>
    )
}

// ---------------------------------------------------------------------------
// Tab: Player links (pending link suggestions on player pages)
// Backend: GET /admin/player-links/pending + PUT /admin/player-links/<id>
// ---------------------------------------------------------------------------

const LINK_TYPE_COLORS = {
    article: 'bg-blue-50 text-blue-800 border-blue-200',
    highlight: 'bg-amber-50 text-amber-800 border-amber-200',
    social: 'bg-sky-50 text-sky-800 border-sky-200',
    stats: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    other: 'bg-stone-100 text-stone-700 border-stone-200',
}

function PlayerLinksTab({ setMessage, refreshCounts }) {
    const [links, setLinks] = useState([])
    const [loading, setLoading] = useState(true)
    const [reloadKey, setReloadKey] = useState(0)
    const [actingId, setActingId] = useState(null)

    useEffect(() => {
        let cancelled = false
        APIService.adminGetPendingPlayerLinks()
            .then((data) => { if (!cancelled) setLinks(Array.isArray(data) ? data : []) })
            .catch((err) => {
                console.error('Failed to load pending player links', err)
                if (!cancelled) setMessage({ type: 'error', text: 'Failed to load pending player links' })
            })
            .finally(() => { if (!cancelled) setLoading(false) })
        return () => { cancelled = true }
    }, [reloadKey, setMessage])

    const handleAction = async (link, status) => {
        setActingId(link.id)
        try {
            await APIService.adminUpdatePlayerLink(link.id, { status })
            setMessage({ type: 'success', text: `Link ${status}` })
            setReloadKey((k) => k + 1)
            refreshCounts()
        } catch (err) {
            setMessage({ type: 'error', text: err.message || 'Failed to update link' })
        } finally {
            setActingId(null)
        }
    }

    return (
        <Card>
            <CardHeader>
                <CardTitle>Player Links</CardTitle>
                <CardDescription>User-submitted links on player pages awaiting review</CardDescription>
            </CardHeader>
            <CardContent>
                {loading ? (
                    <ListSkeleton />
                ) : links.length === 0 ? (
                    <EmptyState icon={Link2}>No pending player links</EmptyState>
                ) : (
                    <div className="space-y-3">
                        {links.map((link) => (
                            <div key={link.id} className="border rounded-lg p-4 flex flex-col sm:flex-row gap-4 justify-between items-start bg-card">
                                <div className="space-y-1 flex-1 min-w-0">
                                    <div className="flex items-center gap-2 flex-wrap">
                                        <Badge className={LINK_TYPE_COLORS[link.link_type] || LINK_TYPE_COLORS.other}>
                                            {link.link_type}
                                        </Badge>
                                        <Badge variant="outline">Player #{link.player_id}</Badge>
                                        {Number(link.upvotes) > 0 && (
                                            <Badge variant="secondary">{link.upvotes} upvotes</Badge>
                                        )}
                                    </div>
                                    <p className="text-sm font-medium truncate">{link.title || link.url}</p>
                                    <a
                                        href={link.url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="text-xs text-primary hover:underline inline-flex items-center gap-1 max-w-full"
                                    >
                                        <span className="truncate">{link.url}</span>
                                        <ExternalLink className="h-3 w-3 shrink-0" />
                                    </a>
                                    <p className="text-xs text-muted-foreground">
                                        Submitted: {formatDateTime(link.created_at)}
                                    </p>
                                </div>
                                <div className="flex items-center gap-2 shrink-0">
                                    <Button
                                        size="sm"
                                        variant="outline"
                                        className="text-emerald-600 border-emerald-600 hover:bg-emerald-50"
                                        onClick={() => handleAction(link, 'approved')}
                                        disabled={actingId === link.id}
                                        data-testid={`link-approve-${link.id}`}
                                    >
                                        {actingId === link.id ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Check className="h-4 w-4 mr-1" />}
                                        Approve
                                    </Button>
                                    <Button
                                        size="sm"
                                        variant="outline"
                                        className="text-rose-600 border-rose-600 hover:bg-rose-50"
                                        onClick={() => handleAction(link, 'rejected')}
                                        disabled={actingId === link.id}
                                        data-testid={`link-reject-${link.id}`}
                                    >
                                        <X className="h-4 w-4 mr-1" />
                                        Reject
                                    </Button>
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

export function AdminInbox() {
    const [searchParams, setSearchParams] = useSearchParams()
    const requestedTab = searchParams.get('tab')
    const activeTab = TAB_VALUES.includes(requestedTab) ? requestedTab : 'manual'

    const [message, setMessage] = useState(null)
    const [counts, setCounts] = useState(null)
    const [countsReload, setCountsReload] = useState(0)

    useEffect(() => {
        let cancelled = false
        fetchInboxCounts()
            .then((c) => { if (!cancelled) setCounts(c) })
            .catch((err) => console.error('Failed to load inbox counts', err))
        return () => { cancelled = true }
    }, [countsReload])

    const refreshCounts = useCallback(() => setCountsReload((k) => k + 1), [])

    const handleTabChange = (value) => {
        setSearchParams((prev) => {
            const next = new URLSearchParams(prev)
            next.set('tab', value)
            return next
        }, { replace: true })
    }

    const tabProps = { setMessage, refreshCounts }

    return (
        <div className="space-y-6">
            <header className="flex flex-col sm:flex-row sm:items-end justify-between gap-2">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">Inbox</h1>
                    <p className="text-muted-foreground mt-1">
                        Everything waiting on an admin decision — submissions, takes, flags and requests in one queue
                    </p>
                </div>
                {counts === null ? (
                    <Skeleton className="h-6 w-28" data-testid="inbox-counts-skeleton" />
                ) : (
                    <Badge
                        variant={counts.total > 0 ? 'default' : 'secondary'}
                        data-testid="inbox-total-pending"
                    >
                        {counts.total} pending
                    </Badge>
                )}
            </header>

            {/* Message Display */}
            {message && (
                <Alert className={message.type === 'error' ? 'border-rose-500 bg-rose-50' : 'border-emerald-500 bg-emerald-50'}>
                    {message.type === 'error' ? <AlertCircle className="h-4 w-4 text-rose-600" /> : <CheckCircle2 className="h-4 w-4 text-emerald-600" />}
                    <AlertDescription className={message.type === 'error' ? 'text-rose-800' : 'text-emerald-800'}>
                        {message.text}
                    </AlertDescription>
                </Alert>
            )}

            <Tabs value={activeTab} onValueChange={handleTabChange} className="space-y-4">
                <TabsList className="flex flex-wrap h-auto">
                    {TABS.map((tab) => (
                        <TabsTrigger key={tab.value} value={tab.value} data-testid={`inbox-tab-${tab.value}`}>
                            {tab.label}
                            {counts !== null && counts[tab.value] > 0 && (
                                <Badge variant="secondary" className="ml-1.5 px-1.5 py-0 text-xs">
                                    {counts[tab.value]}
                                </Badge>
                            )}
                        </TabsTrigger>
                    ))}
                </TabsList>

                <TabsContent value="manual" className="space-y-4">
                    {activeTab === 'manual' && <ManualPlayersTab {...tabProps} />}
                </TabsContent>
                <TabsContent value="takes" className="space-y-4">
                    {activeTab === 'takes' && <CommunityTakesTab {...tabProps} />}
                </TabsContent>
                <TabsContent value="submissions" className="space-y-4">
                    {activeTab === 'submissions' && <UserSubmissionsTab {...tabProps} />}
                </TabsContent>
                <TabsContent value="flags" className="space-y-4">
                    {activeTab === 'flags' && <FlagsTab {...tabProps} />}
                </TabsContent>
                <TabsContent value="tracking" className="space-y-4">
                    {activeTab === 'tracking' && <TrackingRequestsTab {...tabProps} />}
                </TabsContent>
                <TabsContent value="links" className="space-y-4">
                    {activeTab === 'links' && <PlayerLinksTab {...tabProps} />}
                </TabsContent>
            </Tabs>
        </div>
    )
}

export default AdminInbox
