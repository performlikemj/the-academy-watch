import { useState, useEffect, useMemo, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { APIService } from '@/lib/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
    DialogFooter,
} from '@/components/ui/dialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Mail, Calendar, Send, Trash2, AlertCircle, CheckCircle2, FileJson, Loader2, Monitor, Copy, Check, FileText, Download, Clock, Inbox, Sprout } from 'lucide-react'
import { convertNewsletterToMarkdown, convertNewsletterToCompactMarkdown } from '@/lib/newsletter-markdown'
import TeamMultiSelect from '@/components/ui/TeamMultiSelect.jsx'
import { NewsletterPreviewDialog } from '@/components/admin/NewsletterPreviewDialog'
import { ConfirmGate } from '@/components/admin/ConfirmGate'
import { NEWSLETTER_ACTION_GRID_CLASS } from './admin-newsletters-layout.js'
import { buildGenerateTeamRequest, buildGenerateAllRequest } from './admin-newsletters-api.js'

const ITEMS_PER_PAGE = 20

export function AdminNewsletters() {
    // State
    const [newsletters, setNewsletters] = useState([])
    const [newslettersLoading, setNewslettersLoading] = useState(false)
    const [selectedTeams, setSelectedTeams] = useState([])
    const [generateDate, setGenerateDate] = useState('')
    const [message, setMessage] = useState(null)
    const [teams, setTeams] = useState([])

    // Deadline card (Monday 23:59 GMT — publishes + charges writers)
    const [deadlineInfo, setDeadlineInfo] = useState(null)
    const [deadlineLoading, setDeadlineLoading] = useState(true)
    const [writerStatuses, setWriterStatuses] = useState([])
    const [writerStatusError, setWriterStatusError] = useState(null)
    const [deadlineWeekOverride, setDeadlineWeekOverride] = useState('')
    const [processingDeadline, setProcessingDeadline] = useState(false)
    const [deadlineResult, setDeadlineResult] = useState(null)
    const [deadlineConfirmOpen, setDeadlineConfirmOpen] = useState(false)

    // Digest queue card
    const [digestWeekKey, setDigestWeekKey] = useState('')
    const [digestQueue, setDigestQueue] = useState(null)
    const [digestLoading, setDigestLoading] = useState(true)
    const [digestSending, setDigestSending] = useState(false)
    const [digestSendResult, setDigestSendResult] = useState(null)
    const [digestConfirmOpen, setDigestConfirmOpen] = useState(false)

    // Pagination
    const [currentPage, setCurrentPage] = useState(1)

    // Filters
    const [filters, setFilters] = useState({
        issue_start: '',
        issue_end: '',
        created_start: '',
        created_end: '',
        week_start: '',
        week_end: '',
        published_only: false
    })
    const [appliedFilters, setAppliedFilters] = useState({ ...filters })

    // Multi-select
    const [selectedIds, setSelectedIds] = useState([])
    const [selectAllFiltered, setSelectAllFiltered] = useState(false)

    // Bulk operations busy states
    const [bulkPublishBusy, setBulkPublishBusy] = useState(false)
    const [bulkDeleteBusy, setBulkDeleteBusy] = useState(false)
    
    // Reddit integration removed

    // JSON/Markdown viewer modal
    const [jsonViewerOpen, setJsonViewerOpen] = useState(false)
    const [viewingNewsletter, setViewingNewsletter] = useState(null)
    const [newsletterJson, setNewsletterJson] = useState(null)
    const [viewerTab, setViewerTab] = useState('json')
    const [markdownFormat, setMarkdownFormat] = useState('full') // 'full' | 'compact'
    const [copied, setCopied] = useState(false)

    // Preview dialog
    const [previewOpen, setPreviewOpen] = useState(false)
    const [previewNewsletter, setPreviewNewsletter] = useState(null)
    const [pdfDownloadingId, setPdfDownloadingId] = useState(null)

    // Delete confirmation
    const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false)
    const [deleteTarget, setDeleteTarget] = useState(null)

    // Generate all teams confirmation
    const [generateAllConfirmOpen, setGenerateAllConfirmOpen] = useState(false)
    const [generatingAll, setGeneratingAll] = useState(false)
    // Local generation state for selected teams
    const [generating, setGenerating] = useState(false)
    const [forceRefresh, setForceRefresh] = useState(false)

    // Pending games check state
    const [generationPreference, setGenerationPreference] = useState('always_ask')
    const [pendingGamesDialogOpen, setPendingGamesDialogOpen] = useState(false)
    const [pendingGamesData, setPendingGamesData] = useState([]) // Array of { teamName, games: [] }

    // Newsletter readiness state
    const [readinessData, setReadinessData] = useState(null)
    const [readinessLoading, setReadinessLoading] = useState(false)
    const [readinessDialogOpen, setReadinessDialogOpen] = useState(false)

    // Load config for preference
    useEffect(() => {
        const loadConfig = async () => {
            try {
                const config = await APIService.adminGetConfig()
                if (config?.newsletter_generation_preference) {
                    setGenerationPreference(config.newsletter_generation_preference)
                }
            } catch (err) {
                console.warn('Failed to load generation preference', err)
            }
        }
        loadConfig()
    }, [])


    // Load teams
    useEffect(() => {
        const loadTeams = async () => {
            try {
                const teamsData = await APIService.getTeams()
                setTeams(teamsData || [])
            } catch (error) {
                console.error('Failed to load teams', error)
            }
        }
        loadTeams()
    }, [])

    // Load newsletters
    const loadNewsletters = useCallback(async (filtersToApply) => {
        setNewslettersLoading(true)
        try {
            const filterParams = filtersToApply || appliedFilters
            const params = {}
            if (filterParams.issue_start) params.issue_start = filterParams.issue_start
            if (filterParams.issue_end) params.issue_end = filterParams.issue_end
            if (filterParams.created_start) params.created_start = filterParams.created_start
            if (filterParams.created_end) params.created_end = filterParams.created_end
            if (filterParams.week_start) params.week_start = filterParams.week_start
            if (filterParams.week_end) params.week_end = filterParams.week_end
            if (filterParams.published_only) params.published_only = 'true'

            const data = await APIService.adminNewslettersList(params)
            const newsletterArray = Array.isArray(data?.items) ? data.items : Array.isArray(data) ? data : []
            setNewsletters(newsletterArray)
        } catch (error) {
            console.error('Failed to load newsletters', error)
            setMessage({ type: 'error', text: 'Failed to load newsletters' })
        } finally {
            setNewslettersLoading(false)
        }
    }, [appliedFilters])

    useEffect(() => {
        // Data fetch on mount — the loader owns loading/error state.
        // eslint-disable-next-line react-hooks/set-state-in-effect
        loadNewsletters()
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []) // Only on mount

    const applyFilters = () => {
        setAppliedFilters({ ...filters })
        loadNewsletters(filters)
    }

    const resetFilters = () => {
        const defaultFilters = {
            issue_start: '',
            issue_end: '',
            created_start: '',
            created_end: '',
            week_start: '',
            week_end: '',
            published_only: false
        }
        setFilters(defaultFilters)
        setAppliedFilters(defaultFilters)
        loadNewsletters(defaultFilters)
    }

    // Pagination calculations
    const totalPages = Math.ceil(newsletters.length / ITEMS_PER_PAGE)
    const pageStart = newsletters.length ? (currentPage - 1) * ITEMS_PER_PAGE + 1 : 0
    const pageEnd = newsletters.length ? Math.min(currentPage * ITEMS_PER_PAGE, newsletters.length) : 0
    const paginatedNewsletters = useMemo(() => {
        const start = (currentPage - 1) * ITEMS_PER_PAGE
        return newsletters.slice(start, start + ITEMS_PER_PAGE)
    }, [newsletters, currentPage])

    // Multi-select logic
    const selectedIdsSet = useMemo(() => new Set(selectedIds), [selectedIds])
    const currentPageIds = useMemo(() => paginatedNewsletters.map(n => n.id), [paginatedNewsletters])

    const selectedCount = useMemo(() => {
        if (selectAllFiltered) {
            return newsletters.length - selectedIds.length
        }
        return selectedIds.length
    }, [selectAllFiltered, selectedIds, newsletters.length])

    const allPageSelected = useMemo(() => {
        if (currentPageIds.length === 0) return false
        return currentPageIds.every(id => {
            if (selectAllFiltered) return !selectedIdsSet.has(id)
            return selectedIdsSet.has(id)
        })
    }, [currentPageIds, selectedIdsSet, selectAllFiltered])

    const togglePageSelection = (checked) => {
        if (checked) {
            const newIds = selectAllFiltered
                ? selectedIds.filter(id => !currentPageIds.includes(id))
                : [...new Set([...selectedIds, ...currentPageIds])]
            setSelectedIds(newIds)
        } else {
            const newIds = selectAllFiltered
                ? [...new Set([...selectedIds, ...currentPageIds])]
                : selectedIds.filter(id => !currentPageIds.includes(id))
            setSelectedIds(newIds)
        }
    }

    const toggleSelection = (id) => {
        if (selectAllFiltered) {
            setSelectedIds(prev =>
                prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
            )
        } else {
            setSelectedIds(prev =>
                prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
            )
        }
    }

    const toggleSelectAllFiltered = (checked) => {
        setSelectAllFiltered(checked)
        setSelectedIds([])
    }

    const clearSelection = () => {
        setSelectAllFiltered(false)
        setSelectedIds([])
    }

    // View newsletter JSON
    const viewNewsletterJson = async (newsletter) => {
        try {
            setViewingNewsletter(newsletter)
            const data = await APIService.adminNewsletterGet(newsletter.id)
            setNewsletterJson(data)
            setViewerTab('json')
            setCopied(false)
            setJsonViewerOpen(true)
        } catch (error) {
            setMessage({ type: 'error', text: `Failed to load newsletter: ${error.message}` })
        }
    }

    // Get markdown content based on format
    const getMarkdownContent = useCallback(() => {
        if (!newsletterJson) return ''
        const webUrl = newsletterJson.public_slug 
            ? `https://theacademywatch.com/newsletters/${newsletterJson.public_slug}`
            : null
        if (markdownFormat === 'compact') {
            return convertNewsletterToCompactMarkdown(newsletterJson)
        }
        return convertNewsletterToMarkdown(newsletterJson, { webUrl })
    }, [newsletterJson, markdownFormat])

    // Copy content to clipboard
    const copyToClipboard = async (content) => {
        try {
            await navigator.clipboard.writeText(content)
            setCopied(true)
            setTimeout(() => setCopied(false), 2000)
        } catch (error) {
            console.error('Failed to copy:', error)
            setMessage({ type: 'error', text: 'Failed to copy to clipboard' })
        }
    }

    const openPreview = (newsletter) => {
        setPreviewNewsletter(newsletter)
        setPreviewOpen(true)
    }

    const downloadPdf = useCallback(async (newsletter) => {
        if (!newsletter || !newsletter.id) return
        setPdfDownloadingId(newsletter.id)
        try {
            await APIService.adminNewsletterDownloadPdf(newsletter.id)
            setMessage({ type: 'success', text: 'PDF downloaded' })
        } catch (error) {
            console.error('Failed to download PDF:', error)
            setMessage({ type: 'error', text: `PDF download failed: ${error.message || 'Unknown error'}` })
        } finally {
            setPdfDownloadingId(null)
        }
    }, [])

    // Publish/unpublish
    const togglePublish = useCallback(async (newsletter) => {
        try {
            const newStatus = !newsletter.published
            await APIService.adminNewsletterBulkPublish([newsletter.id], newStatus)
            setMessage({
                type: 'success',
                text: `Newsletter ${newStatus ? 'published' : 'unpublished'} successfully`
            })
            await loadNewsletters()
        } catch (error) {
            console.error('Failed to toggle publish:', error)
            setMessage({ type: 'error', text: `Failed to update: ${error.message}` })
        }
    }, [loadNewsletters])

    // Bulk publish
    const bulkPublish = useCallback(async (publish) => {
        setBulkPublishBusy(true)
        try {
            const idsToPublish = selectAllFiltered
                ? newsletters.filter(n => !selectedIds.includes(n.id)).map(n => n.id)
                : selectedIds

            if (idsToPublish.length === 0) {
                setMessage({ type: 'error', text: 'No newsletters selected' })
                return
            }

            const _result = await APIService.adminNewsletterBulkPublish(idsToPublish, publish)

            const successText = `${idsToPublish.length} newsletter(s) ${publish ? 'published' : 'unpublished'}`
            setMessage({ type: 'success', text: successText })
            clearSelection()
            await loadNewsletters()
        } catch (error) {
            setMessage({ type: 'error', text: `Bulk operation failed: ${error.message}` })
        } finally {
            setBulkPublishBusy(false)
        }
    }, [selectAllFiltered, newsletters, selectedIds, loadNewsletters])

    // Delete newsletter
    const confirmDelete = (newsletter) => {
        setDeleteTarget(newsletter)
        setDeleteConfirmOpen(true)
    }

    const executeDelete = useCallback(async () => {
        if (!deleteTarget) return

        try {
            await APIService.adminNewsletterDelete(deleteTarget.id)
            setMessage({ type: 'success', text: 'Newsletter deleted' })
            setDeleteConfirmOpen(false)
            setDeleteTarget(null)
            await loadNewsletters()
        } catch (error) {
            setMessage({ type: 'error', text: `Failed to delete: ${error.message}` })
        }
    }, [deleteTarget, loadNewsletters])

    // Bulk delete
    const bulkDelete = useCallback(async () => {
        const idsToDelete = selectAllFiltered
            ? newsletters.filter(n => !selectedIds.includes(n.id)).map(n => n.id)
            : selectedIds

        if (idsToDelete.length === 0) {
            setMessage({ type: 'error', text: 'No newsletters selected' })
            return
        }

        setBulkDeleteBusy(true)
        try {
            await Promise.all(idsToDelete.map(id => APIService.adminNewsletterDelete(id)))
            setMessage({ type: 'success', text: `${idsToDelete.length} newsletter(s) deleted` })
            clearSelection()
            await loadNewsletters()
        } catch (error) {
            setMessage({ type: 'error', text: `Bulk delete failed: ${error.message}` })
        } finally {
            setBulkDeleteBusy(false)
        }
    }, [selectAllFiltered, newsletters, selectedIds, loadNewsletters])

    // Generate newsletters
    // Generate newsletters
    const executeGeneration = async (teamIds) => {
        setGenerating(true)
        setPendingGamesDialogOpen(false)
        try {
            const requests = teamIds.map(id => buildGenerateTeamRequest({
                teamId: parseInt(id),
                targetDate: generateDate,
                forceRefresh: forceRefresh
            }))

            const successes = []
            const failures = []

            for (const req of requests) {
                try {
                    const res = await APIService.request(req.endpoint, req.options, { admin: req.admin })
                    successes.push(res?.newsletter?.team_name || req.options.body)
                } catch (err) {
                    failures.push(err)
                }
            }

            if (successes.length) {
                setMessage({
                    type: failures.length ? 'error' : 'success',
                    text: failures.length
                        ? `Generated ${successes.length} newsletter(s); ${failures.length} failed: ${failures.map(f => f.message).join('; ')}`
                        : `Generated ${successes.length} newsletter(s) successfully`
                })
                await loadNewsletters()
            } else {
                setMessage({ type: 'error', text: failures[0]?.message || 'Generation failed' })
            }
        } catch (error) {
            setMessage({ type: 'error', text: `Generation failed: ${error.message}` })
        } finally {
            setGenerating(false)
        }
    }

    // Check newsletter readiness for all tracked teams
    const checkReadiness = async () => {
        if (!generateDate) {
            setMessage({ type: 'error', text: 'Please select a target date first' })
            return
        }

        try {
            setReadinessLoading(true)
            const data = await APIService.adminCheckNewsletterReadiness(generateDate)
            setReadinessData(data)
            setReadinessDialogOpen(true)
        } catch (error) {
            console.error('Failed to check readiness:', error)
            setMessage({ type: 'error', text: `Failed to check readiness: ${error.message}` })
        } finally {
            setReadinessLoading(false)
        }
    }

    const generateForSelectedTeams = async () => {
        if (selectedTeams.length === 0) {
            setMessage({ type: 'error', text: 'Please select at least one team' })
            return
        }
        if (!generateDate) {
            setMessage({ type: 'error', text: 'Please select a date' })
            return
        }

        if (generationPreference === 'always_run') {
            await executeGeneration(selectedTeams)
            return
        }

        // Check pending games
        setGenerating(true)
        try {
            const pendingResults = []
            for (const teamId of selectedTeams) {
                const res = await APIService.adminCheckPendingGames(teamId, generateDate)

                if (res.pending) {
                    // Find team name
                    // selectedTeams contains IDs (strings or ints). teams array has team_id and id.
                    // Usually selectedTeams comes from TeamMultiSelect which uses team.id (database ID)
                    const team = teams.find(t => String(t.id) === String(teamId))
                    pendingResults.push({
                        teamName: team?.name || `Team ${teamId}`,
                        games: res.games
                    })
                }
            }

            if (pendingResults.length > 0) {
                setPendingGamesData(pendingResults)
                setPendingGamesDialogOpen(true)
                setGenerating(false)
            } else {
                await executeGeneration(selectedTeams)
            }
        } catch (error) {
            console.error('Check pending games failed', error)
            // If check fails, just proceed to avoid blocking
            await executeGeneration(selectedTeams)
        }
    }

    const generateForAllTeams = () => {
        if (!generateDate) {
            setMessage({ type: 'error', text: 'Please select a date' })
            return
        }
        setGenerateAllConfirmOpen(true)
    }

    const confirmGenerateAll = async () => {
        try {
            setGeneratingAll(true)
            const req = buildGenerateAllRequest({ targetDate: generateDate })
            const result = await APIService.request(req.endpoint, req.options, { admin: req.admin })

            setMessage({ type: 'success', text: result.message || 'Newsletters generated for all teams' })
            setGenerateAllConfirmOpen(false)
            await loadNewsletters()
        } catch (error) {
            setMessage({ type: 'error', text: `Generation failed: ${error.message}` })
        } finally {
            setGeneratingAll(false)
        }
    }

    // --- Deadline (Monday 23:59 GMT — publishes submitted newsletters, charges writers) ---
    const loadDeadline = useCallback(async () => {
        setDeadlineLoading(true)
        try {
            const info = await APIService.adminDeadlineInfo()
            setDeadlineInfo(info)
        } catch (error) {
            console.error('Failed to load deadline info', error)
            setDeadlineInfo(null)
        }

        // Per-writer submission status: the backend only exposes a per-journalist
        // endpoint, so enumerate journalists and fetch each status.
        try {
            const journalists = await APIService.adminGetJournalists()
            const list = (Array.isArray(journalists) ? journalists : []).slice(0, 12)
            const results = await Promise.allSettled(
                list.map(j => APIService.adminWriterSubmissionStatus(j.id))
            )
            const rows = []
            results.forEach((res, idx) => {
                const journalist = list[idx]
                if (res.status === 'fulfilled' && !res.value?.error) {
                    const status = res.value
                    const total = status?.newsletters?.length || 0
                    const submitted = (status?.newsletters || []).filter(n => n.has_submitted).length
                    rows.push({
                        id: journalist.id,
                        name: status?.journalist_name || journalist.display_name || journalist.email || `Writer ${journalist.id}`,
                        submitted,
                        total,
                    })
                }
            })
            setWriterStatuses(rows)
            setWriterStatusError(rows.length === 0 && list.length > 0 ? 'No submission status available' : null)
        } catch (error) {
            setWriterStatuses([])
            setWriterStatusError(error?.body?.error || error.message)
        } finally {
            setDeadlineLoading(false)
        }
    }, [])

    const processDeadline = async () => {
        setProcessingDeadline(true)
        setDeadlineResult(null)
        try {
            const res = await APIService.adminProcessDeadline(
                deadlineWeekOverride ? { weekStartDate: deadlineWeekOverride } : {}
            )
            const result = res?.result || res
            setDeadlineResult(result)
            if (result?.success === false) {
                setMessage({ type: 'error', text: `Deadline processing failed: ${result.error || 'unknown error'}` })
            } else {
                setMessage({
                    type: 'success',
                    text: result?.message
                        || `Deadline processed: ${result?.newsletters_processed ?? 0} newsletter(s) published, ${result?.writers_contributed ?? 0} writer(s) charged`,
                })
                await loadNewsletters()
            }
        } catch (error) {
            setMessage({ type: 'error', text: `Deadline processing failed: ${error?.body?.error || error.message}` })
        } finally {
            setProcessingDeadline(false)
        }
    }

    // --- Digest queue (weekly digest emails for digest-preference subscribers) ---
    const loadDigestQueue = useCallback(async (weekKey) => {
        setDigestLoading(true)
        try {
            const data = await APIService.adminDigestQueue(weekKey || undefined)
            setDigestQueue(data)
            if (data?.week_key) {
                setDigestWeekKey(prev => prev || data.week_key)
            }
        } catch (error) {
            console.error('Failed to load digest queue', error)
            setDigestQueue(null)
            setMessage({ type: 'error', text: `Failed to load digest queue: ${error?.body?.error || error.message}` })
        } finally {
            setDigestLoading(false)
        }
    }, [])

    const sendDigests = async () => {
        setDigestSending(true)
        setDigestSendResult(null)
        try {
            const payload = {}
            if (digestWeekKey) payload.week_key = digestWeekKey
            const res = await APIService.adminSendNewsletterDigests(payload)
            setDigestSendResult(res)
            if (res?.success === false) {
                setMessage({ type: 'error', text: `Digest send failed: ${res?.error || 'unknown error'}` })
            } else {
                const errCount = res?.errors?.length || 0
                setMessage({
                    type: errCount ? 'error' : 'success',
                    text: `Sent ${res?.digests_sent ?? 0} digest email(s)${errCount ? ` — ${errCount} error(s)` : ''}`,
                })
            }
            await loadDigestQueue(digestWeekKey)
        } catch (error) {
            setMessage({ type: 'error', text: `Digest send failed: ${error?.body?.error || error.message}` })
        } finally {
            setDigestSending(false)
        }
    }

    useEffect(() => {
        // Data fetch on mount — the loaders own loading/error state.
        // eslint-disable-next-line react-hooks/set-state-in-effect
        loadDeadline()
        loadDigestQueue()
    }, [loadDeadline, loadDigestQueue])

    return (
        <div className="space-y-6">
            <header>
                <h2 className="text-3xl font-bold tracking-tight">Newsletters</h2>
                <p className="text-muted-foreground mt-1">Generate and manage newsletters for tracked teams</p>
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

            {/* Newsletter Generation */}
            <div className={NEWSLETTER_ACTION_GRID_CLASS}>
                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <Mail className="h-5 w-5" />
                            Generate Newsletters
                        </CardTitle>
                        <CardDescription>Create newsletters for selected teams or all teams</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <div>
                            <Label htmlFor="generate-date">Target Week Date</Label>
                            <Input
                                id="generate-date"
                                type="date"
                                value={generateDate}
                                onChange={(e) => setGenerateDate(e.target.value)}
                            />
                        </div>
                        <div>
                            <Label>Select Teams</Label>
                            <TeamMultiSelect
                                teams={teams}
                                value={selectedTeams}
                                onChange={setSelectedTeams}
                                placeholder="Select teams..."
                            />
                        </div>
                        <div className="flex items-center space-x-2">
                            <input
                                type="checkbox"
                                id="force-refresh"
                                checked={forceRefresh}
                                onChange={(e) => setForceRefresh(e.target.checked)}
                                className="h-4 w-4 rounded border-border"
                            />
                            <Label htmlFor="force-refresh" className="font-normal text-sm cursor-pointer">
                                Force Refresh Data (clear cache)
                            </Label>
                        </div>
                        
                        {/* Readiness Check Button */}
                        <Button 
                            onClick={checkReadiness} 
                            variant="outline" 
                            className="w-full"
                            disabled={readinessLoading || !generateDate}
                        >
                            {readinessLoading ? (
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            ) : readinessData?.ready ? (
                                <CheckCircle2 className="mr-2 h-4 w-4 text-emerald-600" />
                            ) : readinessData ? (
                                <AlertCircle className="mr-2 h-4 w-4 text-amber-500" />
                            ) : (
                                <Calendar className="mr-2 h-4 w-4" />
                            )}
                            {readinessData?.ready 
                                ? 'All Games Complete - Ready to Generate!' 
                                : readinessData 
                                    ? `${readinessData.summary?.pending_count || 0} team(s) have pending games`
                                    : 'Check Newsletter Readiness'
                            }
                        </Button>
                        
                        <div className="flex gap-2">
                            <Button onClick={generateForSelectedTeams} className="flex-1" disabled={generating || generatingAll}>
                                {generating && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                Generate for Selected
                            </Button>
                            <Button onClick={generateForAllTeams} variant="outline" className="flex-1" disabled={generating || generatingAll}>
                                Generate for All
                            </Button>
                        </div>
                    </CardContent>
                </Card>

                {/* Deadline */}
                <Card data-testid="deadline-card">
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <Clock className="h-5 w-5" />
                            Deadline
                        </CardTitle>
                        <CardDescription>
                            Monday 23:59 GMT — publishes newsletters with submitted content and charges contributing writers.
                            No cron runs this; process it manually.
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        {deadlineLoading && !deadlineInfo ? (
                            <div className="space-y-2">
                                <Skeleton className="h-5 w-2/3" />
                                <Skeleton className="h-5 w-1/2" />
                                <Skeleton className="h-5 w-3/5" />
                            </div>
                        ) : deadlineInfo ? (
                            <dl className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-sm">
                                <div>
                                    <dt className="text-xs text-muted-foreground">Next deadline</dt>
                                    <dd className="font-medium">{new Date(deadlineInfo.next_deadline).toLocaleString()}</dd>
                                </div>
                                <div>
                                    <dt className="text-xs text-muted-foreground">Time remaining</dt>
                                    <dd className="font-medium">{deadlineInfo.time_remaining_formatted}</dd>
                                </div>
                                <div>
                                    <dt className="text-xs text-muted-foreground">Week starting</dt>
                                    <dd className="font-medium">{deadlineInfo.week_start_date}</dd>
                                </div>
                            </dl>
                        ) : (
                            <p className="text-sm text-muted-foreground">Deadline info unavailable</p>
                        )}

                        <div>
                            <p className="text-sm font-medium mb-1">Writer submissions this week</p>
                            {deadlineLoading ? (
                                <Skeleton className="h-4 w-1/2" />
                            ) : writerStatuses.length > 0 ? (
                                <ul className="space-y-1 text-sm">
                                    {writerStatuses.map(w => (
                                        <li key={w.id} className="flex items-center justify-between gap-2">
                                            <span className="truncate">{w.name}</span>
                                            {w.total === 0 ? (
                                                <Badge variant="outline">no newsletters</Badge>
                                            ) : (
                                                <Badge
                                                    variant="outline"
                                                    className={w.submitted === w.total
                                                        ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                                                        : 'bg-amber-50 text-amber-700 border-amber-200'}
                                                >
                                                    {w.submitted}/{w.total} submitted
                                                </Badge>
                                            )}
                                        </li>
                                    ))}
                                </ul>
                            ) : (
                                <p className="text-xs text-muted-foreground">
                                    {writerStatusError ? `Submission status unavailable (${writerStatusError})` : 'No writers found'}
                                </p>
                            )}
                        </div>

                        <div className="flex flex-col sm:flex-row sm:items-end gap-2">
                            <div className="flex-1">
                                <Label htmlFor="deadline-week-override" className="text-xs">Week start override (optional)</Label>
                                <Input
                                    id="deadline-week-override"
                                    type="date"
                                    value={deadlineWeekOverride}
                                    onChange={(e) => setDeadlineWeekOverride(e.target.value)}
                                    data-testid="deadline-week-override"
                                />
                            </div>
                            <Button
                                variant="destructive"
                                onClick={() => setDeadlineConfirmOpen(true)}
                                disabled={processingDeadline}
                                data-testid="deadline-process"
                            >
                                {processingDeadline && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                Process deadline…
                            </Button>
                        </div>
                        <p className="text-xs text-amber-600">
                            Processing publishes and charges writers — it cannot be undone.
                        </p>

                        {deadlineResult && (
                            <div className="rounded-md border bg-muted/30 p-3 text-sm" data-testid="deadline-result">
                                {deadlineResult.success === false ? (
                                    <p className="text-rose-600">Failed: {deadlineResult.error}</p>
                                ) : (
                                    <p>
                                        {deadlineResult.newsletters_processed ?? 0} newsletter(s) processed ·{' '}
                                        {deadlineResult.writers_contributed ?? 0} writer(s) contributed
                                        {deadlineResult.message ? ` · ${deadlineResult.message}` : ''}
                                    </p>
                                )}
                            </div>
                        )}
                    </CardContent>
                </Card>

                {/* Digest queue */}
                <Card data-testid="digest-queue-card">
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <Inbox className="h-5 w-5" />
                            Digest Queue
                        </CardTitle>
                        <CardDescription>
                            Weekly digest emails queued for subscribers who prefer digest delivery
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <div className="flex flex-col sm:flex-row sm:items-end gap-2">
                            <div className="flex-1">
                                <Label htmlFor="digest-week-key" className="text-xs">Week key</Label>
                                <Input
                                    id="digest-week-key"
                                    value={digestWeekKey}
                                    onChange={(e) => setDigestWeekKey(e.target.value)}
                                    placeholder="e.g. 2026-W24 (blank = current week)"
                                    data-testid="digest-week-key"
                                />
                            </div>
                            <Button
                                variant="outline"
                                onClick={() => loadDigestQueue(digestWeekKey)}
                                disabled={digestLoading}
                                data-testid="digest-queue-load"
                            >
                                {digestLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                Load queue
                            </Button>
                        </div>

                        {digestLoading && !digestQueue ? (
                            <div className="space-y-2">
                                <Skeleton className="h-5 w-2/3" />
                                <Skeleton className="h-5 w-1/2" />
                            </div>
                        ) : digestQueue ? (
                            <div className="space-y-2 text-sm" data-testid="digest-queue-stats">
                                <div className="flex flex-wrap items-center gap-2">
                                    <Badge variant="outline">{digestQueue.week_key}</Badge>
                                    <Badge
                                        variant="outline"
                                        className={(digestQueue.pending?.items || 0) > 0
                                            ? 'bg-amber-50 text-amber-700 border-amber-200'
                                            : 'bg-emerald-50 text-emerald-700 border-emerald-200'}
                                    >
                                        {digestQueue.pending?.items ?? 0} pending item(s) · {digestQueue.pending?.users ?? 0} user(s)
                                    </Badge>
                                    <Badge variant="outline">
                                        {digestQueue.sent?.items ?? 0} sent item(s) · {digestQueue.sent?.users ?? 0} user(s)
                                    </Badge>
                                </div>
                            </div>
                        ) : (
                            <p className="text-sm text-muted-foreground">Digest queue unavailable</p>
                        )}

                        <Button
                            onClick={() => setDigestConfirmOpen(true)}
                            disabled={digestSending || digestLoading || !(digestQueue?.pending?.items > 0)}
                            data-testid="digest-queue-send"
                        >
                            {digestSending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            Send digests…
                        </Button>
                        {digestQueue && (digestQueue.pending?.items ?? 0) === 0 && (
                            <p className="text-xs text-muted-foreground">Nothing pending for this week.</p>
                        )}

                        {digestSendResult && (
                            <div className="rounded-md border bg-muted/30 p-3 text-sm" data-testid="digest-send-result">
                                {digestSendResult.success === false ? (
                                    <p className="text-rose-600">Failed: {digestSendResult.error}</p>
                                ) : (
                                    <p>
                                        {digestSendResult.digests_sent ?? 0} digest(s) sent
                                        {typeof digestSendResult.newsletters_included === 'number'
                                            ? ` covering ${digestSendResult.newsletters_included} newsletter item(s)`
                                            : ''}
                                        {digestSendResult.errors?.length ? ` · ${digestSendResult.errors.length} error(s)` : ''}
                                    </p>
                                )}
                            </div>
                        )}
                    </CardContent>
                </Card>

                {/* Loan data seeding moved to /admin/seeding */}
                <Card data-testid="seeding-moved-card">
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <Sprout className="h-5 w-5" />
                            Loan Data Seeding
                        </CardTitle>
                        <CardDescription>
                            Seeding now lives on its own page alongside the rest of the data tools
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <Button asChild variant="outline" data-testid="seeding-link">
                            <Link to="/admin/seeding">Open Seeding &amp; Rebuild</Link>
                        </Button>
                    </CardContent>
                </Card>
            </div>

            {/* Filters */}
            <Card>
                <CardHeader>
                    <CardTitle>Filters</CardTitle>
                    <CardDescription>Filter newsletters by date ranges and status</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div>
                            <Label className="text-xs font-semibold">Issue Date</Label>
                            <div className="grid grid-cols-2 gap-2 mt-1">
                                <Input
                                    type="date"
                                    value={filters.issue_start}
                                    onChange={(e) => setFilters({ ...filters, issue_start: e.target.value })}
                                    placeholder="Start"
                                />
                                <Input
                                    type="date"
                                    value={filters.issue_end}
                                    onChange={(e) => setFilters({ ...filters, issue_end: e.target.value })}
                                    placeholder="End"
                                />
                            </div>
                        </div>
                        <div>
                            <Label className="text-xs font-semibold">Created Date</Label>
                            <div className="grid grid-cols-2 gap-2 mt-1">
                                <Input
                                    type="date"
                                    value={filters.created_start}
                                    onChange={(e) => setFilters({ ...filters, created_start: e.target.value })}
                                    placeholder="Start"
                                />
                                <Input
                                    type="date"
                                    value={filters.created_end}
                                    onChange={(e) => setFilters({ ...filters, created_end: e.target.value })}
                                    placeholder="End"
                                />
                            </div>
                        </div>
                        <div>
                            <Label className="text-xs font-semibold">Week Range</Label>
                            <div className="grid grid-cols-2 gap-2 mt-1">
                                <Input
                                    type="date"
                                    value={filters.week_start}
                                    onChange={(e) => setFilters({ ...filters, week_start: e.target.value })}
                                    placeholder="Start"
                                />
                                <Input
                                    type="date"
                                    value={filters.week_end}
                                    onChange={(e) => setFilters({ ...filters, week_end: e.target.value })}
                                    placeholder="End"
                                />
                            </div>
                        </div>
                    </div>
                    <div className="flex items-center justify-between">
                        <label className="flex items-center gap-2 text-sm">
                            <input
                                type="checkbox"
                                checked={filters.published_only}
                                onChange={(e) => setFilters({ ...filters, published_only: e.target.checked })}
                                className="h-4 w-4"
                            />
                            <span>Published only</span>
                        </label>
                        <div className="flex gap-2">
                            <Button size="sm" onClick={applyFilters}>Apply Filters</Button>
                            <Button size="sm" variant="ghost" onClick={resetFilters}>Reset</Button>
                        </div>
                    </div>
                </CardContent>
            </Card>

            {/* Newsletter List */}
            <Card>
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <div>
                            <CardTitle>Newsletters</CardTitle>
                            <CardDescription>
                                {newsletters.length > 0 && `Showing ${pageStart}–${pageEnd} of ${newsletters.length}`}
                            </CardDescription>
                        </div>
                        <Button onClick={() => loadNewsletters()} variant="outline" size="sm">
                            Refresh
                        </Button>
                    </div>
                </CardHeader>
                <CardContent>
                    {newslettersLoading ? (
                        <div className="text-center py-8 text-muted-foreground">
                            <Loader2 className="h-8 w-8 animate-spin mx-auto mb-2" />
                            Loading newsletters...
                        </div>
                    ) : newsletters.length === 0 ? (
                        <div className="text-center py-8 text-muted-foreground">
                            <Mail className="h-12 w-12 mx-auto mb-3 opacity-50" />
                            <p>No newsletters found</p>
                            <p className="text-sm mt-1">Generate your first newsletter above</p>
                        </div>
                    ) : (
                        <>
                            {/* Bulk Actions */}
                            <div className="flex flex-wrap items-center gap-2 mb-4">
                                <label className="flex items-center gap-2 text-xs">
                                    <input
                                        type="checkbox"
                                        checked={selectAllFiltered}
                                        onChange={(e) => toggleSelectAllFiltered(e.target.checked)}
                                        className="h-4 w-4"
                                    />
                                    <span>Select all filtered</span>
                                </label>
                                <span className="text-xs text-muted-foreground">Total {newsletters.length}</span>
                                {selectAllFiltered && selectedIds.length > 0 && (
                                    <span className="text-xs text-muted-foreground">Excluding {selectedIds.length}</span>
                                )}
                                <span className="text-xs font-semibold">Selected {selectedCount}</span>
                                
                                <Button
                                    size="sm"
                                    onClick={() => bulkPublish(true)}
                                    disabled={selectedCount === 0 || bulkPublishBusy || bulkDeleteBusy}
                                >
                                    {bulkPublishBusy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                    Publish Selected
                                </Button>
                                <Button
                                    size="sm"
                                    variant="outline"
                                    onClick={() => bulkPublish(false)}
                                    disabled={selectedCount === 0 || bulkPublishBusy || bulkDeleteBusy}
                                >
                                    Unpublish Selected
                                </Button>
                                <Button
                                    size="sm"
                                    variant="destructive"
                                    onClick={bulkDelete}
                                    disabled={selectedCount === 0 || bulkDeleteBusy}
                                >
                                    {bulkDeleteBusy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                    Delete Selected
                                </Button>
                                <Button
                                    size="sm"
                                    variant="ghost"
                                    onClick={clearSelection}
                                    disabled={selectedCount === 0 || bulkPublishBusy || bulkDeleteBusy}
                                >
                                    Clear Selection
                                </Button>
                            </div>

                            {/* Table */}
                            <div className="overflow-x-auto">
                                <table className="min-w-full text-sm">
                                    <thead>
                                        <tr className="border-b">
                                            <th className="p-2 text-left w-10">
                                                <input
                                                    type="checkbox"
                                                    checked={allPageSelected}
                                                    onChange={(e) => togglePageSelection(e.target.checked)}
                                                    className="h-4 w-4"
                                                />
                                            </th>
                                            <th className="p-2 text-left">ID</th>
                                            <th className="p-2 text-left">Team</th>
                                            <th className="p-2 text-left">Issue #</th>
                                            <th className="p-2 text-left">Week</th>
                                            <th className="p-2 text-left">Status</th>
                                            <th className="p-2 text-left">Actions</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {paginatedNewsletters.map((newsletter) => {
                                            const isSelected = selectAllFiltered
                                                ? !selectedIdsSet.has(newsletter.id)
                                                : selectedIdsSet.has(newsletter.id)

                                            return (
                                                <tr key={newsletter.id} className="border-b hover:bg-accent/50">
                                                    <td className="p-2">
                                                        <input
                                                            type="checkbox"
                                                            checked={isSelected}
                                                            onChange={() => toggleSelection(newsletter.id)}
                                                            className="h-4 w-4"
                                                        />
                                                    </td>
                                                    <td className="p-2 text-muted-foreground">
                                                        <Link
                                                            to={`/admin/newsletters/${newsletter.id}`}
                                                            className="hover:underline"
                                                        >
                                                            #{newsletter.id}
                                                        </Link>
                                                    </td>
                                                    <td className="p-2 font-medium">
                                                        <Link
                                                            to={`/admin/newsletters/${newsletter.id}`}
                                                            className="hover:underline"
                                                            data-testid={`newsletter-detail-link-${newsletter.id}`}
                                                        >
                                                            {newsletter.team_name || 'Unknown'}
                                                        </Link>
                                                    </td>
                                                    <td className="p-2">{newsletter.issue_number || 'N/A'}</td>
                                                    <td className="p-2 text-xs">
                                                        {newsletter.week_start_date && newsletter.week_end_date ? (
                                                            <span className="flex items-center gap-1">
                                                                <Calendar className="h-3 w-3" />
                                                                {newsletter.week_start_date} → {newsletter.week_end_date}
                                                            </span>
                                                        ) : '—'}
                                                    </td>
                                                    <td className="p-2">
                                                        <Badge variant={newsletter.published ? 'default' : 'secondary'}>
                                                            {newsletter.published ? 'Published' : 'Draft'}
                                                        </Badge>
                                                    </td>
                                                    <td className="p-2">
                                                        <div className="flex gap-1">
                                                            <Button
                                                                size="sm"
                                                                variant="outline"
                                                                onClick={() => openPreview(newsletter)}
                                                                title="Preview"
                                                            >
                                                                <Monitor className="h-4 w-4" />
                                                            </Button>
                                                            <Button
                                                                size="sm"
                                                                variant="outline"
                                                                onClick={() => viewNewsletterJson(newsletter)}
                                                                title="View JSON"
                                                            >
                                                                <FileJson className="h-4 w-4" />
                                                            </Button>
                                                            <Button
                                                                size="sm"
                                                                variant="outline"
                                                                onClick={() => downloadPdf(newsletter)}
                                                                title="Download PDF"
                                                                disabled={pdfDownloadingId === newsletter.id}
                                                            >
                                                                {pdfDownloadingId === newsletter.id ? (
                                                                    <Loader2 className="h-4 w-4 animate-spin" />
                                                                ) : (
                                                                    <Download className="h-4 w-4" />
                                                                )}
                                                            </Button>
                                                            <Button
                                                                size="sm"
                                                                variant={newsletter.published ? 'secondary' : 'default'}
                                                                onClick={() => togglePublish(newsletter)}
                                                                title={newsletter.published ? 'Unpublish' : 'Publish'}
                                                            >
                                                                <Send className="h-4 w-4" />
                                                            </Button>
                                                            <Button
                                                                size="sm"
                                                                variant="destructive"
                                                                onClick={() => confirmDelete(newsletter)}
                                                                title="Delete"
                                                            >
                                                                <Trash2 className="h-4 w-4" />
                                                            </Button>
                                                        </div>
                                                    </td>
                                                </tr>
                                            )
                                        })}
                                    </tbody>
                                </table>
                            </div>

                            {/* Pagination */}
                            {totalPages > 1 && (
                                <div className="flex items-center justify-between border-t pt-4 mt-4">
                                    <span className="text-sm text-muted-foreground">
                                        Page {currentPage} of {totalPages}
                                    </span>
                                    <div className="flex gap-2">
                                        <Button
                                            variant="outline"
                                            size="sm"
                                            onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                                            disabled={currentPage === 1}
                                        >
                                            Previous
                                        </Button>
                                        <Button
                                            variant="outline"
                                            size="sm"
                                            onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                                            disabled={currentPage === totalPages}
                                        >
                                            Next
                                        </Button>
                                    </div>
                                </div>
                            )}
                        </>
                    )}
                </CardContent>
            </Card>

            {/* Preview Dialog */}
            <NewsletterPreviewDialog
                open={previewOpen}
                onOpenChange={setPreviewOpen}
                newsletter={previewNewsletter}
                onStatus={setMessage}
            />

            {/* JSON/Markdown Viewer Dialog */}
            <Dialog open={jsonViewerOpen} onOpenChange={setJsonViewerOpen}>
                <DialogContent className="max-w-4xl w-[95vw] h-[85vh] flex flex-col p-0 gap-0">
                    <DialogHeader className="px-6 py-4 border-b shrink-0">
                        <DialogTitle className="flex items-center gap-2">
                            <FileJson className="h-5 w-5" />
                            Newsletter Data
                        </DialogTitle>
                        <DialogDescription>
                            {viewingNewsletter?.team_name} - Issue #{viewingNewsletter?.issue_number}
                        </DialogDescription>
                    </DialogHeader>
                    
                    <Tabs value={viewerTab} onValueChange={setViewerTab} className="flex-1 flex flex-col min-h-0 px-6 py-4">
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 shrink-0">
                            <TabsList>
                                <TabsTrigger value="json" className="gap-2">
                                    <FileJson className="h-4 w-4" />
                                    JSON
                                </TabsTrigger>
                                <TabsTrigger value="markdown" className="gap-2">
                                    <FileText className="h-4 w-4" />
                                    Markdown
                                </TabsTrigger>
                            </TabsList>
                            
                            {viewerTab === 'markdown' && (
                                <div className="flex items-center gap-2">
                                    <Label className="text-sm text-muted-foreground whitespace-nowrap">Format:</Label>
                                    <select
                                        value={markdownFormat}
                                        onChange={(e) => setMarkdownFormat(e.target.value)}
                                        className="h-8 rounded-md border border-input bg-background px-2 py-1 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                                    >
                                        <option value="full">Full</option>
                                        <option value="compact">Compact</option>
                                    </select>
                                </div>
                            )}
                        </div>
                        
                        <TabsContent value="json" className="flex-1 min-h-0 mt-0 data-[state=active]:flex data-[state=active]:flex-col">
                            <div className="flex justify-end mb-2 shrink-0">
                                <Button
                                    size="sm"
                                    variant="outline"
                                    className="gap-2"
                                    onClick={() => copyToClipboard(JSON.stringify(newsletterJson, null, 2))}
                                >
                                    {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                                    {copied ? 'Copied!' : 'Copy'}
                                </Button>
                            </div>
                            <div className="flex-1 min-h-0 overflow-auto rounded-lg border bg-muted">
                                <pre className="p-4 text-xs font-mono whitespace-pre">
                                    {JSON.stringify(newsletterJson, null, 2)}
                                </pre>
                            </div>
                        </TabsContent>
                        
                        <TabsContent value="markdown" className="flex-1 min-h-0 mt-0 data-[state=active]:flex data-[state=active]:flex-col">
                            <div className="flex justify-end mb-2 shrink-0">
                                <Button
                                    size="sm"
                                    variant="outline"
                                    className="gap-2"
                                    onClick={() => copyToClipboard(getMarkdownContent())}
                                >
                                    {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                                    {copied ? 'Copied!' : 'Copy'}
                                </Button>
                            </div>
                            <div className="flex-1 min-h-0 overflow-auto rounded-lg border bg-zinc-900">
                                <pre className="p-4 text-zinc-100 text-sm font-mono whitespace-pre-wrap">
                                    {getMarkdownContent()}
                                </pre>
                            </div>
                        </TabsContent>
                    </Tabs>
                    
                    <div className="px-6 py-4 border-t shrink-0 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                        <p className="text-xs text-muted-foreground">
                            💡 Copy and paste the markdown content above
                        </p>
                        <Button onClick={() => setJsonViewerOpen(false)}>Close</Button>
                    </div>
                </DialogContent>
            </Dialog>

            {/* Delete Confirmation Dialog */}
            <Dialog open={deleteConfirmOpen} onOpenChange={setDeleteConfirmOpen}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Delete Newsletter?</DialogTitle>
                        <DialogDescription>
                            Are you sure you want to delete the newsletter for <strong>{deleteTarget?.team_name}</strong> (Issue #{deleteTarget?.issue_number})?
                            This action cannot be undone.
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setDeleteConfirmOpen(false)}>
                            Cancel
                        </Button>
                        <Button variant="destructive" onClick={executeDelete}>
                            Delete
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Generate All Teams Confirmation Dialog */}
            <Dialog open={generateAllConfirmOpen} onOpenChange={setGenerateAllConfirmOpen}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Generate for All Teams?</DialogTitle>
                        <DialogDescription>
                            This will generate newsletters for ALL teams. This may take a while.
                            Are you sure you want to continue?
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setGenerateAllConfirmOpen(false)} disabled={generatingAll}>
                            Cancel
                        </Button>
                        <Button onClick={confirmGenerateAll} disabled={generatingAll}>
                            {generatingAll && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            Generate
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
            {/* Pending Games Dialog */}
            <Dialog open={pendingGamesDialogOpen} onOpenChange={setPendingGamesDialogOpen}>
                <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2 text-amber-600">
                            <AlertCircle className="h-5 w-5" />
                            Pending Games Detected
                        </DialogTitle>
                        <DialogDescription>
                            The following teams have tracked players with upcoming games in the target week.
                            Generating now might miss these match stats.
                        </DialogDescription>
                    </DialogHeader>

                    <div className="space-y-4 my-4">
                        {pendingGamesData.map((item, idx) => (
                            <div key={idx} className="border rounded-md p-3 bg-muted/30">
                                <h4 className="font-semibold mb-2">{item.teamName}</h4>
                                <ul className="space-y-2">
                                    {item.games.map((game, gIdx) => (
                                        <li key={gIdx} className="text-sm flex items-start gap-2">
                                            <Calendar className="h-4 w-4 mt-0.5 text-muted-foreground" />
                                            <div>
                                                <div>
                                                    <div className="font-medium">
                                                        {game.player_name} ({game.loan_team})
                                                    </div>
                                                    <div className="text-sm">
                                                        vs {game.opponent} ({game.league})
                                                    </div>
                                                    <div className="text-xs text-muted-foreground">
                                                        {new Date(game.date).toLocaleString()}
                                                    </div>
                                                </div>
                                            </div>
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        ))}
                    </div>

                    <DialogFooter>
                        <Button variant="outline" onClick={() => setPendingGamesDialogOpen(false)}>
                            Cancel
                        </Button>
                        <Button onClick={() => executeGeneration(selectedTeams)}>
                            Generate Anyway
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Newsletter Readiness Dialog */}
            <Dialog open={readinessDialogOpen} onOpenChange={setReadinessDialogOpen}>
                <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
                    <DialogHeader>
                        <DialogTitle className={`flex items-center gap-2 ${readinessData?.ready ? 'text-emerald-600' : 'text-amber-600'}`}>
                            {readinessData?.ready ? (
                                <CheckCircle2 className="h-5 w-5" />
                            ) : (
                                <AlertCircle className="h-5 w-5" />
                            )}
                            {readinessData?.ready ? 'All Games Complete!' : 'Some Games Pending'}
                        </DialogTitle>
                        <DialogDescription>
                            Week: {readinessData?.week_start} to {readinessData?.week_end}
                        </DialogDescription>
                    </DialogHeader>

                    {readinessData && (
                        <div className="space-y-4 my-4">
                            {/* Summary */}
                            <div className={`p-4 rounded-lg ${readinessData.ready ? 'bg-emerald-50 border border-emerald-200' : 'bg-amber-50 border border-amber-200'}`}>
                                <div className="flex items-center justify-between">
                                    <span className="font-medium">
                                        {readinessData.ready ? (
                                            '✅ Ready to generate newsletters!'
                                        ) : (
                                            `⚠️ ${readinessData.summary?.pending_count} of ${readinessData.summary?.total_teams} team(s) have pending games`
                                        )}
                                    </span>
                                    <div className="flex gap-2">
                                        <Badge variant="outline" className="bg-emerald-50">
                                            {readinessData.summary?.ready_count} ready
                                        </Badge>
                                        {readinessData.summary?.pending_count > 0 && (
                                            <Badge variant="outline" className="bg-amber-100">
                                                {readinessData.summary?.pending_count} pending
                                            </Badge>
                                        )}
                                    </div>
                                </div>
                            </div>

                            {/* Team Details */}
                            <div className="border rounded-lg overflow-hidden">
                                <div className="max-h-[400px] overflow-auto">
                                    <table className="w-full text-sm">
                                        <thead className="bg-muted sticky top-0">
                                            <tr className="text-left">
                                                <th className="px-3 py-2 w-10">Status</th>
                                                <th className="px-3 py-2">Team</th>
                                                <th className="px-3 py-2 w-24 text-center">Active Players</th>
                                                <th className="px-3 py-2 w-24 text-center">Pending</th>
                                                <th className="px-3 py-2">Details</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {readinessData.teams?.map((team, idx) => (
                                                <tr key={idx} className={`border-t ${team.ready ? '' : 'bg-amber-50'}`}>
                                                    <td className="px-3 py-2 text-center">
                                                        {team.ready ? (
                                                            <CheckCircle2 className="h-5 w-5 text-emerald-600 mx-auto" />
                                                        ) : (
                                                            <AlertCircle className="h-5 w-5 text-amber-500 mx-auto" />
                                                        )}
                                                    </td>
                                                    <td className="px-3 py-2 font-medium">{team.team_name}</td>
                                                    <td className="px-3 py-2 text-center text-muted-foreground">{team.total_loans}</td>
                                                    <td className="px-3 py-2 text-center">
                                                        {team.pending_count > 0 ? (
                                                            <Badge variant="outline" className="bg-amber-100">{team.pending_count}</Badge>
                                                        ) : (
                                                            <span className="text-muted-foreground">—</span>
                                                        )}
                                                    </td>
                                                    <td className="px-3 py-2">
                                                        {team.pending_games?.length > 0 ? (
                                                            <div className="text-xs text-muted-foreground">
                                                                {team.pending_games.slice(0, 2).map((g, i) => (
                                                                    <div key={i}>
                                                                        {g.player_name} vs {g.opponent} ({new Date(g.date).toLocaleDateString()})
                                                                    </div>
                                                                ))}
                                                                {team.pending_games.length > 2 && (
                                                                    <div className="text-muted-foreground italic">
                                                                        +{team.pending_games.length - 2} more...
                                                                    </div>
                                                                )}
                                                            </div>
                                                        ) : (
                                                            <span className="text-emerald-600 text-xs">All complete</span>
                                                        )}
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        </div>
                    )}

                    <DialogFooter>
                        <Button variant="outline" onClick={() => setReadinessDialogOpen(false)}>
                            Close
                        </Button>
                        {readinessData?.ready && (
                            <Button onClick={() => {
                                setReadinessDialogOpen(false)
                                // Auto-select all ready teams for generation
                                const readyTeamIds = readinessData.teams
                                    ?.filter(t => t.ready)
                                    .map(t => t.team_id)
                                if (readyTeamIds?.length) {
                                    setSelectedTeams(readyTeamIds.map(String))
                                }
                            }}>
                                Select All Ready Teams
                            </Button>
                        )}
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Deadline processing ConfirmGate (MONEY — charges writers) */}
            <ConfirmGate
                open={deadlineConfirmOpen}
                onOpenChange={setDeadlineConfirmOpen}
                title="Process newsletter deadline"
                description={`Publishes every newsletter with submitted content for ${deadlineWeekOverride || 'the current week'} and CHARGES the contributing writers. This cannot be undone.`}
                confirmWord="CHARGE"
                confirmLabel="Process & charge"
                destructive
                onConfirm={processDeadline}
            />

            {/* Digest send ConfirmGate (sends real email) */}
            <ConfirmGate
                open={digestConfirmOpen}
                onOpenChange={setDigestConfirmOpen}
                title="Send digest emails"
                description={`Sends digest emails to ${digestQueue?.pending?.users ?? 0} subscriber(s) covering ${digestQueue?.pending?.items ?? 0} queued newsletter item(s) for ${digestQueue?.week_key || 'the current week'}. Emails go to real subscribers.`}
                confirmWord="SEND"
                confirmLabel="Send digests"
                destructive
                onConfirm={sendDigests}
            />
        </div>
    )
}
