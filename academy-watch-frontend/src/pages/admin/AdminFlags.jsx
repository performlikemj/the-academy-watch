import { useState, useEffect, useCallback } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Checkbox } from '@/components/ui/checkbox'
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
    DialogFooter,
} from '@/components/ui/dialog'
import {
    Loader2, AlertCircle, CheckCircle2, Search, Flag, ExternalLink, Copy, Eye,
    ChevronLeft, ChevronRight,
} from 'lucide-react'
import { APIService } from '@/lib/api'

const CATEGORY_LABELS = {
    player_data: 'Player Info',
    stats: 'Stats',
    club_assignment: 'Club Assignment',
    match_result: 'Match Result',
    missing_data: 'Missing Data',
    transfer: 'Transfer',
    other: 'Other',
}

const CATEGORY_COLORS = {
    player_data: 'bg-blue-50 text-blue-800 border-blue-200',
    stats: 'bg-amber-50 text-amber-800 border-amber-200',
    club_assignment: 'bg-purple-50 text-purple-800 border-purple-200',
    match_result: 'bg-rose-50 text-rose-800 border-rose-200',
    missing_data: 'bg-orange-50 text-orange-800 border-orange-200',
    transfer: 'bg-teal-50 text-teal-800 border-teal-200',
    other: 'bg-stone-100 text-stone-700 border-stone-200',
}

const STATUS_COLORS = {
    pending: 'bg-amber-50 text-amber-800 border-amber-200',
    investigating: 'bg-blue-50 text-blue-800 border-blue-200',
    resolved: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    dismissed: 'bg-stone-100 text-stone-700 border-stone-200',
}

const STATUS_TABS = ['all', 'pending', 'investigating', 'resolved', 'dismissed']

