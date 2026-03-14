import { useState, useEffect, useMemo, useCallback } from 'react'
import { APIService } from '@/lib/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import {
    Accordion,
    AccordionContent,
    AccordionItem,
    AccordionTrigger,
} from '@/components/ui/accordion'
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
    DialogFooter,
} from '@/components/ui/dialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Mail, Calendar, Send, Trash2, AlertCircle, CheckCircle2, FileJson, Loader2, Monitor, Copy, Check, FileText } from 'lucide-react'
import { convertNewsletterToMarkdown, convertNewsletterToCompactMarkdown } from '@/lib/newsletter-markdown'
import TeamMultiSelect from '@/components/ui/TeamMultiSelect.jsx'
import TeamSelect from '@/components/ui/TeamSelect.jsx'
import { NewsletterPreviewDialog } from '@/components/admin/NewsletterPreviewDialog'
import { NEWSLETTER_ACTION_GRID_CLASS } from './admin-newsletters-layout.js'
import { buildGenerateTeamRequest, buildGenerateAllRequest, buildSeedTeamRequest, buildSeedTop5Request } from './admin-newsletters-api.js'
import {
    seedSelectedButtonLabel,
    seedTop5ButtonLabel,
    buildMissingNamesParams,
    buildBackfillNamesPayload,
} from './admin-newsletters-seeding.js'

const ITEMS_PER_PAGE = 20

