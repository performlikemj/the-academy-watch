import React, { useState, useEffect, useMemo, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import TeamMultiSelect from '@/components/ui/TeamMultiSelect'
import {
    Loader2, Users, Search, ShieldCheck, Edit, MoreVertical, UserPlus,
    ChevronDown, ChevronUp, CheckCircle2, XCircle, RefreshCw, Plus, X, PenLine, Sparkles,
} from 'lucide-react'
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { APIService } from '@/lib/api'

// --- Raw admin calls for endpoints that have no APIService wrapper and are
// --- not part of the A2 api.js contract (verified in backend routes/api.py):
// POST /admin/users/<id>/curator-role  (api.py — toggle is_curator)
const updateCuratorRole = (userId, isCurator) =>
    APIService.request(`/admin/users/${userId}/curator-role`, {
        method: 'POST',
        body: JSON.stringify({ is_curator: isCurator }),
    }, { admin: true })

// PUT /admin/users/<id>/author-permission  (api.py — toggle can_author_commentary;
// backend additionally requires the bearer email to be in ADMIN_EMAILS)
const updateAuthorPermission = (userId, canAuthor) =>
    APIService.request(`/admin/users/${userId}/author-permission`, {
        method: 'PUT',
        body: JSON.stringify({ can_author_commentary: canAuthor }),
    }, { admin: true })

const COVERAGE_STATUS_STYLES = {
    pending: 'bg-amber-50 text-amber-800 border-amber-200',
    approved: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    denied: 'bg-red-50 text-red-800 border-red-200',
}

function formatDate(iso) {
    if (!iso) return '—'
    try {
        return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
    } catch {
        return iso
    }
}

export function AdminUsers() {
    const [users, setUsers] = useState([])
    const [journalistStats, setJournalistStats] = useState(null)
    const [loading, setLoading] = useState(true)
    const [searchQuery, setSearchQuery] = useState('')
    const [activeTab, setActiveTab] = useState('users')

    // Role toggle confirm dialogs
    const [confirmRoleChangeUser, setConfirmRoleChangeUser] = useState(null)
    const [togglingRole, setTogglingRole] = useState(false)
    const [confirmEditorChangeUser, setConfirmEditorChangeUser] = useState(null)
    const [togglingEditor, setTogglingEditor] = useState(false)
    // Curator/author toggles share one confirm dialog: { user, kind: 'curator' | 'author' }
    const [confirmFlagChange, setConfirmFlagChange] = useState(null)
    const [togglingFlag, setTogglingFlag] = useState(false)

    // Invite writer dialog
    const [inviteOpen, setInviteOpen] = useState(false)
    const [inviteEmail, setInviteEmail] = useState('')
    const [inviteBio, setInviteBio] = useState('')
    const [inviteImageUrl, setInviteImageUrl] = useState('')
    const [inviting, setInviting] = useState(false)
    const [inviteError, setInviteError] = useState('')

    // Team options for the loan-team assignments editor
    const [teamOptions, setTeamOptions] = useState([])

    // Per-journalist assignments editor state, keyed by user id:
    // { open, loading, error, parent: [], dbIds: [], customNames: [], saving, savedAt }
    const [assignments, setAssignments] = useState({})
    const [customNameDrafts, setCustomNameDrafts] = useState({})

    // Coverage requests
    const [coverage, setCoverage] = useState(null)
    const [coverageLoading, setCoverageLoading] = useState(true)
    const [coverageFilter, setCoverageFilter] = useState('pending')
    const [approvingRequestId, setApprovingRequestId] = useState(null)
    const [denyRequest, setDenyRequest] = useState(null)
    const [denyReason, setDenyReason] = useState('')
    const [denying, setDenying] = useState(false)

    // NOTE: these loaders are promise-chain style (no synchronous setState) so
    // they are safe to invoke from the mount effect (react-hooks/set-state-in-
    // effect). Reloads after actions are silent; loading flags start as true.
    const loadData = useCallback(() => {
        return Promise.all([
            APIService.adminGetUsers(),
            APIService.adminGetJournalistStats().catch(() => null),
        ])
            .then(([usersData, statsData]) => {
                setUsers(usersData || [])
                setJournalistStats(statsData)
            })
            .catch((error) => console.error('Failed to load data:', error))
            .finally(() => setLoading(false))
    }, [])

    const loadCoverage = useCallback(() => {
        return APIService.adminCoverageRequests()
            .then((data) => setCoverage(data))
            .catch((error) => {
                console.error('Failed to load coverage requests:', error)
                setCoverage(null)
            })
            .finally(() => setCoverageLoading(false))
    }, [])

    const refreshCoverage = () => {
        setCoverageLoading(true)
        loadCoverage()
    }

    const loadTeamOptions = useCallback(() => {
        // getTeams() dedupes by club keeping the latest-season row; t.id is the
        // DB PK that journalist_loan_team_assignments.loan_team_id expects.
        return Promise.all([
            APIService.getTeams(),
            APIService.getLoanDestinations().catch(() => null),
        ])
            .then(([teamsData, destinationsData]) => {
                const teams = (Array.isArray(teamsData) ? teamsData : teamsData?.teams || [])
                    .filter((t) => t && t.id != null && t.name)
                    .map((t) => ({ id: t.id, name: t.name, league_name: t.league_name || 'Other' }))
                const seen = new Set(teams.map((t) => t.id))
                // Merge active loan destinations so loan-team options include clubs
                // currently hosting loanees even when not in the supported-team list.
                for (const dest of destinationsData?.destinations || []) {
                    if (dest?.team_id != null && dest.name && !seen.has(dest.team_id)) {
                        seen.add(dest.team_id)
                        teams.push({ id: dest.team_id, name: dest.name, league_name: 'Loan destinations' })
                    }
                }
                setTeamOptions(teams)
            })
            .catch((error) => console.error('Failed to load team options:', error))
    }, [])

    useEffect(() => {
        loadData()
        loadCoverage()
        loadTeamOptions()
    }, [loadData, loadCoverage, loadTeamOptions])

    // ---- Role toggles -------------------------------------------------------

    const confirmToggleJournalist = async () => {
        if (!confirmRoleChangeUser) return
        try {
            setTogglingRole(true)
            await APIService.adminUpdateUserRole(confirmRoleChangeUser.id, !confirmRoleChangeUser.is_journalist)
            setConfirmRoleChangeUser(null)
            loadData()
        } catch (error) {
            console.error('Failed to update role:', error)
            alert(error.message || 'Failed to update user role')
        } finally {
            setTogglingRole(false)
        }
    }

    const confirmToggleEditor = async () => {
        if (!confirmEditorChangeUser) return
        try {
            setTogglingEditor(true)
            await APIService.adminUpdateEditorRole(confirmEditorChangeUser.id, !confirmEditorChangeUser.is_editor)
            setConfirmEditorChangeUser(null)
            loadData()
        } catch (error) {
            console.error('Failed to update editor role:', error)
            alert(error.message || 'Failed to update editor role')
        } finally {
            setTogglingEditor(false)
        }
    }

    const confirmToggleFlag = async () => {
        if (!confirmFlagChange) return
        const { user, kind } = confirmFlagChange
        try {
            setTogglingFlag(true)
            if (kind === 'curator') {
                await updateCuratorRole(user.id, !user.is_curator)
            } else {
                await updateAuthorPermission(user.id, !user.can_author_commentary)
            }
            setConfirmFlagChange(null)
            loadData()
        } catch (error) {
            console.error(`Failed to update ${kind} permission:`, error)
            alert(error.message || `Failed to update ${kind} permission`)
        } finally {
            setTogglingFlag(false)
        }
    }

    // ---- Invite writer ------------------------------------------------------

    const openInvite = () => {
        setInviteEmail('')
        setInviteBio('')
        setInviteImageUrl('')
        setInviteError('')
        setInviteOpen(true)
    }

    const submitInvite = async () => {
        const email = inviteEmail.trim()
        if (!email) {
            setInviteError('Email is required')
            return
        }
        try {
            setInviting(true)
            setInviteError('')
            const payload = { email }
            if (inviteBio.trim()) payload.bio = inviteBio.trim()
            if (inviteImageUrl.trim()) payload.profile_image_url = inviteImageUrl.trim()
            await APIService.adminInviteJournalist(payload)
            setInviteOpen(false)
            loadData()
        } catch (error) {
            console.error('Failed to invite writer:', error)
            setInviteError(error.message || 'Failed to invite writer')
        } finally {
            setInviting(false)
        }
    }

    // ---- Assignments editor -------------------------------------------------

    const setAssignmentState = (userId, patch) => {
        setAssignments((prev) => ({ ...prev, [userId]: { ...(prev[userId] || {}), ...patch } }))
    }

    const fetchAssignments = async (userId) => {
        setAssignmentState(userId, { loading: true, error: '' })
        try {
            const data = await APIService.adminGetJournalistAllAssignments(userId)
            const loanAssignments = data?.loan_team_assignments || []
            setAssignmentState(userId, {
                loading: false,
                parent: data?.parent_club_assignments || [],
                dbIds: loanAssignments.filter((a) => a.loan_team_id != null).map((a) => a.loan_team_id),
                customNames: loanAssignments.filter((a) => a.loan_team_id == null).map((a) => a.loan_team_name),
            })
        } catch (error) {
            console.error('Failed to load assignments:', error)
            setAssignmentState(userId, { loading: false, error: error.message || 'Failed to load assignments' })
        }
    }

    const toggleAssignmentsEditor = (user) => {
        const current = assignments[user.id]
        if (current?.open) {
            setAssignmentState(user.id, { open: false })
            return
        }
        setAssignmentState(user.id, { open: true })
        if (!current || current.parent === undefined) {
            fetchAssignments(user.id)
        }
    }

    const addCustomName = (userId) => {
        const draft = (customNameDrafts[userId] || '').trim()
        if (!draft) return
        const entry = assignments[userId] || {}
        const existing = entry.customNames || []
        if (!existing.some((n) => n.toLowerCase() === draft.toLowerCase())) {
            setAssignmentState(userId, { customNames: [...existing, draft], savedAt: null })
        }
        setCustomNameDrafts((prev) => ({ ...prev, [userId]: '' }))
    }

    const removeCustomName = (userId, name) => {
        const entry = assignments[userId] || {}
        setAssignmentState(userId, {
            customNames: (entry.customNames || []).filter((n) => n !== name),
            savedAt: null,
        })
    }

    const saveLoanAssignments = async (user) => {
        const entry = assignments[user.id]
        if (!entry) return
        const nameById = new Map(teamOptions.map((t) => [t.id, t.name]))
        const loanTeams = [
            ...(entry.dbIds || [])
                .filter((id) => nameById.has(id))
                .map((id) => ({ loan_team_id: id, loan_team_name: nameById.get(id) })),
            ...(entry.customNames || []).map((name) => ({ loan_team_id: null, loan_team_name: name })),
        ]
        try {
            setAssignmentState(user.id, { saving: true, error: '' })
            // POST /admin/journalists/<id>/loan-team-assignments — existing wrapper
            // (contract: "adminSetLoanTeamAssignments — wrapper may exist unused, reuse it")
            await APIService.adminAssignLoanTeams(user.id, loanTeams)
            setAssignmentState(user.id, { saving: false, savedAt: Date.now() })
            fetchAssignments(user.id)
        } catch (error) {
            console.error('Failed to save loan team assignments:', error)
            setAssignmentState(user.id, { saving: false, error: error.message || 'Failed to save assignments' })
        }
    }

    // ---- Coverage requests --------------------------------------------------

    const approveCoverageRequest = async (req) => {
        try {
            setApprovingRequestId(req.id)
            await APIService.adminApproveCoverageRequest(req.id)
            await Promise.all([loadCoverage(), loadData()])
        } catch (error) {
            console.error('Failed to approve coverage request:', error)
            alert(error.message || 'Failed to approve coverage request')
        } finally {
            setApprovingRequestId(null)
        }
    }

    const submitDeny = async () => {
        if (!denyRequest) return
        try {
            setDenying(true)
            const reason = denyReason.trim()
            // Backend accepts optional {reason}; second arg is ignored harmlessly
            // if the APIService wrapper only takes the id.
            await APIService.adminDenyCoverageRequest(denyRequest.id, reason ? { reason } : undefined)
            setDenyRequest(null)
            setDenyReason('')
            loadCoverage()
        } catch (error) {
            console.error('Failed to deny coverage request:', error)
            alert(error.message || 'Failed to deny coverage request')
        } finally {
            setDenying(false)
        }
    }

    // ---- Derived ------------------------------------------------------------

    const filteredUsers = users.filter(user => {
        const query = searchQuery.toLowerCase()
        return (
            (user.display_name || '').toLowerCase().includes(query) ||
            (user.email || '').toLowerCase().includes(query)
        )
    })

    const coverageRequests = useMemo(() => {
        const all = coverage?.requests || []
        if (coverageFilter === 'all') return all
        return all.filter((r) => r.status === coverageFilter)
    }, [coverage, coverageFilter])

    const pendingCoverageCount = coverage?.summary?.pending || 0

    if (loading) {
        return (
            <div className="space-y-6">
                <header className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between lg:items-center">
                    <div>
                        <h2 className="text-3xl font-bold tracking-tight">Users &amp; Writers</h2>
                        <p className="text-muted-foreground">Manage user roles, writer assignments and coverage requests</p>
                    </div>
                </header>
                <Skeleton className="h-10 w-72" />
                <Skeleton className="h-44 w-full" />
                <div className="grid gap-4">
                    <Skeleton className="h-32 w-full" />
                    <Skeleton className="h-32 w-full" />
                    <Skeleton className="h-32 w-full" />
                </div>
            </div>
        )
    }

    return (
        <div className="space-y-6">
            <header className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between lg:items-center">
                <div>
                    <h2 className="text-3xl font-bold tracking-tight">Users &amp; Writers</h2>
                    <p className="text-muted-foreground">Manage user roles, writer assignments and coverage requests</p>
                </div>
                <Button onClick={openInvite} data-testid="invite-writer-button">
                    <UserPlus className="mr-2 h-4 w-4" />
                    Invite Writer
                </Button>
            </header>

            <Tabs value={activeTab} onValueChange={setActiveTab}>
                <TabsList>
                    <TabsTrigger value="users" data-testid="users-tab">Users</TabsTrigger>
                    <TabsTrigger value="coverage" data-testid="coverage-requests-tab">
                        Coverage Requests
                        {pendingCoverageCount > 0 && (
                            <Badge className="ml-2 bg-amber-500 hover:bg-amber-500 text-white" data-testid="coverage-pending-badge">
                                {pendingCoverageCount}
                            </Badge>
                        )}
                    </TabsTrigger>
                </TabsList>

                <TabsContent value="users" className="space-y-6 mt-4">
                    {/* Journalist Analytics Section */}
                    {journalistStats && journalistStats.journalists && journalistStats.journalists.length > 0 && (
                        <Card>
                            <CardHeader>
                                <CardTitle className="flex items-center">
                                    <ShieldCheck className="mr-2 h-5 w-5" />
                                    Journalist Analytics
                                </CardTitle>
                                <CardDescription>
                                    Subscriber statistics for all journalists ({journalistStats.total_subscriptions} total subscriptions)
                                </CardDescription>
                            </CardHeader>
                            <CardContent>
                                <div className="rounded-md border overflow-x-auto">
                                    <table className="w-full min-w-[640px] text-sm">
                                        <thead>
                                            <tr className="border-b bg-muted/50">
                                                <th className="p-3 text-left font-medium">Journalist</th>
                                                <th className="p-3 text-left font-medium">Email</th>
                                                <th className="p-3 text-center font-medium">Teams</th>
                                                <th className="p-3 text-right font-medium">Subscribers</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {journalistStats.journalists.map((journalist, idx) => (
                                                <tr key={journalist.journalist_id} className={idx % 2 === 0 ? 'bg-background' : 'bg-muted/20'}>
                                                    <td className="p-3">
                                                        <div className="flex items-center gap-2">
                                                            {journalist.profile_image_url ? (
                                                                <img
                                                                    src={journalist.profile_image_url}
                                                                    alt={journalist.journalist_name}
                                                                    className="h-8 w-8 rounded-full object-cover"
                                                                />
                                                            ) : (
                                                                <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center text-xs font-semibold text-primary">
                                                                    {journalist.journalist_name?.substring(0, 2).toUpperCase()}
                                                                </div>
                                                            )}
                                                            <span className="font-medium">{journalist.journalist_name}</span>
                                                        </div>
                                                    </td>
                                                    <td className="p-3 text-sm text-muted-foreground">{journalist.journalist_email}</td>
                                                    <td className="p-3 text-center">
                                                        <Badge variant="outline" className="text-xs">
                                                            {journalist.teams_count} {journalist.teams_count === 1 ? 'team' : 'teams'}
                                                        </Badge>
                                                    </td>
                                                    <td className="p-3 text-right">
                                                        <div className="flex items-center justify-end gap-2">
                                                            <Users className="h-4 w-4 text-muted-foreground" />
                                                            <span className="text-lg font-semibold text-primary">
                                                                {journalist.total_subscribers}
                                                            </span>
                                                        </div>
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            </CardContent>
                        </Card>
                    )}

                    <div className="flex items-center space-x-2">
                        <Search className="h-4 w-4 text-muted-foreground" />
                        <Input
                            placeholder="Search users..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="max-w-sm"
                        />
                    </div>

                    <div className="grid gap-4">
                        {filteredUsers.length === 0 ? (
                            <Card>
                                <CardContent className="pt-6 text-center text-muted-foreground">
                                    No users found matching your search.
                                </CardContent>
                            </Card>
                        ) : (
                            filteredUsers.map((user) => {
                                const entry = assignments[user.id] || {}
                                return (
                                    <Card key={user.id}>
                                        <CardHeader className="pb-2">
                                            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                                                <div className="flex flex-wrap items-center gap-2">
                                                    <CardTitle className="text-lg">{user.display_name || 'No Name'}</CardTitle>
                                                    {user.is_journalist && (
                                                        <Badge variant="default" className="bg-primary hover:bg-primary/90">
                                                            <ShieldCheck className="h-3 w-3 mr-1" /> Journalist
                                                        </Badge>
                                                    )}
                                                    {user.is_editor && (
                                                        <Badge variant="default" className="bg-purple-600 hover:bg-purple-700">
                                                            <Edit className="h-3 w-3 mr-1" /> Editor
                                                        </Badge>
                                                    )}
                                                    {user.is_curator && (
                                                        <Badge variant="default" className="bg-teal-600 hover:bg-teal-700">
                                                            <Sparkles className="h-3 w-3 mr-1" /> Curator
                                                        </Badge>
                                                    )}
                                                    {user.can_author_commentary && !user.is_journalist && (
                                                        <Badge variant="outline">
                                                            <PenLine className="h-3 w-3 mr-1" /> Author
                                                        </Badge>
                                                    )}
                                                </div>
                                                <div className="flex items-center gap-2 flex-wrap sm:justify-end">
                                                    <span className="text-sm text-muted-foreground break-all sm:mr-2">{user.email}</span>
                                                    <DropdownMenu>
                                                        <DropdownMenuTrigger asChild>
                                                            <Button variant="ghost" size="sm" className="h-8 w-8 p-0" data-testid={`user-actions-${user.id}`}>
                                                                <span className="sr-only">Open menu</span>
                                                                <MoreVertical className="h-4 w-4" />
                                                            </Button>
                                                        </DropdownMenuTrigger>
                                                        <DropdownMenuContent align="start">
                                                            <DropdownMenuLabel>Actions</DropdownMenuLabel>
                                                            <DropdownMenuItem onClick={() => setConfirmRoleChangeUser(user)}>
                                                                {user.is_journalist ? 'Revoke Journalist' : 'Make Journalist'}
                                                            </DropdownMenuItem>
                                                            <DropdownMenuItem onClick={() => setConfirmEditorChangeUser(user)}>
                                                                {user.is_editor ? 'Revoke Editor' : 'Make Editor'}
                                                            </DropdownMenuItem>
                                                            <DropdownMenuItem
                                                                onClick={() => setConfirmFlagChange({ user, kind: 'curator' })}
                                                                data-testid={`curator-toggle-${user.id}`}
                                                            >
                                                                {user.is_curator ? 'Revoke Curator' : 'Make Curator'}
                                                            </DropdownMenuItem>
                                                            <DropdownMenuItem
                                                                onClick={() => setConfirmFlagChange({ user, kind: 'author' })}
                                                                data-testid={`author-toggle-${user.id}`}
                                                            >
                                                                {user.can_author_commentary ? 'Revoke Author Permission' : 'Grant Author Permission'}
                                                            </DropdownMenuItem>
                                                        </DropdownMenuContent>
                                                    </DropdownMenu>
                                                </div>
                                            </div>
                                        </CardHeader>
                                        <CardContent>
                                            <div className="grid md:grid-cols-2 gap-4">
                                                <div>
                                                    <h4 className="text-sm font-medium mb-2 text-muted-foreground">Following ({user.following?.length || 0})</h4>
                                                    <div className="flex flex-wrap gap-2">
                                                        {user.following && user.following.length > 0 ? (
                                                            user.following.map((team) => (
                                                                <Badge key={team.team_id} variant="outline">
                                                                    {team.name}
                                                                </Badge>
                                                            ))
                                                        ) : (
                                                            <span className="text-sm text-muted-foreground italic">Not following any teams</span>
                                                        )}
                                                    </div>
                                                </div>
                                                {user.is_journalist && (
                                                    <div>
                                                        <h4 className="text-sm font-medium mb-2 text-muted-foreground">Reporting On ({user.reporting?.length || 0})</h4>
                                                        <div className="flex flex-wrap gap-2">
                                                            {user.reporting && user.reporting.length > 0 ? (
                                                                user.reporting.map((team) => (
                                                                    <Badge key={team.team_id} variant="secondary">
                                                                        {team.name}
                                                                    </Badge>
                                                                ))
                                                            ) : (
                                                                <span className="text-sm text-muted-foreground italic">No teams assigned</span>
                                                            )}
                                                        </div>
                                                    </div>
                                                )}
                                            </div>

                                            {user.is_journalist && (
                                                <div className="mt-4 border-t pt-3">
                                                    <Button
                                                        variant="outline"
                                                        size="sm"
                                                        onClick={() => toggleAssignmentsEditor(user)}
                                                        data-testid={`assignments-toggle-${user.id}`}
                                                    >
                                                        {entry.open ? <ChevronUp className="mr-1 h-4 w-4" /> : <ChevronDown className="mr-1 h-4 w-4" />}
                                                        {entry.open ? 'Hide assignments' : 'Edit assignments'}
                                                    </Button>

                                                    {entry.open && (
                                                        <div className="mt-3 space-y-4" data-testid={`assignments-editor-${user.id}`}>
                                                            {entry.loading ? (
                                                                <div className="space-y-2">
                                                                    <Skeleton className="h-6 w-1/2" />
                                                                    <Skeleton className="h-9 w-full" />
                                                                </div>
                                                            ) : (
                                                                <>
                                                                    {entry.error && (
                                                                        <p className="text-sm text-red-600">{entry.error}</p>
                                                                    )}
                                                                    <div>
                                                                        <h5 className="text-sm font-medium mb-1">Parent club assignments</h5>
                                                                        <div className="flex flex-wrap gap-2">
                                                                            {(entry.parent || []).length > 0 ? (
                                                                                (entry.parent || []).map((a) => (
                                                                                    <Badge key={a.id} variant="secondary">{a.team_name || `Team #${a.team_id}`}</Badge>
                                                                                ))
                                                                            ) : (
                                                                                <span className="text-sm text-muted-foreground italic">None</span>
                                                                            )}
                                                                        </div>
                                                                        <p className="mt-1 text-xs text-muted-foreground">
                                                                            Parent-club assignments are granted by approving coverage requests.
                                                                        </p>
                                                                    </div>
                                                                    <div className="space-y-2">
                                                                        <h5 className="text-sm font-medium">Loan team assignments</h5>
                                                                        <TeamMultiSelect
                                                                            teams={teamOptions}
                                                                            value={entry.dbIds || []}
                                                                            onChange={(ids) => setAssignmentState(user.id, { dbIds: ids, savedAt: null })}
                                                                            placeholder="Select loan destination clubs…"
                                                                        />
                                                                        <div>
                                                                            <div className="flex flex-wrap gap-2 mb-2">
                                                                                {(entry.customNames || []).map((name) => (
                                                                                    <Badge key={name} variant="outline" className="flex items-center gap-1">
                                                                                        {name}
                                                                                        <X
                                                                                            className="h-3 w-3 cursor-pointer"
                                                                                            onClick={() => removeCustomName(user.id, name)}
                                                                                        />
                                                                                    </Badge>
                                                                                ))}
                                                                            </div>
                                                                            <div className="flex items-center gap-2">
                                                                                <Input
                                                                                    placeholder="Add custom team name (not in database)…"
                                                                                    className="max-w-xs"
                                                                                    value={customNameDrafts[user.id] || ''}
                                                                                    onChange={(e) => setCustomNameDrafts((prev) => ({ ...prev, [user.id]: e.target.value }))}
                                                                                    onKeyDown={(e) => {
                                                                                        if (e.key === 'Enter') {
                                                                                            e.preventDefault()
                                                                                            addCustomName(user.id)
                                                                                        }
                                                                                    }}
                                                                                    data-testid={`custom-loan-team-input-${user.id}`}
                                                                                />
                                                                                <Button
                                                                                    variant="outline"
                                                                                    size="sm"
                                                                                    onClick={() => addCustomName(user.id)}
                                                                                    data-testid={`custom-loan-team-add-${user.id}`}
                                                                                >
                                                                                    <Plus className="h-4 w-4" />
                                                                                </Button>
                                                                            </div>
                                                                        </div>
                                                                        <div className="flex items-center gap-3">
                                                                            <Button
                                                                                size="sm"
                                                                                onClick={() => saveLoanAssignments(user)}
                                                                                disabled={entry.saving}
                                                                                data-testid={`save-assignments-${user.id}`}
                                                                            >
                                                                                {entry.saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                                                                Save loan team assignments
                                                                            </Button>
                                                                            {entry.savedAt && (
                                                                                <span className="text-sm text-emerald-700 flex items-center gap-1">
                                                                                    <CheckCircle2 className="h-4 w-4" /> Saved
                                                                                </span>
                                                                            )}
                                                                        </div>
                                                                        <p className="text-xs text-muted-foreground">
                                                                            Saving replaces the journalist's full loan-team list with the selection above.
                                                                        </p>
                                                                    </div>
                                                                </>
                                                            )}
                                                        </div>
                                                    )}
                                                </div>
                                            )}
                                        </CardContent>
                                    </Card>
                                )
                            })
                        )}
                    </div>
                </TabsContent>

                <TabsContent value="coverage" className="space-y-6 mt-4">
                    <Card>
                        <CardHeader>
                            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                                <div>
                                    <CardTitle>Coverage Requests</CardTitle>
                                    <CardDescription>
                                        Writer requests to cover a parent club or loan destination
                                    </CardDescription>
                                </div>
                                <Button variant="outline" size="sm" onClick={refreshCoverage} disabled={coverageLoading} data-testid="coverage-refresh">
                                    <RefreshCw className={`mr-2 h-4 w-4 ${coverageLoading ? 'animate-spin' : ''}`} />
                                    Refresh
                                </Button>
                            </div>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div className="flex flex-wrap gap-2">
                                {['pending', 'approved', 'denied', 'all'].map((status) => (
                                    <Button
                                        key={status}
                                        variant={coverageFilter === status ? 'default' : 'outline'}
                                        size="sm"
                                        onClick={() => setCoverageFilter(status)}
                                        data-testid={`coverage-filter-${status}`}
                                    >
                                        {status.charAt(0).toUpperCase() + status.slice(1)}
                                        {status !== 'all' && coverage?.summary && (
                                            <span className="ml-1 text-xs opacity-70">({coverage.summary[status] ?? 0})</span>
                                        )}
                                    </Button>
                                ))}
                            </div>

                            {coverageLoading && !coverage ? (
                                <div className="space-y-2">
                                    <Skeleton className="h-20 w-full" />
                                    <Skeleton className="h-20 w-full" />
                                </div>
                            ) : coverageRequests.length === 0 ? (
                                <p className="py-8 text-center text-muted-foreground">
                                    {coverage ? `No ${coverageFilter === 'all' ? '' : coverageFilter + ' '}coverage requests.` : 'Could not load coverage requests.'}
                                </p>
                            ) : (
                                <div className="space-y-3">
                                    {coverageRequests.map((req) => (
                                        <div
                                            key={req.id}
                                            className="rounded-md border p-3 flex flex-col gap-3 md:flex-row md:items-start md:justify-between"
                                            data-testid={`coverage-request-${req.id}`}
                                        >
                                            <div className="space-y-1 min-w-0">
                                                <div className="flex flex-wrap items-center gap-2">
                                                    <span className="font-medium">{req.writer_name || req.writer_email || `User #${req.user_id}`}</span>
                                                    <Badge variant="outline" className={COVERAGE_STATUS_STYLES[req.status] || ''}>
                                                        {req.status}
                                                    </Badge>
                                                    <Badge variant="secondary">
                                                        {req.coverage_type === 'parent_club' ? 'Parent club' : 'Loan team'}
                                                    </Badge>
                                                    {req.is_custom_team && (
                                                        <Badge variant="outline">custom team</Badge>
                                                    )}
                                                </div>
                                                <p className="text-sm">
                                                    Wants to cover <span className="font-medium">{req.team_name}</span>
                                                    <span className="text-muted-foreground"> · requested {formatDate(req.requested_at)}</span>
                                                </p>
                                                {req.request_message && (
                                                    <p className="text-sm text-muted-foreground italic break-words">"{req.request_message}"</p>
                                                )}
                                                {req.status === 'denied' && req.denial_reason && (
                                                    <p className="text-sm text-red-700">Denied: {req.denial_reason}</p>
                                                )}
                                            </div>
                                            {req.status === 'pending' && (
                                                <div className="flex items-center gap-2 shrink-0">
                                                    <Button
                                                        size="sm"
                                                        className="bg-emerald-600 hover:bg-emerald-700"
                                                        onClick={() => approveCoverageRequest(req)}
                                                        disabled={approvingRequestId === req.id}
                                                        data-testid={`coverage-approve-${req.id}`}
                                                    >
                                                        {approvingRequestId === req.id
                                                            ? <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                                                            : <CheckCircle2 className="mr-1 h-4 w-4" />}
                                                        Approve
                                                    </Button>
                                                    <Button
                                                        size="sm"
                                                        variant="outline"
                                                        className="text-red-600 border-red-200 hover:bg-red-50"
                                                        onClick={() => { setDenyRequest(req); setDenyReason('') }}
                                                        data-testid={`coverage-deny-${req.id}`}
                                                    >
                                                        <XCircle className="mr-1 h-4 w-4" />
                                                        Deny
                                                    </Button>
                                                </div>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </TabsContent>
            </Tabs>

            {/* Invite Writer Dialog */}
            <Dialog open={inviteOpen} onOpenChange={(open) => { if (!inviting) setInviteOpen(open) }}>
                <DialogContent data-testid="invite-writer-dialog">
                    <DialogHeader>
                        <DialogTitle>Invite Writer</DialogTitle>
                        <DialogDescription>
                            Creates (or updates) a user account with journalist access. If the email already exists, the account is upgraded to journalist.
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-3">
                        <div className="space-y-1">
                            <Label htmlFor="invite-email">Email (required)</Label>
                            <Input
                                id="invite-email"
                                type="email"
                                placeholder="writer@example.com"
                                value={inviteEmail}
                                onChange={(e) => setInviteEmail(e.target.value)}
                                data-testid="invite-writer-email"
                            />
                        </div>
                        <div className="space-y-1">
                            <Label htmlFor="invite-bio">Bio (optional)</Label>
                            <Textarea
                                id="invite-bio"
                                placeholder="Short writer bio…"
                                value={inviteBio}
                                onChange={(e) => setInviteBio(e.target.value)}
                                rows={3}
                            />
                        </div>
                        <div className="space-y-1">
                            <Label htmlFor="invite-image">Profile image URL (optional)</Label>
                            <Input
                                id="invite-image"
                                placeholder="https://…"
                                value={inviteImageUrl}
                                onChange={(e) => setInviteImageUrl(e.target.value)}
                            />
                        </div>
                        {inviteError && <p className="text-sm text-red-600">{inviteError}</p>}
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setInviteOpen(false)} disabled={inviting}>
                            Cancel
                        </Button>
                        <Button onClick={submitInvite} disabled={inviting} data-testid="invite-writer-submit">
                            {inviting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            Send Invite
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Deny Coverage Request Dialog */}
            <Dialog open={!!denyRequest} onOpenChange={(open) => { if (!open && !denying) { setDenyRequest(null); setDenyReason('') } }}>
                <DialogContent data-testid="coverage-deny-dialog">
                    <DialogHeader>
                        <DialogTitle>Deny Coverage Request</DialogTitle>
                        <DialogDescription>
                            Deny {denyRequest?.writer_name || denyRequest?.writer_email || 'this writer'}'s request to cover {denyRequest?.team_name}?
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-1">
                        <Label htmlFor="deny-reason">Reason (optional)</Label>
                        <Textarea
                            id="deny-reason"
                            placeholder="Why is this request being denied?"
                            value={denyReason}
                            onChange={(e) => setDenyReason(e.target.value)}
                            rows={3}
                            data-testid="coverage-deny-reason"
                        />
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => { setDenyRequest(null); setDenyReason('') }} disabled={denying}>
                            Cancel
                        </Button>
                        <Button variant="destructive" onClick={submitDeny} disabled={denying} data-testid="coverage-deny-confirm">
                            {denying && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            Deny Request
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Confirm Role Change Dialog */}
            <Dialog open={!!confirmRoleChangeUser} onOpenChange={() => setConfirmRoleChangeUser(null)}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>
                            {confirmRoleChangeUser?.is_journalist ? 'Revoke Journalist Status' : 'Grant Journalist Status'}
                        </DialogTitle>
                        <DialogDescription>
                            Are you sure you want to {confirmRoleChangeUser?.is_journalist ? 'revoke journalist status from' : 'make'} {confirmRoleChangeUser?.display_name} {confirmRoleChangeUser?.is_journalist ? '' : 'a journalist'}?
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setConfirmRoleChangeUser(null)} disabled={togglingRole}>
                            Cancel
                        </Button>
                        <Button onClick={confirmToggleJournalist} disabled={togglingRole}>
                            {togglingRole && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            Confirm
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Confirm Editor Role Change Dialog */}
            <Dialog open={!!confirmEditorChangeUser} onOpenChange={() => setConfirmEditorChangeUser(null)}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>
                            {confirmEditorChangeUser?.is_editor ? 'Revoke Editor Status' : 'Grant Editor Status'}
                        </DialogTitle>
                        <DialogDescription>
                            {confirmEditorChangeUser?.is_editor
                                ? `Are you sure you want to revoke editor status from ${confirmEditorChangeUser?.display_name}? They will no longer be able to manage external writers.`
                                : `Are you sure you want to make ${confirmEditorChangeUser?.display_name} an editor? They will be able to create and manage external writers.`
                            }
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setConfirmEditorChangeUser(null)} disabled={togglingEditor}>
                            Cancel
                        </Button>
                        <Button onClick={confirmToggleEditor} disabled={togglingEditor}>
                            {togglingEditor && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            Confirm
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Confirm Curator / Author Permission Change Dialog */}
            <Dialog open={!!confirmFlagChange} onOpenChange={() => setConfirmFlagChange(null)}>
                <DialogContent data-testid="flag-confirm-dialog">
                    <DialogHeader>
                        <DialogTitle>
                            {confirmFlagChange?.kind === 'curator'
                                ? (confirmFlagChange?.user?.is_curator ? 'Revoke Curator Status' : 'Grant Curator Status')
                                : (confirmFlagChange?.user?.can_author_commentary ? 'Revoke Author Permission' : 'Grant Author Permission')}
                        </DialogTitle>
                        <DialogDescription>
                            {confirmFlagChange?.kind === 'curator'
                                ? (confirmFlagChange?.user?.is_curator
                                    ? `Revoke curator status from ${confirmFlagChange?.user?.display_name}? They will no longer be able to add tweets/attributions to newsletters.`
                                    : `Make ${confirmFlagChange?.user?.display_name} a curator? They will be able to add tweets/attributions to newsletters for approved teams.`)
                                : (confirmFlagChange?.user?.can_author_commentary
                                    ? `Revoke commentary authorship from ${confirmFlagChange?.user?.display_name}? They will no longer be able to author newsletter commentary.`
                                    : `Grant commentary authorship to ${confirmFlagChange?.user?.display_name}? They will be able to author newsletter commentary.`)}
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setConfirmFlagChange(null)} disabled={togglingFlag}>
                            Cancel
                        </Button>
                        <Button onClick={confirmToggleFlag} disabled={togglingFlag} data-testid="flag-confirm-button">
                            {togglingFlag && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            Confirm
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    )
}
