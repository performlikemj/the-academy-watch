import { useState, useEffect, useCallback, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Checkbox } from '@/components/ui/checkbox'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Label } from '@/components/ui/label'
import {
  Loader2,
  Trash2,
  CheckCircle,
  XCircle,
  Clock,
  AlertCircle,
  Search,
  RefreshCw,
  Users,
  CheckSquare,
  Square,
  Shield,
  ArrowLeftRight,
  Pencil,
  Save,
  X,
  Wand2,
  LayoutGrid,
  MoreVertical,
  ChevronsUpDown,
  Sprout
} from 'lucide-react'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from '@/components/ui/collapsible'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'
import { APIService } from '@/lib/api'

export function AdminTeams() {
  const [teams, setTeams] = useState([])
  const [trackingRequests, setTrackingRequests] = useState([])
  const [loading, setLoading] = useState(true)
  const [requestsLoading, setRequestsLoading] = useState(true)
  const [message, setMessage] = useState(null)
  const [search, setSearch] = useState('')
  const [requestFilter, setRequestFilter] = useState('pending')

  // Pagination state
  const [trackedPage, setTrackedPage] = useState(1)
  const [untrackedPage, setUntrackedPage] = useState(1)

  // Selection state
  const [selectedTeamIds, setSelectedTeamIds] = useState(new Set())
  const [bulkMode, setBulkMode] = useState('delete') // 'delete' or 'keep'

  // Delete team data dialog state
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState(null) // Single team or null for bulk
  const [deletePreview, setDeletePreview] = useState(null)
  const [bulkDeletePreviews, setBulkDeletePreviews] = useState([])
  const [deleteLoading, setDeleteLoading] = useState(false)
  const [previewLoading, setPreviewLoading] = useState(false)

  // Placeholder team names state
  const [placeholderTeams, setPlaceholderTeams] = useState([])
  const [placeholderLoading, setPlaceholderLoading] = useState(false)
  const [placeholderSeason, setPlaceholderSeason] = useState(new Date().getFullYear().toString())
  const [editingTeamId, setEditingTeamId] = useState(null)
  const [editingName, setEditingName] = useState('')
  const [savingName, setSavingName] = useState(false)
  const [bulkFixing, setBulkFixing] = useState(false)
  const [bulkFixDryRun, setBulkFixDryRun] = useState(true)
  const [propagating, setPropagating] = useState(false)
  const [propagateDryRun, setPropagateDryRun] = useState(true)

  // Seed all tracked state
  const [seedingAll, setSeedingAll] = useState(false)

  // Sync fixtures state
  const [syncingTeamId, setSyncingTeamId] = useState(null)
  const [syncJobId, setSyncJobId] = useState(null)
  const [syncProgress, setSyncProgress] = useState(null)

  // Purge state
  const [purgeTeamId, setPurgeTeamId] = useState('')
  const [purgePreview, setPurgePreview] = useState(null)
  const [purgeLoading, setPurgeLoading] = useState(false)

  // Team Aliases state
  const [aliases, setAliases] = useState([])
  const [aliasesLoading, setAliasesLoading] = useState(false)
  const [newAliasCanonical, setNewAliasCanonical] = useState('')
  const [newAliasName, setNewAliasName] = useState('')
  const [creatingAlias, setCreatingAlias] = useState(false)

  const loadAliases = useCallback(async () => {
    try {
      setAliasesLoading(true)
      const data = await APIService.adminListTeamAliases()
      setAliases(Array.isArray(data) ? data : [])
    } catch (error) {
      console.error('Failed to load aliases:', error)
      setMessage({ type: 'error', text: 'Failed to load team aliases' })
    } finally {
      setAliasesLoading(false)
    }
  }, [])

  const handleCreateAlias = async (e) => {
    e.preventDefault()
    if (!newAliasCanonical.trim() || !newAliasName.trim()) return

    try {
      setCreatingAlias(true)
      await APIService.adminCreateTeamAlias({
        canonical_name: newAliasCanonical.trim(),
        alias: newAliasName.trim()
      })
      setMessage({ type: 'success', text: 'Alias created successfully' })
      setNewAliasCanonical('')
      setNewAliasName('')
      loadAliases()
    } catch (error) {
      console.error('Failed to create alias:', error)
      setMessage({ type: 'error', text: error.message || 'Failed to create alias' })
    } finally {
      setCreatingAlias(false)
    }
  }

  const handleDeleteAlias = async (id) => {
    if (!confirm('Are you sure you want to delete this alias?')) return

    try {
      await APIService.adminDeleteTeamAlias(id)
      setMessage({ type: 'success', text: 'Alias deleted successfully' })
      loadAliases()
    } catch (error) {
      console.error('Failed to delete alias:', error)
      setMessage({ type: 'error', text: 'Failed to delete alias' })
    }
  }

  const loadTeams = useCallback(async () => {
    try {
      setLoading(true)
      const data = await APIService.getTeams({ european_only: 'true' })
      // Sort by name and keep latest season per team
      const teamsArray = Array.isArray(data) ? data : []
      const byApiId = {}
      for (const team of teamsArray) {
        const key = team.team_id
        if (!byApiId[key] || team.season > byApiId[key].season) {
          byApiId[key] = team
        }
      }
      const sorted = Object.values(byApiId).sort((a, b) => a.name.localeCompare(b.name))
      setTeams(sorted)
    } catch (error) {
      console.error('Failed to load teams:', error)
      setMessage({ type: 'error', text: 'Failed to load teams' })
    } finally {
      setLoading(false)
    }
  }, [])

  const loadTrackingRequests = useCallback(async () => {
    try {
      setRequestsLoading(true)
      const data = await APIService.adminListTrackingRequests({ status: requestFilter === 'all' ? '' : requestFilter })
      setTrackingRequests(Array.isArray(data) ? data : [])
    } catch (error) {
      console.error('Failed to load tracking requests:', error)
      setMessage({ type: 'error', text: 'Failed to load tracking requests' })
    } finally {
      setRequestsLoading(false)
    }
  }, [requestFilter])

  useEffect(() => {
    loadTeams()
  }, [loadTeams])

  useEffect(() => {
    loadTrackingRequests()
  }, [loadTrackingRequests])

  const filteredTeams = useMemo(() => teams.filter(team =>
    team.name.toLowerCase().includes(search.toLowerCase()) ||
    team.league_name?.toLowerCase().includes(search.toLowerCase())
  ), [teams, search])

  const trackedTeams = useMemo(() => filteredTeams.filter(t => t.is_tracked), [filteredTeams])
  const untrackedTeams = useMemo(() => filteredTeams.filter(t => !t.is_tracked), [filteredTeams])

  const trackedPageSize = 25
  const untrackedPageSize = 30

  const trackedTotalPages = Math.max(1, Math.ceil(trackedTeams.length / trackedPageSize))
  const untrackedTotalPages = Math.max(1, Math.ceil(untrackedTeams.length / untrackedPageSize))

  const trackedTeamsPage = useMemo(() => {
    const start = (trackedPage - 1) * trackedPageSize
    return trackedTeams.slice(start, start + trackedPageSize)
  }, [trackedTeams, trackedPage, trackedPageSize])

  const untrackedTeamsPage = useMemo(() => {
    const start = (untrackedPage - 1) * untrackedPageSize
    return untrackedTeams.slice(start, start + untrackedPageSize)
  }, [untrackedTeams, untrackedPage, untrackedPageSize])

  const trackedRangeStart = trackedTeams.length === 0 ? 0 : (trackedPage - 1) * trackedPageSize + 1
  const trackedRangeEnd = Math.min(trackedTeams.length, trackedPage * trackedPageSize)
  const untrackedRangeStart = untrackedTeams.length === 0 ? 0 : (untrackedPage - 1) * untrackedPageSize + 1
  const untrackedRangeEnd = Math.min(untrackedTeams.length, untrackedPage * untrackedPageSize)

  useEffect(() => {
    setTrackedPage(1)
    setUntrackedPage(1)
  }, [search])

  useEffect(() => {
    if (trackedPage > trackedTotalPages) {
      setTrackedPage(trackedTotalPages)
    }
  }, [trackedPage, trackedTotalPages])

  useEffect(() => {
    if (untrackedPage > untrackedTotalPages) {
      setUntrackedPage(untrackedTotalPages)
    }
  }, [untrackedPage, untrackedTotalPages])

  // Teams that will be deleted based on current selection and mode
  const teamsToDelete = useMemo(() => {
    if (bulkMode === 'delete') {
      return trackedTeams.filter(t => selectedTeamIds.has(t.id))
    } else {
      // 'keep' mode - delete everything NOT selected
      return trackedTeams.filter(t => !selectedTeamIds.has(t.id))
    }
  }, [trackedTeams, selectedTeamIds, bulkMode])

  const teamsToKeep = useMemo(() => {
    if (bulkMode === 'keep') {
      return trackedTeams.filter(t => selectedTeamIds.has(t.id))
    } else {
      return trackedTeams.filter(t => !selectedTeamIds.has(t.id))
    }
  }, [trackedTeams, selectedTeamIds, bulkMode])

  // Selection handlers
  const toggleTeamSelection = (teamId) => {
    setSelectedTeamIds(prev => {
      const next = new Set(prev)
      if (next.has(teamId)) {
        next.delete(teamId)
      } else {
        next.add(teamId)
      }
      return next
    })
  }

  const handleSeedUnseeded = async () => {
    setSeedingAll(true)
    setMessage(null)
    try {
      const res = await APIService.adminSeedAllTrackedPlayers()
      if (res.empty_teams === 0) {
        setMessage({ type: 'info', text: 'All tracked teams already have players seeded.' })
      } else {
        setMessage({
          type: 'success',
          text: `Seeding started for ${res.teams_to_seed} team(s). Job ID: ${res.job_id}`,
        })
      }
    } catch (err) {
      setMessage({ type: 'error', text: `Seed failed: ${err.message}` })
    } finally {
      setSeedingAll(false)
    }
  }

  const selectAllTracked = () => {
    setSelectedTeamIds(new Set(trackedTeams.map(t => t.id)))
  }

  const selectNone = () => {
    setSelectedTeamIds(new Set())
  }

  const invertSelection = () => {
    const allIds = new Set(trackedTeams.map(t => t.id))
    const inverted = new Set()
    for (const id of allIds) {
      if (!selectedTeamIds.has(id)) {
        inverted.add(id)
      }
    }
    setSelectedTeamIds(inverted)
  }

  // Single team delete
  const handleDeleteClick = async (team) => {
    setDeleteTarget(team)
    setBulkDeletePreviews([])
    setDeleteDialogOpen(true)
    setDeletePreview(null)
    setPreviewLoading(true)

    try {
      const preview = await APIService.adminDeleteTeamData(team.id, true)
      setDeletePreview(preview)
    } catch (error) {
      console.error('Failed to preview delete:', error)
      setMessage({ type: 'error', text: 'Failed to preview deletion' })
    } finally {
      setPreviewLoading(false)
    }
  }

  // Bulk delete preview
  const handleBulkDeleteClick = async () => {
    if (teamsToDelete.length === 0) {
      setMessage({ type: 'error', text: 'No teams selected for deletion' })
      return
    }

    setDeleteTarget(null)
    setDeletePreview(null)
    setDeleteDialogOpen(true)
    setPreviewLoading(true)
    setBulkDeletePreviews([])

    try {
      // Get preview for each team (limit to first 10 for performance)
      const previewTeams = teamsToDelete.slice(0, 10)
      const previews = await Promise.all(
        previewTeams.map(async (team) => {
          try {
            const preview = await APIService.adminDeleteTeamData(team.id, true)
            return { team, preview }
          } catch (err) {
            return { team, preview: null, error: err.message }
          }
        })
      )
      setBulkDeletePreviews(previews)
    } catch (error) {
      console.error('Failed to preview bulk delete:', error)
      setMessage({ type: 'error', text: 'Failed to preview bulk deletion' })
    } finally {
      setPreviewLoading(false)
    }
  }

  const confirmDelete = async () => {
    setDeleteLoading(true)

    try {
      if (deleteTarget) {
        // Single delete
        await APIService.adminDeleteTeamData(deleteTarget.id, false)
        setMessage({ type: 'success', text: `Successfully deleted all tracking data for ${deleteTarget.name}` })
      } else {
        // Bulk delete
        let successCount = 0
        let errorCount = 0

        for (const team of teamsToDelete) {
          try {
            await APIService.adminDeleteTeamData(team.id, false)
            successCount++
          } catch (err) {
            console.error(`Failed to delete ${team.name}:`, err)
            errorCount++
          }
        }

        if (errorCount === 0) {
          setMessage({ type: 'success', text: `Successfully deleted data for ${successCount} teams` })
        } else {
          setMessage({ type: 'warning', text: `Deleted ${successCount} teams, ${errorCount} failed` })
        }

        setSelectedTeamIds(new Set())
      }

      setDeleteDialogOpen(false)
      setDeleteTarget(null)
      setDeletePreview(null)
      setBulkDeletePreviews([])
      loadTeams()
    } catch (error) {
      console.error('Failed to delete team data:', error)
      setMessage({ type: 'error', text: 'Failed to delete team data' })
    } finally {
      setDeleteLoading(false)
    }
  }

  // Sync fixtures for a single team
  const handleSyncFixtures = async (team) => {
    setSyncingTeamId(team.id)
    setSyncProgress(null)

    try {
      const res = await APIService.adminSyncTeamFixtures(team.id, { background: true })

      if (res.job_id) {
        setSyncJobId(res.job_id)
        setMessage({ type: 'info', text: `Syncing fixtures for ${team.name}... This runs in the background.` })

        // Poll for job status
        const interval = setInterval(async () => {
          try {
            const job = await APIService.request(`/admin/jobs/${res.job_id}`, {}, { admin: true })
            if (job) {
              setSyncProgress(job)
              if (job.status === 'completed' || job.status === 'failed') {
                clearInterval(interval)
                setSyncingTeamId(null)
                setSyncJobId(null)
                if (job.status === 'completed') {
                  const results = job.results || {}
                  setMessage({
                    type: 'success',
                    text: `Synced ${results.total_synced || 0} fixtures for ${results.players_processed || 0} players from ${team.name}`
                  })
                  loadTeams()
                } else {
                  setMessage({ type: 'error', text: `Sync failed: ${job.error || 'Unknown error'}` })
                }
              }
            }
          } catch (err) {
            console.error('Failed to get job status:', err)
          }
        }, 2000)
      } else {
        // Synchronous response
        setMessage({
          type: 'success',
          text: `Synced ${res.total_synced || 0} fixtures for ${res.players_processed || 0} players`
        })
        setSyncingTeamId(null)
        loadTeams()
      }
    } catch (error) {
      console.error('Failed to sync fixtures:', error)
      setMessage({ type: 'error', text: `Failed to sync fixtures: ${error.message || 'Unknown error'}` })
      setSyncingTeamId(null)
      setSyncJobId(null)
    }
  }

  // Purge loans except selected team
  const handlePurgePreview = async () => {
    if (!purgeTeamId) {
      setMessage({ type: 'error', text: 'Please select a team to keep' })
      return
    }
    setPurgeLoading(true)
    try {
      const preview = await APIService.adminPurgeLoansExcept([parseInt(purgeTeamId)], { dryRun: true })
      setPurgePreview(preview)
    } catch (error) {
      console.error('Failed to preview purge:', error)
      setMessage({ type: 'error', text: 'Failed to preview purge' })
    } finally {
      setPurgeLoading(false)
    }
  }

  const handlePurgeConfirm = async () => {
    if (!purgeTeamId || !purgePreview) return

    setPurgeLoading(true)
    try {
      const result = await APIService.adminPurgeLoansExcept([parseInt(purgeTeamId)], { dryRun: false })
      setMessage({ type: 'success', text: result.message })
      setPurgePreview(null)
      loadTeams()
    } catch (error) {
      console.error('Failed to purge:', error)
      setMessage({ type: 'error', text: 'Failed to purge loans' })
    } finally {
      setPurgeLoading(false)
    }
  }

  const handleRequestAction = async (requestId, status, note = '') => {
    try {
      await APIService.adminUpdateTrackingRequest(requestId, { status, note })
      setMessage({ type: 'success', text: `Request ${status}` })
      loadTrackingRequests()
      if (status === 'approved') {
        loadTeams()
      }
    } catch (error) {
      console.error('Failed to update request:', error)
      setMessage({ type: 'error', text: 'Failed to update request' })
    }
  }

  const handleToggleTracking = async (team) => {
    try {
      await APIService.adminUpdateTeamTracking(team.id, !team.is_tracked)
      setMessage({ type: 'success', text: `${team.name} is now ${!team.is_tracked ? 'tracked' : 'untracked'}` })
      loadTeams()
    } catch (error) {
      console.error('Failed to toggle tracking:', error)
      setMessage({ type: 'error', text: 'Failed to update tracking status' })
    }
  }

  // Placeholder team names functions
  const loadPlaceholderTeams = useCallback(async () => {
    try {
      setPlaceholderLoading(true)
      const params = {}
      if (placeholderSeason) params.season = placeholderSeason
      const data = await APIService.adminListPlaceholderTeamNames(params)
      setPlaceholderTeams(Array.isArray(data) ? data : [])
    } catch (error) {
      console.error('Failed to load placeholder teams:', error)
      setMessage({ type: 'error', text: 'Failed to load placeholder team names' })
    } finally {
      setPlaceholderLoading(false)
    }
  }, [placeholderSeason])

  const startEditingName = (team) => {
    setEditingTeamId(team.id)
    setEditingName(team.name)
  }

  const cancelEditingName = () => {
    setEditingTeamId(null)
    setEditingName('')
  }

  const saveTeamName = async (teamId) => {
    if (!editingName.trim()) {
      setMessage({ type: 'error', text: 'Name cannot be empty' })
      return
    }

    try {
      setSavingName(true)
      await APIService.adminUpdateTeamName(teamId, editingName.trim())
      setMessage({ type: 'success', text: 'Team name updated successfully' })
      setEditingTeamId(null)
      setEditingName('')
      loadPlaceholderTeams()
      loadTeams() // Also refresh main teams list
    } catch (error) {
      console.error('Failed to update team name:', error)
      setMessage({ type: 'error', text: `Failed to update team name: ${error.message}` })
    } finally {
      setSavingName(false)
    }
  }

  const bulkFixPlaceholderNames = async () => {
    if (!placeholderSeason) {
      setMessage({ type: 'error', text: 'Please enter a season year' })
      return
    }

    try {
      setBulkFixing(true)
      const result = await APIService.adminBulkFixTeamNames({
        season: parseInt(placeholderSeason),
        dry_run: bulkFixDryRun
      })

      const updatedCount = result.updated_count || 0
      const skippedCount = result.skipped_count || 0

      if (bulkFixDryRun) {
        setMessage({
          type: 'success',
          text: `Dry run: would update ${updatedCount} team(s), skipped ${skippedCount}`
        })
      } else {
        setMessage({
          type: 'success',
          text: `Updated ${updatedCount} team name(s), skipped ${skippedCount}`
        })
        loadPlaceholderTeams()
        loadTeams()
      }
    } catch (error) {
      console.error('Failed to bulk fix team names:', error)
      setMessage({ type: 'error', text: `Failed to bulk fix names: ${error.message}` })
    } finally {
      setBulkFixing(false)
    }
  }

  const propagateTeamNames = async () => {
    try {
      setPropagating(true)
      const result = await APIService.adminPropagateTeamNames({
        dry_run: propagateDryRun,
        fix_loans: true,
        fix_newsletters: true
      })

      const loansUpdated = result.loans_updated || 0
      const newslettersUpdated = result.newsletters_updated || 0
      const detailsCount = result.details?.length || 0

      if (propagateDryRun) {
        setMessage({
          type: 'success',
          text: `Dry run: would update ${detailsCount} record(s) (loans + newsletters)`
        })
      } else {
        setMessage({
          type: 'success',
          text: `Propagated names to ${loansUpdated} loan record(s) and ${newslettersUpdated} newsletter(s)`
        })
      }
    } catch (error) {
      console.error('Failed to propagate team names:', error)
      setMessage({ type: 'error', text: `Failed to propagate names: ${error.message}` })
    } finally {
      setPropagating(false)
    }
  }

  // Calculate totals for bulk preview
  const bulkTotals = useMemo(() => {
    const totals = {
      loaned_players: 0,
      newsletters: 0,
      weekly_reports: 0,
      subscriptions: 0,
      commentaries: 0,
      fixture_player_stats: 0
    }
    for (const { preview } of bulkDeletePreviews) {
      if (preview?.deleted) {
        totals.loaned_players += preview.deleted.loaned_players || 0
        totals.newsletters += preview.deleted.newsletters || 0
        totals.weekly_reports += preview.deleted.weekly_reports || 0
        totals.subscriptions += preview.deleted.subscriptions || 0
        totals.commentaries += preview.deleted.commentaries || 0
        totals.fixture_player_stats += preview.deleted.fixture_player_stats || 0
      }
    }
    return totals
  }, [bulkDeletePreviews])

  return (
    <div className="space-y-4 sm:space-y-6 overflow-hidden">
      <div>
        <h2 className="text-2xl sm:text-3xl font-bold tracking-tight">Team Management</h2>
        <p className="text-sm sm:text-base text-muted-foreground mt-1">
          Manage team tracking status and data
        </p>
      </div>

      {message && (
        <Alert className={message.type === 'error' ? 'border-rose-500' : message.type === 'success' ? 'border-emerald-500' : 'border-primary/20'}>
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{message.text}</AlertDescription>
        </Alert>
      )}

      <Tabs defaultValue="teams">
        <TabsList className="w-full justify-start overflow-x-auto h-auto gap-1 p-1" style={{ scrollbarWidth: 'none' }}>
          <TabsTrigger value="teams" className="text-xs sm:text-sm">
            <Users className="h-4 w-4 mr-1 sm:mr-2" />
            <span className="hidden xs:inline">Teams</span> ({trackedTeams.length})
          </TabsTrigger>
          <TabsTrigger value="requests" className="text-xs sm:text-sm">
            <Clock className="h-4 w-4 mr-1 sm:mr-2" />
            <span className="hidden xs:inline">Tracking</span> Requests
            {trackingRequests.filter(r => r.status === 'pending').length > 0 && (
              <Badge variant="destructive" className="ml-1 sm:ml-2 text-xs">
                {trackingRequests.filter(r => r.status === 'pending').length}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="fix-names" className="text-xs sm:text-sm" onClick={() => { if (placeholderTeams.length === 0) loadPlaceholderTeams() }}>
            <Pencil className="h-4 w-4 mr-1 sm:mr-2" />
            Fix <span className="hidden xs:inline">Team</span> Names
          </TabsTrigger>
          <TabsTrigger value="aliases" className="text-xs sm:text-sm" onClick={loadAliases}>
            <ArrowLeftRight className="h-4 w-4 mr-1 sm:mr-2" />
            <span className="hidden xs:inline">Team</span> Aliases
          </TabsTrigger>
          <TabsTrigger value="purge" className="text-xs sm:text-sm">
            <Trash2 className="h-4 w-4 mr-1 sm:mr-2" />
            Purge <span className="hidden xs:inline">Data</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="teams" className="space-y-6">
          {/* Shared search bar */}
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 sm:gap-4">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search teams by name or league..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-10"
                autoComplete="off"
                aria-label="Search teams"
              />
            </div>
            <Button variant="outline" onClick={loadTeams} className="shrink-0">
              <RefreshCw className="h-4 w-4 mr-2" />
              Refresh
            </Button>
          </div>

          {/* Tracked Teams - full width */}
          <Card>
            <CardHeader>
              <CardTitle>Tracked Teams ({trackedTeams.length})</CardTitle>
              <CardDescription>
                Teams currently being tracked for academy player data
              </CardDescription>
              <CardAction>
                <div className="flex items-center gap-1">
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button variant="ghost" size="icon" className="h-8 w-8" onClick={handleSeedUnseeded} disabled={seedingAll} aria-label="Seed unseeded teams">
                        {seedingAll ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sprout className="h-4 w-4" />}
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>Seed Unseeded Teams</TooltipContent>
                  </Tooltip>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button variant="ghost" size="icon" className="h-8 w-8" onClick={selectAllTracked} aria-label="Select all">
                        <CheckSquare className="h-4 w-4" />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>Select All</TooltipContent>
                  </Tooltip>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button variant="ghost" size="icon" className="h-8 w-8" onClick={selectNone} aria-label="Deselect all">
                        <Square className="h-4 w-4" />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>Deselect All</TooltipContent>
                  </Tooltip>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button variant="ghost" size="icon" className="h-8 w-8" onClick={invertSelection} aria-label="Invert selection">
                        <ArrowLeftRight className="h-4 w-4" />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>Invert Selection</TooltipContent>
                  </Tooltip>
                </div>
              </CardAction>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-6 w-6 animate-spin" />
                </div>
              ) : trackedTeams.length === 0 ? (
                <p className="text-center text-muted-foreground py-8">No tracked teams found</p>
              ) : (
                <div className="space-y-2">
                  {trackedTeamsPage.map(team => {
                    const isSelected = selectedTeamIds.has(team.id)
                    const willBeDeleted = teamsToDelete.some(t => t.id === team.id)

                    return (
                      <div
                        key={team.id}
                        className={`flex items-center gap-3 p-3 border rounded-lg transition-colors ${isSelected
                          ? willBeDeleted
                            ? 'bg-rose-50 border-rose-200'
                            : 'bg-emerald-50 border-emerald-200'
                          : 'hover:bg-muted/50'
                          }`}
                      >
                        <Checkbox
                          checked={isSelected}
                          onCheckedChange={() => toggleTeamSelection(team.id)}
                          aria-label={`Select ${team.name}`}
                        />
                        <Avatar className="h-8 w-8 shrink-0">
                          <AvatarImage src={team.logo} alt="" />
                          <AvatarFallback>{team.name.slice(0, 2).toUpperCase()}</AvatarFallback>
                        </Avatar>
                        <div className="flex-1 min-w-0">
                          <p className="font-medium truncate">{team.name}</p>
                          <p className="text-xs text-muted-foreground truncate">
                            {team.league_name || team.country} · {team.tracked_player_count} players tracked
                          </p>
                        </div>
                        {isSelected && selectedTeamIds.size > 0 && (
                          <Badge
                            variant={willBeDeleted ? "destructive" : "secondary"}
                            className="shrink-0 hidden sm:inline-flex"
                          >
                            {willBeDeleted ? 'Delete' : 'Keep'}
                          </Badge>
                        )}
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" className="shrink-0 h-8 w-8" aria-label={`Actions for ${team.name}`}>
                              <MoreVertical className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuLabel>Actions</DropdownMenuLabel>
                            <DropdownMenuItem onClick={() => handleToggleTracking(team)}>
                              <XCircle className="h-4 w-4" />
                              Stop Tracking
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              onClick={() => handleSyncFixtures(team)}
                              disabled={syncingTeamId === team.id}
                            >
                              {syncingTeamId === team.id ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                              ) : (
                                <RefreshCw className="h-4 w-4" />
                              )}
                              {syncingTeamId === team.id ? 'Syncing...' : 'Sync Fixtures'}
                            </DropdownMenuItem>
                            <DropdownMenuItem asChild>
                              <Link to={`/admin/teams/${team.id}/formation`}>
                                <LayoutGrid className="h-4 w-4" />
                                Formation
                              </Link>
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              variant="destructive"
                              onClick={() => handleDeleteClick(team)}
                            >
                              <Trash2 className="h-4 w-4" />
                              Delete Data
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    )
                  })}
                </div>
              )}
            </CardContent>
            {!loading && trackedTeams.length > 0 && (
              <CardFooter className="flex items-center justify-between border-t pt-4">
                <span className="text-xs text-muted-foreground">
                  {trackedRangeStart}–{trackedRangeEnd} of {trackedTeams.length}
                </span>
                {trackedTotalPages > 1 && (
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={trackedPage === 1}
                      onClick={() => setTrackedPage(page => Math.max(1, page - 1))}
                    >
                      Previous
                    </Button>
                    <span className="text-xs text-muted-foreground tabular-nums">
                      {trackedPage} / {trackedTotalPages}
                    </span>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={trackedPage === trackedTotalPages}
                      onClick={() => setTrackedPage(page => Math.min(trackedTotalPages, page + 1))}
                    >
                      Next
                    </Button>
                  </div>
                )}
              </CardFooter>
            )}
          </Card>

          {/* Untracked Teams - full width, collapsible */}
          <Collapsible defaultOpen={untrackedTeams.length > 0 && untrackedTeams.length <= 20}>
            <Card>
              <CardHeader>
                <CardTitle>Untracked Teams ({untrackedTeams.length})</CardTitle>
                <CardDescription>
                  Teams available but not currently being tracked
                </CardDescription>
                <CardAction>
                  <CollapsibleTrigger asChild>
                    <Button variant="ghost" size="icon" className="h-8 w-8" aria-label="Toggle untracked teams">
                      <ChevronsUpDown className="h-4 w-4" />
                    </Button>
                  </CollapsibleTrigger>
                </CardAction>
              </CardHeader>
              <CollapsibleContent>
                <CardContent>
                  {loading ? (
                    <div className="flex items-center justify-center py-8">
                      <Loader2 className="h-6 w-6 animate-spin" />
                    </div>
                  ) : untrackedTeams.length === 0 ? (
                    <p className="text-center text-muted-foreground py-8">All teams are being tracked</p>
                  ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
                      {untrackedTeamsPage.map(team => (
                        <div key={team.id} className="flex items-center gap-2 p-2 border rounded-lg text-sm">
                          <Avatar className="h-8 w-8 shrink-0">
                            <AvatarImage src={team.logo} alt="" />
                            <AvatarFallback className="text-xs">{team.name.slice(0, 2).toUpperCase()}</AvatarFallback>
                          </Avatar>
                          <span className="flex-1 min-w-0 truncate">{team.name}</span>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="shrink-0"
                            onClick={() => handleToggleTracking(team)}
                          >
                            Track
                          </Button>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
                {!loading && untrackedTeams.length > 0 && (
                  <CardFooter className="flex items-center justify-between border-t pt-4">
                    <span className="text-xs text-muted-foreground">
                      {untrackedRangeStart}–{untrackedRangeEnd} of {untrackedTeams.length}
                    </span>
                    {untrackedTotalPages > 1 && (
                      <div className="flex items-center gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={untrackedPage === 1}
                          onClick={() => setUntrackedPage(page => Math.max(1, page - 1))}
                        >
                          Previous
                        </Button>
                        <span className="text-xs text-muted-foreground tabular-nums">
                          {untrackedPage} / {untrackedTotalPages}
                        </span>
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={untrackedPage === untrackedTotalPages}
                          onClick={() => setUntrackedPage(page => Math.min(untrackedTotalPages, page + 1))}
                        >
                          Next
                        </Button>
                      </div>
                    )}
                  </CardFooter>
                )}
              </CollapsibleContent>
            </Card>
          </Collapsible>

          {/* Floating bulk selection bar */}
          {selectedTeamIds.size > 0 && (
            <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 rounded-lg border bg-background px-4 py-2.5 shadow-lg">
              <span className="text-sm font-medium tabular-nums">
                {selectedTeamIds.size} selected
              </span>
              <div className="h-4 w-px bg-border" />
              <Select value={bulkMode} onValueChange={setBulkMode}>
                <SelectTrigger className="h-8 w-40 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="delete">
                    <span className="flex items-center gap-2">
                      <Trash2 className="h-3 w-3" />
                      Delete selected
                    </span>
                  </SelectItem>
                  <SelectItem value="keep">
                    <span className="flex items-center gap-2">
                      <Shield className="h-3 w-3" />
                      Keep selected only
                    </span>
                  </SelectItem>
                </SelectContent>
              </Select>
              <Button
                variant="destructive"
                size="sm"
                onClick={handleBulkDeleteClick}
              >
                <Trash2 className="h-4 w-4 mr-1" />
                {bulkMode === 'delete'
                  ? `Delete ${teamsToDelete.length}`
                  : `Delete ${teamsToDelete.length}, keep ${teamsToKeep.length}`
                }
              </Button>
              <Button variant="ghost" size="sm" onClick={selectNone} aria-label="Clear selection">
                <X className="h-4 w-4" />
              </Button>
            </div>
          )}
        </TabsContent>

        <TabsContent value="requests" className="space-y-4">
          <Card>
            <CardHeader>
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <CardTitle>Tracking Requests</CardTitle>
                  <CardDescription>
                    User requests to track new teams
                  </CardDescription>
                </div>
                <Select value={requestFilter} onValueChange={setRequestFilter}>
                  <SelectTrigger className="w-full sm:w-40">
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
              {requestsLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-6 w-6 animate-spin" />
                </div>
              ) : trackingRequests.length === 0 ? (
                <p className="text-center text-muted-foreground py-8">No tracking requests found</p>
              ) : (
                <div className="space-y-3">
                  {trackingRequests.map(req => (
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
                          {req.status === 'approved' && <CheckCircle className="h-3 w-3 mr-1" />}
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
                            onClick={() => handleRequestAction(req.id, 'approved')}
                            className="flex-1 sm:flex-none"
                          >
                            <CheckCircle className="h-4 w-4 mr-1" />
                            Approve
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleRequestAction(req.id, 'rejected')}
                            className="flex-1 sm:flex-none"
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
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="fix-names" className="space-y-4">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2">
                    <Pencil className="h-5 w-5" />
                    Fix Placeholder Team Names
                  </CardTitle>
                  <CardDescription>
                    Correct teams showing as "Team 12345" with their real names
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Controls */}
              <div className="flex flex-col sm:flex-row flex-wrap items-start sm:items-end gap-3 sm:gap-4 p-4 bg-muted/50 rounded-lg">
                <div className="space-y-1 w-full sm:w-auto">
                  <Label htmlFor="placeholder-season">Season Year</Label>
                  <Input
                    id="placeholder-season"
                    type="number"
                    value={placeholderSeason}
                    onChange={(e) => setPlaceholderSeason(e.target.value)}
                    className="w-full sm:w-28"
                    placeholder="2024"
                  />
                </div>
                <Button onClick={loadPlaceholderTeams} disabled={placeholderLoading} className="w-full sm:w-auto">
                  {placeholderLoading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                  <Search className="h-4 w-4 mr-2" />
                  Find Placeholder Names
                </Button>
                <div className="flex flex-wrap items-center gap-2 w-full sm:w-auto sm:ml-auto">
                  <div className="flex items-center gap-2">
                    <Checkbox
                      id="bulk-fix-dry-run"
                      checked={bulkFixDryRun}
                      onCheckedChange={setBulkFixDryRun}
                    />
                    <Label htmlFor="bulk-fix-dry-run" className="text-sm font-normal">Dry run</Label>
                  </div>
                  <Button
                    onClick={bulkFixPlaceholderNames}
                    disabled={bulkFixing || !placeholderSeason}
                    variant="secondary"
                    className="flex-1 sm:flex-none"
                  >
                    {bulkFixing && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                    <Wand2 className="h-4 w-4 mr-2" />
                    Auto-Fix
                  </Button>
                </div>
              </div>

              {/* Propagate to Old Data */}
              <div className="p-4 bg-primary/5 border border-primary/20 rounded-lg">
                <div className="flex flex-col sm:flex-row flex-wrap items-start sm:items-center justify-between gap-3 sm:gap-4">
                  <div>
                    <h4 className="font-medium text-foreground">Propagate Names to Old Data</h4>
                    <p className="text-sm text-foreground/80 mt-1">
                      Update old newsletters and loan records.
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 w-full sm:w-auto">
                    <div className="flex items-center gap-2">
                      <Checkbox
                        id="propagate-dry-run"
                        checked={propagateDryRun}
                        onCheckedChange={setPropagateDryRun}
                      />
                      <Label htmlFor="propagate-dry-run" className="text-sm font-normal">Dry run</Label>
                    </div>
                    <Button
                      onClick={propagateTeamNames}
                      disabled={propagating}
                      className="flex-1 sm:flex-none"
                    >
                      {propagating && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                      <RefreshCw className="h-4 w-4 mr-2" />
                      {propagateDryRun ? 'Preview' : 'Propagate'}
                    </Button>
                  </div>
                </div>
              </div>

              {/* Results */}
              {placeholderLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-6 w-6 animate-spin" />
                </div>
              ) : placeholderTeams.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  <CheckCircle className="h-12 w-12 mx-auto mb-3 text-emerald-500" />
                  <p className="font-medium">No placeholder team names found!</p>
                  <p className="text-sm mt-1">All teams have proper names. Click "Find Placeholder Names" to search.</p>
                </div>
              ) : (
                <div className="border rounded-lg overflow-hidden">
                  <div className="flex flex-wrap items-center justify-between gap-2 bg-muted px-4 py-2">
                    <span className="text-sm font-medium">
                      Found {placeholderTeams.length} team(s)
                    </span>
                    <Badge variant="secondary">Season {placeholderSeason}</Badge>
                  </div>
                  <div className="max-h-[500px] overflow-auto">
                    <table className="w-full text-sm min-w-[600px]">
                      <thead className="bg-muted/60 sticky top-0">
                        <tr className="text-left">
                          <th className="px-3 sm:px-4 py-2 w-12 sm:w-16">ID</th>
                          <th className="px-3 sm:px-4 py-2">Current Name</th>
                          <th className="px-3 sm:px-4 py-2">API ID</th>
                          <th className="px-3 sm:px-4 py-2">Season</th>
                          <th className="px-3 sm:px-4 py-2">Country</th>
                          <th className="px-3 sm:px-4 py-2 w-28 sm:w-40">Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {placeholderTeams.map((team) => (
                          <tr key={team.id} className="border-t hover:bg-muted/30">
                            <td className="px-3 sm:px-4 py-2 text-muted-foreground">{team.id}</td>
                            <td className="px-3 sm:px-4 py-2">
                              {editingTeamId === team.id ? (
                                <Input
                                  value={editingName}
                                  onChange={(e) => setEditingName(e.target.value)}
                                  className="h-8"
                                  autoFocus
                                  onKeyDown={(e) => {
                                    if (e.key === 'Enter') saveTeamName(team.id)
                                    if (e.key === 'Escape') cancelEditingName()
                                  }}
                                />
                              ) : (
                                <div className="flex items-center gap-2">
                                  {team.logo && (
                                    <Avatar className="h-6 w-6 shrink-0">
                                      <AvatarImage src={team.logo} alt={team.name} />
                                      <AvatarFallback className="text-xs">?</AvatarFallback>
                                    </Avatar>
                                  )}
                                  <span className="text-amber-600 font-medium truncate max-w-[150px]">{team.name}</span>
                                </div>
                              )}
                            </td>
                            <td className="px-3 sm:px-4 py-2 text-muted-foreground font-mono text-xs">
                              {team.team_id}
                            </td>
                            <td className="px-3 sm:px-4 py-2">{team.season}</td>
                            <td className="px-3 sm:px-4 py-2">{team.country}</td>
                            <td className="px-3 sm:px-4 py-2">
                              {editingTeamId === team.id ? (
                                <div className="flex gap-1">
                                  <Button
                                    size="sm"
                                    onClick={() => saveTeamName(team.id)}
                                    disabled={savingName}
                                    aria-label="Save team name"
                                  >
                                    {savingName ? (
                                      <Loader2 className="h-4 w-4 animate-spin" />
                                    ) : (
                                      <Save className="h-4 w-4" />
                                    )}
                                  </Button>
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    onClick={cancelEditingName}
                                    disabled={savingName}
                                    aria-label="Cancel editing"
                                  >
                                    <X className="h-4 w-4" />
                                  </Button>
                                </div>
                              ) : (
                                <Button
                                  size="sm"
                                  variant="outline"
                                  onClick={() => startEditingName(team)}
                                >
                                  <Pencil className="h-4 w-4 sm:mr-1" />
                                  <span className="hidden sm:inline">Edit</span>
                                </Button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="purge" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-rose-600">
                <Trash2 className="h-5 w-5" />
                Purge All Data Except One Team
              </CardTitle>
              <CardDescription>
                Delete ALL player data except for one specific team. This is useful for resetting to track only one team.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Alert className="border-rose-500">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>
                  <strong>Warning:</strong> This will permanently delete all tracked players and their fixture stats
                  from every team EXCEPT the one you select. This cannot be undone.
                </AlertDescription>
              </Alert>

              <div className="flex flex-col sm:flex-row gap-4">
                <div className="flex-1">
                  <Label className="mb-2 block">Team to Keep</Label>
                  <Select value={purgeTeamId} onValueChange={setPurgeTeamId}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select a team to keep..." />
                    </SelectTrigger>
                    <SelectContent>
                      {teams.filter(t => t.is_tracked).map(team => (
                        <SelectItem key={team.id} value={String(team.id)}>
                          {team.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <Button
                  onClick={handlePurgePreview}
                  disabled={!purgeTeamId || purgeLoading}
                  variant="outline"
                  className="mt-auto"
                >
                  {purgeLoading ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : null}
                  Preview
                </Button>
              </div>

              {purgePreview && (
                <div className="mt-4 p-4 border rounded-lg bg-muted/30">
                  <h4 className="font-medium mb-2">Preview - What will be deleted:</h4>
                  <ul className="space-y-1 text-sm">
                    <li><strong>Loans to delete:</strong> {purgePreview.loans_to_delete}</li>
                    <li><strong>Fixture stats to delete:</strong> {purgePreview.fixture_stats_to_delete}</li>
                    <li><strong>Teams affected:</strong> {purgePreview.teams_affected?.slice(0, 10).join(', ')}{purgePreview.teams_affected?.length > 10 ? `... and ${purgePreview.teams_affected.length - 10} more` : ''}</li>
                  </ul>
                  <div className="mt-4 flex gap-2">
                    <Button
                      variant="destructive"
                      onClick={handlePurgeConfirm}
                      disabled={purgeLoading}
                    >
                      {purgeLoading ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Trash2 className="h-4 w-4 mr-2" />}
                      Confirm Purge
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() => setPurgePreview(null)}
                    >
                      Cancel
                    </Button>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="aliases" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Team Aliases</CardTitle>
              <CardDescription>
                Manage alternative names for teams to ensure correct mapping (e.g. "Man Utd" maps to "Manchester United")
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Create Alias Form */}
              <form onSubmit={handleCreateAlias} className="flex flex-col sm:flex-row gap-4 items-end border-b pb-6">
                <div className="flex-1 space-y-2 w-full">
                  <Label>Canonical Name (Official)</Label>
                  <Input
                    placeholder="e.g. Manchester United"
                    value={newAliasCanonical}
                    onChange={(e) => setNewAliasCanonical(e.target.value)}
                  />
                </div>
                <div className="flex-1 space-y-2 w-full">
                  <Label>Alias (Alternative)</Label>
                  <Input
                    placeholder="e.g. Man Utd"
                    value={newAliasName}
                    onChange={(e) => setNewAliasName(e.target.value)}
                  />
                </div>
                <Button type="submit" disabled={creatingAlias}>
                  {creatingAlias ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4 mr-2" />}
                  Add Alias
                </Button>
              </form>

              {/* Aliases List */}
              {aliasesLoading ? (
                <div className="flex justify-center py-8">
                  <Loader2 className="h-6 w-6 animate-spin" />
                </div>
              ) : aliases.length === 0 ? (
                <p className="text-center text-muted-foreground py-8">No aliases defined yet.</p>
              ) : (
                <div className="border rounded-md">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b bg-muted/50">
                        <th className="px-4 py-3 text-left font-medium">Alias</th>
                        <th className="px-4 py-3 text-left font-medium">Canonical Name</th>
                        <th className="px-4 py-3 text-left font-medium">Mapped Team</th>
                        <th className="px-4 py-3 text-right font-medium">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {aliases.map((alias) => (
                        <tr key={alias.id} className="border-b last:border-0">
                          <td className="px-4 py-3 font-medium">{alias.alias}</td>
                          <td className="px-4 py-3">{alias.canonical_name}</td>
                          <td className="px-4 py-3">
                            {alias.team_name ? (
                              <Badge variant="outline" className="bg-emerald-50 text-emerald-700 border-emerald-200">
                                {alias.team_name}
                              </Badge>
                            ) : (
                              <span className="text-muted-foreground text-xs italic">No DB Link</span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-right">
                            <Button
                              variant="ghost"
                              size="sm"
                              className="text-rose-600 hover:text-rose-700 hover:bg-rose-50"
                              onClick={() => handleDeleteAlias(alias.id)}
                              aria-label={`Delete alias ${alias.alias}`}
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Delete Team Data Dialog */}
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent className="sm:max-w-xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-rose-600">
              <Trash2 className="h-5 w-5" />
              {deleteTarget ? 'Delete Team Data' : `Delete Data for ${teamsToDelete.length} Teams`}
            </DialogTitle>
            <DialogDescription>
              {deleteTarget ? (
                <>This will permanently delete all tracking data for <strong>{deleteTarget.name}</strong>.</>
              ) : (
                <>
                  This will permanently delete all tracking data for <strong>{teamsToDelete.length} teams</strong>.
                  {teamsToKeep.length > 0 && (
                    <> <strong>{teamsToKeep.length} teams</strong> will be kept.</>
                  )}
                </>
              )}
              {' '}This action cannot be undone.
            </DialogDescription>
          </DialogHeader>

          {previewLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin mr-2" />
              <span>Calculating impact...</span>
            </div>
          ) : deleteTarget && deletePreview ? (
            // Single team preview
            <div className="space-y-4 py-4">
              <div className="flex items-center gap-3 p-3 bg-muted/50 rounded-lg">
                {deleteTarget.logo && (
                  <Avatar className="h-12 w-12">
                    <AvatarImage src={deleteTarget.logo} alt={deleteTarget.name} />
                    <AvatarFallback>{deleteTarget.name?.slice(0, 2).toUpperCase()}</AvatarFallback>
                  </Avatar>
                )}
                <div>
                  <p className="font-medium">{deleteTarget.name}</p>
                  <p className="text-sm text-muted-foreground">{deleteTarget.league_name}</p>
                </div>
              </div>

              <div className="border rounded-lg p-4 bg-rose-50">
                <p className="font-medium text-rose-800 mb-3">The following data will be deleted:</p>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div className="flex justify-between">
                    <span>Loan Players:</span>
                    <Badge variant="destructive">{deletePreview.deleted?.loaned_players || 0}</Badge>
                  </div>
                  <div className="flex justify-between">
                    <span>Newsletters:</span>
                    <Badge variant="destructive">{deletePreview.deleted?.newsletters || 0}</Badge>
                  </div>
                  <div className="flex justify-between">
                    <span>Weekly Reports:</span>
                    <Badge variant="destructive">{deletePreview.deleted?.weekly_reports || 0}</Badge>
                  </div>
                  <div className="flex justify-between">
                    <span>Subscriptions:</span>
                    <Badge variant="destructive">{deletePreview.deleted?.subscriptions || 0}</Badge>
                  </div>
                  <div className="flex justify-between">
                    <span>Commentaries:</span>
                    <Badge variant="destructive">{deletePreview.deleted?.commentaries || 0}</Badge>
                  </div>
                  <div className="flex justify-between">
                    <span>Fixture Stats:</span>
                    <Badge variant="destructive">{deletePreview.deleted?.fixture_player_stats || 0}</Badge>
                  </div>
                </div>
              </div>
            </div>
          ) : bulkDeletePreviews.length > 0 ? (
            // Bulk preview
            <div className="space-y-4 py-4">
              {/* Teams to keep (if any) */}
              {teamsToKeep.length > 0 && (
                <div className="border rounded-lg p-3 bg-emerald-50">
                  <p className="font-medium text-emerald-800 mb-2 flex items-center gap-2">
                    <Shield className="h-4 w-4" />
                    Teams that will be KEPT ({teamsToKeep.length}):
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {teamsToKeep.map(team => (
                      <Badge key={team.id} variant="outline" className="bg-card">
                        {team.name}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}

              {/* Teams to delete */}
              <div className="border rounded-lg p-3 bg-rose-50">
                <p className="font-medium text-rose-800 mb-2 flex items-center gap-2">
                  <Trash2 className="h-4 w-4" />
                  Teams to DELETE ({teamsToDelete.length}):
                </p>
                <div className="flex flex-wrap gap-2 max-h-32 overflow-y-auto">
                  {teamsToDelete.map(team => (
                    <Badge key={team.id} variant="destructive">
                      {team.name}
                    </Badge>
                  ))}
                </div>
              </div>

              {/* Totals */}
              <div className="border rounded-lg p-4 bg-rose-50">
                <p className="font-medium text-rose-800 mb-3">
                  Total data to be deleted{teamsToDelete.length > 10 && ' (estimated based on first 10 teams)'}:
                </p>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div className="flex justify-between">
                    <span>Loan Players:</span>
                    <Badge variant="destructive">{bulkTotals.loaned_players}</Badge>
                  </div>
                  <div className="flex justify-between">
                    <span>Newsletters:</span>
                    <Badge variant="destructive">{bulkTotals.newsletters}</Badge>
                  </div>
                  <div className="flex justify-between">
                    <span>Weekly Reports:</span>
                    <Badge variant="destructive">{bulkTotals.weekly_reports}</Badge>
                  </div>
                  <div className="flex justify-between">
                    <span>Subscriptions:</span>
                    <Badge variant="destructive">{bulkTotals.subscriptions}</Badge>
                  </div>
                  <div className="flex justify-between">
                    <span>Commentaries:</span>
                    <Badge variant="destructive">{bulkTotals.commentaries}</Badge>
                  </div>
                  <div className="flex justify-between">
                    <span>Fixture Stats:</span>
                    <Badge variant="destructive">{bulkTotals.fixture_player_stats}</Badge>
                  </div>
                </div>
              </div>
            </div>
          ) : null}

          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={confirmDelete}
              disabled={deleteLoading || previewLoading}
            >
              {deleteLoading ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Deleting...
                </>
              ) : (
                <>
                  <Trash2 className="h-4 w-4 mr-2" />
                  {deleteTarget ? 'Delete All Data' : `Delete ${teamsToDelete.length} Teams`}
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