export function AdminNewsletters() {
    // State
    const [newsletters, setNewsletters] = useState([])
    const [newslettersLoading, setNewslettersLoading] = useState(false)
    const [selectedTeams, setSelectedTeams] = useState([])
    const [generateDate, setGenerateDate] = useState('')
    const [seedYear, setSeedYear] = useState(new Date().getFullYear().toString())
    const [seedTop5DryRun, setSeedTop5DryRun] = useState(false)
    const [seedingTop5, setSeedingTop5] = useState(false)
    const [seedingTeams, setSeedingTeams] = useState(false)
    const [missingNames, setMissingNames] = useState([])
    const [missingNamesBusy, setMissingNamesBusy] = useState(false)
    const [missingNamesTeamDbId, setMissingNamesTeamDbId] = useState(null)
    const [missingNamesTeamApiId, setMissingNamesTeamApiId] = useState('')
    const [missingNamesLimit, setMissingNamesLimit] = useState('')
    const [missingNamesDryRun, setMissingNamesDryRun] = useState(false)
    const [message, setMessage] = useState(null)
    const [teams, setTeams] = useState([])

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

            const result = await APIService.adminNewsletterBulkPublish(idsToPublish, publish)

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

    // Seeding operations
    const seedTop5 = async () => {
        try {
            setSeedingTop5(true)
            const req = buildSeedTop5Request({ season: seedYear, dryRun: seedTop5DryRun })
            const result = await APIService.request(req.endpoint, req.options, { admin: req.admin })

            setMessage({
                type: 'success',
                text: seedTop5DryRun ? 'Dry run completed' : 'Top-5 leagues seeded successfully'
            })
        } catch (error) {
            setMessage({ type: 'error', text: `Seeding failed: ${error.message}` })
        } finally {
            setSeedingTop5(false)
        }
    }

    const seedSelectedTeams = async () => {
        if (selectedTeams.length === 0) {
            setMessage({ type: 'error', text: 'Please select teams to seed' })
            return
        }

        const season = parseInt(seedYear, 10)
        if (!season || Number.isNaN(season)) {
            setMessage({ type: 'error', text: 'Please enter a valid season year before seeding' })
            return
        }

        try {
            setSeedingTeams(true)
            const requests = selectedTeams.map((id) => buildSeedTeamRequest({ teamId: id, season }))
            const outcomes = await Promise.all(requests.map(async (req) => {
                try {
                    const res = await APIService.request(req.endpoint, req.options, { admin: req.admin })
                    return { ok: true, teamId: req.options?.body, res }
                } catch (err) {
                    return { ok: false, teamId: req.options?.body, error: err }
                }
            }))

            const successes = outcomes.filter(o => o.ok).length
            const failures = outcomes.filter(o => !o.ok)

            if (failures.length) {
                const detail = failures.map(f => f.error?.message || 'unknown error').join('; ')
                setMessage({ type: 'error', text: `Seeding completed with ${failures.length} failure(s): ${detail}` })
            } else {
                setMessage({ type: 'success', text: `Seeded ${successes} team(s) for ${season}` })
            }
        } catch (error) {
            setMessage({ type: 'error', text: `Seeding failed: ${error.message}` })
        } finally {
            setSeedingTeams(false)
        }
    }

    const loadMissingNames = useCallback(async ({ silent = false } = {}) => {
        setMissingNamesBusy(true)
        try {
            const params = buildMissingNamesParams({
                season: seedYear,
                teamDbId: missingNamesTeamDbId,
                teamApiId: missingNamesTeamApiId,
                activeOnly: true,
                limit: missingNamesLimit,
            })
            const rows = await APIService.adminMissingNames(params)
            const list = Array.isArray(rows) ? rows : []
            setMissingNames(list)

            if (!silent) {
                const count = list.length
                setMessage({
                    type: 'success',
                    text: count
                        ? `Found ${count} loan${count === 1 ? '' : 's'} with missing names`
                        : 'No missing player names found',
                })
            }
        } catch (error) {
            setMissingNames([])
            setMessage({ type: 'error', text: `Missing names lookup failed: ${error?.body?.error || error.message}` })
        } finally {
            setMissingNamesBusy(false)
        }
    }, [seedYear, missingNamesTeamDbId, missingNamesTeamApiId, missingNamesLimit])

    const backfillMissingNames = async () => {
        setMissingNamesBusy(true)
        try {
            const payload = buildBackfillNamesPayload({
                season: seedYear,
                teamDbId: missingNamesTeamDbId,
                teamApiId: missingNamesTeamApiId,
                activeOnly: true,
                dryRun: missingNamesDryRun,
                limit: missingNamesLimit,
            })
            const res = await APIService.adminBackfillNames(payload)
            const updated = Number(res?.updated || 0)
            const skipped = Number(res?.skipped || 0)
            const processed = Number(res?.processed || 0)

            setMessage({
                type: 'success',
                text: missingNamesDryRun
                    ? `Dry run: would update ${updated} name${updated === 1 ? '' : 's'} (skipped ${skipped}, processed ${processed})`
                    : `Updated ${updated} name${updated === 1 ? '' : 's'} (skipped ${skipped})`,
            })

            try {
                const refreshParams = buildMissingNamesParams({
                    season: seedYear,
                    teamDbId: missingNamesTeamDbId,
                    teamApiId: missingNamesTeamApiId,
                    activeOnly: true,
                    limit: missingNamesLimit,
                })
                const refreshed = await APIService.adminMissingNames(refreshParams)
                setMissingNames(Array.isArray(refreshed) ? refreshed : [])
            } catch (refreshErr) {
                console.warn('Failed to refresh missing names after backfill', refreshErr)
            }
        } catch (error) {
            setMessage({ type: 'error', text: `Backfill names failed: ${error?.body?.error || error.message}` })
        } finally {
            setMissingNamesBusy(false)
        }
    }

    return (
        <div className="space-y-6">
            <div>
                <h2 className="text-3xl font-bold tracking-tight">Newsletters</h2>
                <p className="text-muted-foreground mt-1">Generate and manage newsletters for tracked teams</p>
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

                {/* Loan Data Seeding */}
                <Card>
                    <CardHeader>
                        <CardTitle>Loan Data Seeding</CardTitle>
                        <CardDescription>Populate loan data before generating newsletters</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <Accordion type="single" collapsible className="w-full">
                            <AccordionItem value="top5">
                                <AccordionTrigger>Seed Top-5 Leagues</AccordionTrigger>
                                <AccordionContent className="space-y-3 pt-3">
                                    <div>
                                        <Label htmlFor="seed-year">Season Year</Label>
                                        <Input
                                            id="seed-year"
                                            type="number"
                                            value={seedYear}
                                            onChange={(e) => setSeedYear(e.target.value)}
                                            placeholder="2024"
                                        />
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <input
                                            type="checkbox"
                                            id="dry-run"
                                            checked={seedTop5DryRun}
                                            onChange={(e) => setSeedTop5DryRun(e.target.checked)}
                                            className="h-4 w-4"
                                        />
                                        <Label htmlFor="dry-run" className="cursor-pointer">
                                            Dry run (preview without saving)
                                        </Label>
                                    </div>
                                    <Button onClick={seedTop5} className="w-full" disabled={seedingTop5 || seedingTeams}>
                                        {seedingTop5 && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                        {seedTop5ButtonLabel({ isSeeding: seedingTop5, dryRun: seedTop5DryRun })}
                                    </Button>
                                </AccordionContent>
                            </AccordionItem>
                            <AccordionItem value="selected">
                                <AccordionTrigger>Seed Selected Teams</AccordionTrigger>
                                <AccordionContent className="space-y-3 pt-3">
                                    <p className="text-sm text-muted-foreground">
                                        Uses teams selected in the generation section above
                                    </p>
                                    <Button onClick={seedSelectedTeams} className="w-full" disabled={seedingTeams || seedingTop5}>
                                        {seedingTeams && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                        {seedSelectedButtonLabel({ isSeeding: seedingTeams, selectionCount: selectedTeams.length })}
                                    </Button>
                                </AccordionContent>
                            </AccordionItem>
                            <AccordionItem value="missing-names">
                                <AccordionTrigger>Backfill Missing Player Names</AccordionTrigger>
                                <AccordionContent className="space-y-4 pt-3">
                                    <p className="text-sm text-muted-foreground">
                                        Find loans that still show placeholder names from API-Football and fill them using the season year below.
                                    </p>
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                        <div className="space-y-1">
                                            <Label htmlFor="missing-names-season">Season Year</Label>
                                            <Input
                                                id="missing-names-season"
                                                type="number"
                                                value={seedYear}
                                                onChange={(e) => setSeedYear(e.target.value)}
                                                placeholder="2024"
                                            />
                                        </div>
                                        <div className="space-y-1">
                                            <Label htmlFor="missing-names-limit">Max Rows (optional)</Label>
                                            <Input
                                                id="missing-names-limit"
                                                type="number"
                                                min="1"
                                                value={missingNamesLimit}
                                                onChange={(e) => setMissingNamesLimit(e.target.value)}
                                                placeholder="200"
                                            />
                                        </div>
                                    </div>

                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                        <div className="space-y-1">
                                            <Label>Parent Team (optional)</Label>
                                            <TeamSelect
                                                teams={teams}
                                                value={missingNamesTeamDbId}
                                                onChange={(id) => setMissingNamesTeamDbId(id || null)}
                                                placeholder="Select team..."
                                            />
                                        </div>
                                        <div className="space-y-1">
                                            <Label htmlFor="missing-names-team-api">Team API ID (optional)</Label>
                                            <Input
                                                id="missing-names-team-api"
                                                type="number"
                                                value={missingNamesTeamApiId}
                                                onChange={(e) => setMissingNamesTeamApiId(e.target.value)}
                                                placeholder="Use if team is missing from DB"
                                            />
                                            <p className="text-xs text-muted-foreground">Requires season year when using API id.</p>
                                        </div>
                                    </div>

                                    <div className="flex items-center gap-2">
                                        <input
                                            type="checkbox"
                                            id="missing-names-dry-run"
                                            checked={missingNamesDryRun}
                                            onChange={(e) => setMissingNamesDryRun(e.target.checked)}
                                            className="h-4 w-4"
                                        />
                                        <Label htmlFor="missing-names-dry-run" className="cursor-pointer">Dry run (preview without saving)</Label>
                                    </div>

                                    <div className="flex flex-col md:flex-row gap-2">
                                        <Button
                                            onClick={() => loadMissingNames()}
                                            variant="outline"
                                            className="flex-1"
                                            disabled={missingNamesBusy}
                                        >
                                            {missingNamesBusy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                            Find Missing Names
                                        </Button>
                                        <Button
                                            onClick={backfillMissingNames}
                                            className="flex-1"
                                            disabled={missingNamesBusy}
                                        >
                                            {missingNamesBusy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                            {missingNamesDryRun ? 'Preview Backfill' : 'Backfill Names'}
                                        </Button>
                                    </div>

                                    {missingNames.length > 0 && (
                                        <div className="rounded-md border">
                                            <div className="flex items-center justify-between bg-muted px-3 py-2 text-sm font-medium">
                                                <span>Found {missingNames.length} loan{missingNames.length === 1 ? '' : 's'} with placeholder names</span>
                                                <Badge variant="secondary">Season {seedYear || 'n/a'}</Badge>
                                            </div>
                                            <div className="max-h-64 overflow-auto">
                                                <table className="w-full text-sm">
                                                    <thead className="bg-muted/60 sticky top-0">
                                                        <tr className="text-left">
                                                            <th className="px-3 py-2">Loan ID</th>
                                                            <th className="px-3 py-2">Player ID</th>
                                                            <th className="px-3 py-2">Name</th>
                                                            <th className="px-3 py-2">Parent Team</th>
                                                            <th className="px-3 py-2">Loan Team</th>
                                                            <th className="px-3 py-2">Window</th>
                                                        </tr>
                                                    </thead>
                                                    <tbody>
                                                        {missingNames.map((row) => (
                                                            <tr key={row.id} className="border-t">
                                                                <td className="px-3 py-2 whitespace-nowrap text-muted-foreground">{row.id}</td>
                                                                <td className="px-3 py-2 whitespace-nowrap">{row.player_id}</td>
                                                                <td className="px-3 py-2 text-muted-foreground italic">{row.player_name || '(empty)'}</td>
                                                                <td className="px-3 py-2 whitespace-nowrap">{row.primary_team_name}</td>
                                                                <td className="px-3 py-2 whitespace-nowrap">{row.loan_team_name}</td>
                                                                <td className="px-3 py-2 whitespace-nowrap">{row.window_key}</td>
                                                            </tr>
                                                        ))}
                                                    </tbody>
                                                </table>
                                            </div>
                                        </div>
                                    )}
                                </AccordionContent>
                            </AccordionItem>
                        </Accordion>
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
                                                    <td className="p-2 text-muted-foreground">#{newsletter.id}</td>
                                                    <td className="p-2 font-medium">{newsletter.team_name || 'Unknown'}</td>
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
        </div>
    )
}