export function AdminFlags() {
    const [flags, setFlags] = useState([])
    const [stats, setStats] = useState(null)
    const [loading, setLoading] = useState(true)
    const [message, setMessage] = useState(null)

    // Filters
    const [statusFilter, setStatusFilter] = useState('pending')
    const [categoryFilter, setCategoryFilter] = useState('')
    const [sourceFilter, setSourceFilter] = useState('')
    const [search, setSearch] = useState('')
    const [page, setPage] = useState(1)
    const [total, setTotal] = useState(0)
    const perPage = 25

    // Detail dialog
    const [selectedFlag, setSelectedFlag] = useState(null)
    const [adminNote, setAdminNote] = useState('')
    const [updating, setUpdating] = useState(false)

    // Bulk selection
    const [selectedIds, setSelectedIds] = useState(new Set())
    const [bulkUpdating, setBulkUpdating] = useState(false)

    const loadFlags = useCallback(async () => {
        setLoading(true)
        try {
            const params = { page, per_page: perPage }
            if (statusFilter && statusFilter !== 'all') params.status = statusFilter
            if (categoryFilter) params.category = categoryFilter
            if (sourceFilter) params.source = sourceFilter
            if (search) params.search = search
            const res = await APIService.adminFlags(params)
            setFlags(res.flags || [])
            setTotal(res.total || 0)
        } catch (err) {
            setMessage({ type: 'error', text: err.message })
        } finally {
            setLoading(false)
        }
    }, [statusFilter, categoryFilter, sourceFilter, search, page])

    const loadStats = useCallback(async () => {
        try {
            const res = await APIService.adminFlagsStats()
            setStats(res)
        } catch {
            // non-critical
        }
    }, [])

    useEffect(() => { loadFlags() }, [loadFlags])
    useEffect(() => { loadStats() }, [loadStats])

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
            loadFlags()
            loadStats()
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
            loadFlags()
            loadStats()
        } catch (err) {
            setMessage({ type: 'error', text: err.message })
        } finally {
            setBulkUpdating(false)
        }
    }

    const toggleSelect = (id) => {
        setSelectedIds(prev => {
            const next = new Set(prev)
            next.has(id) ? next.delete(id) : next.add(id)
            return next
        })
    }

    const toggleSelectAll = () => {
        if (selectedIds.size === flags.length) {
            setSelectedIds(new Set())
        } else {
            setSelectedIds(new Set(flags.map(f => f.id)))
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
            `Category: ${CATEGORY_LABELS[flag.category] || flag.category}`,
            ``,
            `Issue: ${flag.reason}`,
            ``,
            `Reported via The Academy Watch`,
        ].join('\n')
        navigator.clipboard.writeText(text)
        setMessage({ type: 'success', text: 'Correction email copied to clipboard' })
    }

    const totalPages = Math.ceil(total / perPage)

    return (
        <div>
            <h2 className="text-3xl font-bold tracking-tight mb-6">Data Flags</h2>

            {/* Stats bar */}
            {stats && (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
                    {['pending', 'investigating', 'resolved', 'dismissed'].map(s => (
                        <Card key={s} className="cursor-pointer hover:ring-1 hover:ring-primary/30"
                              onClick={() => { setStatusFilter(s); setPage(1) }}>
                            <CardContent className="py-3 px-4">
                                <p className="text-xs text-muted-foreground capitalize">{s}</p>
                                <p className="text-2xl font-bold">{stats.by_status?.[s] || 0}</p>
                            </CardContent>
                        </Card>
                    ))}
                </div>
            )}

            {/* Filters */}
            <div className="flex flex-col sm:flex-row gap-3 mb-4">
                <div className="flex gap-1 flex-wrap">
                    {STATUS_TABS.map(s => (
                        <Button
                            key={s}
                            variant={statusFilter === s ? 'default' : 'outline'}
                            size="sm"
                            onClick={() => { setStatusFilter(s); setPage(1) }}
                            className="capitalize"
                        >
                            {s}
                        </Button>
                    ))}
                </div>
                <select
                    className="h-8 rounded-md border border-input bg-background px-2 text-sm"
                    value={categoryFilter}
                    onChange={e => { setCategoryFilter(e.target.value); setPage(1) }}
                >
                    <option value="">All Categories</option>
                    {Object.entries(CATEGORY_LABELS).map(([k, v]) => (
                        <option key={k} value={k}>{v}</option>
                    ))}
                </select>
                <select
                    className="h-8 rounded-md border border-input bg-background px-2 text-sm"
                    value={sourceFilter}
                    onChange={e => { setSourceFilter(e.target.value); setPage(1) }}
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
                        onChange={e => { setSearch(e.target.value); setPage(1) }}
                    />
                </div>
            </div>

            {/* Bulk actions */}
            {selectedIds.size > 0 && (
                <div className="flex items-center gap-2 mb-3 p-2 bg-muted rounded-md">
                    <span className="text-sm text-muted-foreground">{selectedIds.size} selected</span>
                    <Button size="sm" variant="outline" onClick={() => handleBulkAction('resolved')} disabled={bulkUpdating}>
                        Resolve
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => handleBulkAction('dismissed')} disabled={bulkUpdating}>
                        Dismiss
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setSelectedIds(new Set())}>
                        Clear
                    </Button>
                </div>
            )}

            {/* Message */}
            {message && (
                <Alert className={`mb-4 ${message.type === 'error' ? 'border-rose-500 bg-rose-50' : 'border-emerald-500 bg-emerald-50'}`}>
                    {message.type === 'error'
                        ? <AlertCircle className="h-4 w-4 text-rose-600" />
                        : <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                    }
                    <AlertDescription className={message.type === 'error' ? 'text-rose-800' : 'text-emerald-800'}>
                        {message.text}
                    </AlertDescription>
                </Alert>
            )}

            {/* Flag list */}
            {loading ? (
                <div className="flex items-center justify-center py-12">
                    <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
            ) : flags.length === 0 ? (
                <div className="text-center py-12 text-muted-foreground">
                    <Flag className="h-8 w-8 mx-auto mb-3 opacity-50" />
                    <p>No flags found</p>
                </div>
            ) : (
                <div className="space-y-2">
                    {/* Select all */}
                    <div className="flex items-center gap-2 px-4 py-1">
                        <Checkbox
                            checked={selectedIds.size === flags.length && flags.length > 0}
                            onCheckedChange={toggleSelectAll}
                        />
                        <span className="text-xs text-muted-foreground">Select all</span>
                    </div>

                    {flags.map(flag => (
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
                                        <Badge className={CATEGORY_COLORS[flag.category] || CATEGORY_COLORS.other}>
                                            {CATEGORY_LABELS[flag.category] || flag.category}
                                        </Badge>
                                        <Badge className={STATUS_COLORS[flag.status] || STATUS_COLORS.pending}>
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
                <div className="flex items-center justify-center gap-2 mt-4">
                    <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>
                        <ChevronLeft className="h-4 w-4" />
                    </Button>
                    <span className="text-sm text-muted-foreground">
                        Page {page} of {totalPages}
                    </span>
                    <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>
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
                                <Badge className={CATEGORY_COLORS[selectedFlag.category] || CATEGORY_COLORS.other}>
                                    {CATEGORY_LABELS[selectedFlag.category] || selectedFlag.category}
                                </Badge>
                                <Badge className={STATUS_COLORS[selectedFlag.status]}>
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
                                <Label className="text-xs">Admin Note</Label>
                                <Textarea
                                    className="mt-1"
                                    placeholder="Add a note..."
                                    value={adminNote}
                                    onChange={e => setAdminNote(e.target.value)}
                                    rows={3}
                                />
                            </div>

                            {/* Actions */}
                            <div className="flex flex-wrap gap-2">
                                {selectedFlag.status !== 'investigating' && (
                                    <Button size="sm" variant="outline" onClick={() => handleStatusUpdate(selectedFlag.id, 'investigating')} disabled={updating}>
                                        Investigate
                                    </Button>
                                )}
                                {selectedFlag.status !== 'resolved' && (
                                    <Button size="sm" onClick={() => handleStatusUpdate(selectedFlag.id, 'resolved')} disabled={updating}>
                                        {updating && <Loader2 className="h-4 w-4 mr-1 animate-spin" />}
                                        Resolve
                                    </Button>
                                )}
                                {selectedFlag.status !== 'dismissed' && (
                                    <Button size="sm" variant="secondary" onClick={() => handleStatusUpdate(selectedFlag.id, 'dismissed')} disabled={updating}>
                                        Dismiss
                                    </Button>
                                )}
                                <Button size="sm" variant="outline" onClick={() => copyApiFootballEmail(selectedFlag)} title="Copy pre-formatted email for API-Football">
                                    <Copy className="h-4 w-4 mr-1" />
                                    Copy API-Football Email
                                </Button>
                            </div>
                        </div>
                    )}
                </DialogContent>
            </Dialog>
        </div>
    )
}
