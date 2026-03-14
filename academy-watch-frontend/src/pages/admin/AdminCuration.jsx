import { useState, useEffect, useCallback } from 'react'
import { APIService } from '@/lib/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
    DialogFooter,
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
    Plus,
    Trash2,
    Check,
    X,
    MessageSquare,
    ExternalLink,
    User
} from 'lucide-react'

export function AdminCuration() {
    // Stats
    const [stats, setStats] = useState(null)
    const [statsLoading, setStatsLoading] = useState(true)

    // Takes list
    const [takes, setTakes] = useState([])
    const [takesLoading, setTakesLoading] = useState(false)
    const [takesFilter, setTakesFilter] = useState('pending')

    // Submissions list
    const [submissions, setSubmissions] = useState([])
    const [submissionsLoading, setSubmissionsLoading] = useState(false)
    const [submissionsFilter, setSubmissionsFilter] = useState('pending')

    // Messages
    const [message, setMessage] = useState(null)

    // Create take dialog
    const [createDialogOpen, setCreateDialogOpen] = useState(false)
    const [createLoading, setCreateLoading] = useState(false)
    const [newTake, setNewTake] = useState({
        source_type: 'editor',
        source_author: '',
        source_url: '',
        source_platform: '',
        content: '',
        player_name: '',
        player_id: '',
    })

    // Reject dialog
    const [rejectTarget, setRejectTarget] = useState(null)
    const [rejectType, setRejectType] = useState(null) // 'take' or 'submission'
    const [rejectReason, setRejectReason] = useState('')
    const [rejectLoading, setRejectLoading] = useState(false)

    // Load stats
    const loadStats = useCallback(async () => {
        try {
            setStatsLoading(true)
            const data = await APIService.adminTakesStats()
            setStats(data)
        } catch (err) {
            console.error('Failed to load stats', err)
        } finally {
            setStatsLoading(false)
        }
    }, [])

    // Load takes
    const loadTakes = useCallback(async () => {
        try {
            setTakesLoading(true)
            const data = await APIService.adminListCommunityTakes({ status: takesFilter })
            setTakes(data?.takes || [])
        } catch (err) {
            console.error('Failed to load takes', err)
            setMessage({ type: 'error', text: 'Failed to load community takes' })
        } finally {
            setTakesLoading(false)
        }
    }, [takesFilter])

    // Load submissions
    const loadSubmissions = useCallback(async () => {
        try {
            setSubmissionsLoading(true)
            const data = await APIService.adminListSubmissions({ status: submissionsFilter })
            setSubmissions(data?.submissions || [])
        } catch (err) {
            console.error('Failed to load submissions', err)
            setMessage({ type: 'error', text: 'Failed to load submissions' })
        } finally {
            setSubmissionsLoading(false)
        }
    }, [submissionsFilter])

    useEffect(() => {
        loadStats()
    }, [loadStats])

    useEffect(() => {
        loadTakes()
    }, [loadTakes])

    useEffect(() => {
        loadSubmissions()
    }, [loadSubmissions])

    // Approve take
    const handleApproveTake = async (takeId) => {
        try {
            await APIService.adminApproveTake(takeId)
            setMessage({ type: 'success', text: 'Take approved' })
            loadTakes()
            loadStats()
        } catch (err) {
            setMessage({ type: 'error', text: err.message || 'Failed to approve take' })
        }
    }

    // Reject take
    const handleRejectTake = async () => {
        if (!rejectTarget) return
        setRejectLoading(true)
        try {
            if (rejectType === 'take') {
                await APIService.adminRejectTake(rejectTarget.id, { reason: rejectReason })
            } else {
                await APIService.adminRejectSubmission(rejectTarget.id, { reason: rejectReason })
            }
            setMessage({ type: 'success', text: `${rejectType === 'take' ? 'Take' : 'Submission'} rejected` })
            setRejectTarget(null)
            setRejectReason('')
            loadTakes()
            loadSubmissions()
            loadStats()
        } catch (err) {
            setMessage({ type: 'error', text: err.message || 'Failed to reject' })
        } finally {
            setRejectLoading(false)
        }
    }

    // Approve submission
    const handleApproveSubmission = async (submissionId) => {
        try {
            await APIService.adminApproveSubmission(submissionId)
            setMessage({ type: 'success', text: 'Submission approved and take created' })
            loadSubmissions()
            loadTakes()
            loadStats()
        } catch (err) {
            setMessage({ type: 'error', text: err.message || 'Failed to approve submission' })
        }
    }

    // Create take
    const handleCreateTake = async () => {
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
            setNewTake({
                source_type: 'editor',
                source_author: '',
                source_url: '',
                source_platform: '',
                content: '',
                player_name: '',
                player_id: '',
            })
            loadTakes()
            loadStats()
        } catch (err) {
            setMessage({ type: 'error', text: err.message || 'Failed to create take' })
        } finally {
            setCreateLoading(false)
        }
    }

    // Delete take
    const handleDeleteTake = async (takeId) => {
        try {
            await APIService.adminDeleteTake(takeId)
            setMessage({ type: 'success', text: 'Take deleted' })
            loadTakes()
            loadStats()
        } catch (err) {
            setMessage({ type: 'error', text: err.message || 'Failed to delete take' })
        }
    }

    const formatDate = (dateStr) => {
        if (!dateStr) return '-'
        return new Date(dateStr).toLocaleDateString('en-GB', {
            day: 'numeric',
            month: 'short',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        })
    }

    const getSourceBadge = (sourceType) => {
        const colors = {
            editor: 'bg-primary/10 text-primary border-primary/20',
            reddit: 'bg-orange-50 text-orange-800 border-orange-200',
            twitter: 'bg-sky-50 text-sky-800 border-sky-200',
            submission: 'bg-emerald-50 text-emerald-800 border-emerald-200',
        }
        return (
            <Badge className={colors[sourceType] || 'bg-secondary text-muted-foreground'}>
                {sourceType}
            </Badge>
        )
    }

    const getStatusBadge = (status) => {
        const colors = {
            pending: 'bg-amber-50 text-amber-800 border-amber-200',
            approved: 'bg-emerald-50 text-emerald-800 border-emerald-200',
            rejected: 'bg-rose-50 text-rose-800 border-rose-200',
        }
        return (
            <Badge className={colors[status] || 'bg-secondary text-muted-foreground'}>
                {status}
            </Badge>
        )
    }

    return (
        <div className="space-y-6">
            <div>
                <h2 className="text-3xl font-bold tracking-tight">Community Curation</h2>
                <p className="text-muted-foreground mt-1">Review and manage community takes and submissions</p>
            </div>

            {/* Message Display */}
            {message && (
                <Alert className={message.type === 'error' ? 'border-rose-500 bg-rose-50' : 'border-emerald-500 bg-emerald-50'}>
                    {message.type === 'error' ? <AlertCircle className="h-4 w-4 text-rose-600" /> : <CheckCircle2 className="h-4 w-4 text-emerald-600" />}
                    <AlertDescription className={message.type === 'error' ? 'text-rose-800' : 'text-emerald-800'}>
                        {message.text}
                    </AlertDescription>
                </Alert>
            )}

            {/* Stats Cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>Pending Takes</CardDescription>
                        <CardTitle className="text-2xl">
                            {statsLoading ? <Loader2 className="h-5 w-5 animate-spin" /> : stats?.takes?.pending || 0}
                        </CardTitle>
                    </CardHeader>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>Approved Takes</CardDescription>
                        <CardTitle className="text-2xl">
                            {statsLoading ? <Loader2 className="h-5 w-5 animate-spin" /> : stats?.takes?.approved || 0}
                        </CardTitle>
                    </CardHeader>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>Pending Submissions</CardDescription>
                        <CardTitle className="text-2xl">
                            {statsLoading ? <Loader2 className="h-5 w-5 animate-spin" /> : stats?.submissions?.pending || 0}
                        </CardTitle>
                    </CardHeader>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>Total Submissions</CardDescription>
                        <CardTitle className="text-2xl">
                            {statsLoading ? <Loader2 className="h-5 w-5 animate-spin" /> : stats?.submissions?.total || 0}
                        </CardTitle>
                    </CardHeader>
                </Card>
            </div>

            {/* Tabs for Takes and Submissions */}
            <Tabs defaultValue="takes" className="space-y-4">
                <TabsList>
                    <TabsTrigger value="takes">Community Takes</TabsTrigger>
                    <TabsTrigger value="submissions">User Submissions</TabsTrigger>
                </TabsList>

                {/* Takes Tab */}
                <TabsContent value="takes" className="space-y-4">
                    <Card>
                        <CardHeader>
                            <div className="flex items-center justify-between">
                                <div>
                                    <CardTitle>Community Takes</CardTitle>
                                    <CardDescription>
                                        Curated takes from various sources
                                    </CardDescription>
                                </div>
                                <div className="flex items-center gap-2">
                                    <Select value={takesFilter} onValueChange={setTakesFilter}>
                                        <SelectTrigger className="w-32">
                                            <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent>
                                            <SelectItem value="pending">Pending</SelectItem>
                                            <SelectItem value="approved">Approved</SelectItem>
                                            <SelectItem value="rejected">Rejected</SelectItem>
                                        </SelectContent>
                                    </Select>
                                    <Button onClick={() => setCreateDialogOpen(true)}>
                                        <Plus className="h-4 w-4 mr-2" />
                                        Add Take
                                    </Button>
                                </div>
                            </div>
                        </CardHeader>
                        <CardContent>
                            {takesLoading ? (
                                <div className="text-center py-8 text-muted-foreground">
                                    <Loader2 className="h-8 w-8 animate-spin mx-auto mb-2" />
                                    Loading takes...
                                </div>
                            ) : takes.length === 0 ? (
                                <div className="text-center py-8 text-muted-foreground">
                                    <MessageSquare className="h-12 w-12 mx-auto mb-3 opacity-50" />
                                    <p>No {takesFilter} takes found</p>
                                </div>
                            ) : (
                                <div className="space-y-4">
                                    {takes.map((take) => (
                                        <div key={take.id} className="border rounded-lg p-4">
                                            <div className="flex items-start justify-between gap-4">
                                                <div className="flex-1">
                                                    <div className="flex items-center gap-2 mb-2">
                                                        {getSourceBadge(take.source_type)}
                                                        {getStatusBadge(take.status)}
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
                                                        Created: {formatDate(take.created_at)}
                                                    </p>
                                                </div>
                                                <div className="flex items-center gap-2">
                                                    {take.status === 'pending' && (
                                                        <>
                                                            <Button
                                                                size="sm"
                                                                variant="outline"
                                                                className="text-emerald-600 border-emerald-600 hover:bg-emerald-50"
                                                                onClick={() => handleApproveTake(take.id)}
                                                            >
                                                                <Check className="h-4 w-4" />
                                                            </Button>
                                                            <Button
                                                                size="sm"
                                                                variant="outline"
                                                                className="text-rose-600 border-rose-600 hover:bg-rose-50"
                                                                onClick={() => {
                                                                    setRejectTarget(take)
                                                                    setRejectType('take')
                                                                }}
                                                            >
                                                                <X className="h-4 w-4" />
                                                            </Button>
                                                        </>
                                                    )}
                                                    <Button
                                                        size="sm"
                                                        variant="destructive"
                                                        onClick={() => handleDeleteTake(take.id)}
                                                    >
                                                        <Trash2 className="h-4 w-4" />
                                                    </Button>
                                                </div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </TabsContent>

                {/* Submissions Tab */}
                <TabsContent value="submissions" className="space-y-4">
                    <Card>
                        <CardHeader>
                            <div className="flex items-center justify-between">
                                <div>
                                    <CardTitle>User Submissions</CardTitle>
                                    <CardDescription>
                                        Takes submitted by users for review
                                    </CardDescription>
                                </div>
                                <Select value={submissionsFilter} onValueChange={setSubmissionsFilter}>
                                    <SelectTrigger className="w-32">
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
                            {submissionsLoading ? (
                                <div className="text-center py-8 text-muted-foreground">
                                    <Loader2 className="h-8 w-8 animate-spin mx-auto mb-2" />
                                    Loading submissions...
                                </div>
                            ) : submissions.length === 0 ? (
                                <div className="text-center py-8 text-muted-foreground">
                                    <MessageSquare className="h-12 w-12 mx-auto mb-3 opacity-50" />
                                    <p>No {submissionsFilter} submissions found</p>
                                </div>
                            ) : (
                                <div className="space-y-4">
                                    {submissions.map((sub) => (
                                        <div key={sub.id} className="border rounded-lg p-4">
                                            <div className="flex items-start justify-between gap-4">
                                                <div className="flex-1">
                                                    <div className="flex items-center gap-2 mb-2">
                                                        {getStatusBadge(sub.status)}
                                                        <Badge variant="outline">{sub.player_name}</Badge>
                                                    </div>
                                                    <p className="text-sm text-muted-foreground mb-2">
                                                        <User className="h-3 w-3 inline mr-1" />
                                                        {sub.submitter_name || 'Anonymous'}
                                                        {sub.submitter_email && ` (${sub.submitter_email})`}
                                                    </p>
                                                    <p className="text-sm">{sub.content}</p>
                                                    <p className="text-xs text-muted-foreground mt-2">
                                                        Submitted: {formatDate(sub.created_at)}
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
                                                            onClick={() => handleApproveSubmission(sub.id)}
                                                        >
                                                            <Check className="h-4 w-4 mr-1" />
                                                            Approve
                                                        </Button>
                                                        <Button
                                                            size="sm"
                                                            variant="outline"
                                                            className="text-rose-600 border-rose-600 hover:bg-rose-50"
                                                            onClick={() => {
                                                                setRejectTarget(sub)
                                                                setRejectType('submission')
                                                            }}
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
                        </CardContent>
                    </Card>
                </TabsContent>
            </Tabs>

            {/* Create Take Dialog */}
            <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
                <DialogContent className="max-w-lg">
                    <DialogHeader>
                        <DialogTitle>Add Community Take</DialogTitle>
                        <DialogDescription>
                            Create a new community take directly
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4 py-4">
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label>Source Type</Label>
                                <Select
                                    value={newTake.source_type}
                                    onValueChange={(value) => setNewTake({ ...newTake, source_type: value })}
                                >
                                    <SelectTrigger>
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
                                <Label>Author</Label>
                                <Input
                                    value={newTake.source_author}
                                    onChange={(e) => setNewTake({ ...newTake, source_author: e.target.value })}
                                    placeholder="e.g., u/username or @handle"
                                />
                            </div>
                        </div>
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label>Platform (optional)</Label>
                                <Input
                                    value={newTake.source_platform}
                                    onChange={(e) => setNewTake({ ...newTake, source_platform: e.target.value })}
                                    placeholder="e.g., r/reddevils"
                                />
                            </div>
                            <div className="space-y-2">
                                <Label>Source URL (optional)</Label>
                                <Input
                                    value={newTake.source_url}
                                    onChange={(e) => setNewTake({ ...newTake, source_url: e.target.value })}
                                    placeholder="https://..."
                                />
                            </div>
                        </div>
                        <div className="space-y-2">
                            <Label>Player Name (optional)</Label>
                            <Input
                                value={newTake.player_name}
                                onChange={(e) => setNewTake({ ...newTake, player_name: e.target.value })}
                                placeholder="e.g., Kobbie Mainoo"
                            />
                        </div>
                        <div className="space-y-2">
                            <Label>Content</Label>
                            <Textarea
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
                        <Button onClick={handleCreateTake} disabled={createLoading}>
                            {createLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            Create Take
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Reject Dialog */}
            <Dialog open={!!rejectTarget} onOpenChange={() => setRejectTarget(null)}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Reject {rejectType === 'take' ? 'Take' : 'Submission'}?</DialogTitle>
                        <DialogDescription>
                            Optionally provide a reason for rejection.
                        </DialogDescription>
                    </DialogHeader>
                    <div className="py-4">
                        <Label>Rejection Reason (optional)</Label>
                        <Textarea
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
                        <Button variant="destructive" onClick={handleRejectTake} disabled={rejectLoading}>
                            {rejectLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            Reject
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    )
}
