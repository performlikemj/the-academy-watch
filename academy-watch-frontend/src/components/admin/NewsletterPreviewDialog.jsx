import { useState, useEffect } from 'react'
import { APIService } from '@/lib/api'
import { buildAdminPreviewSendOptions } from '@/lib/newsletter-admin'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Loader2, RefreshCw, Monitor, Mail, ExternalLink, Send } from 'lucide-react'
import { ScrollArea } from '@/components/ui/scroll-area'

export function NewsletterPreviewDialog({ open, onOpenChange, newsletter, onStatus }) {
    const [loading, setLoading] = useState(false)
    const [journalists, setJournalists] = useState([])
    const [selectedJournalists, setSelectedJournalists] = useState([])
    const [renderMode, setRenderMode] = useState('web') // 'web' | 'email'
    const [useSnippets, setUseSnippets] = useState(true) // Default to snippets for email
    const [htmlContent, setHtmlContent] = useState('')
    const [simulateSubscription, setSimulateSubscription] = useState(false)
    const [sendingAdminPreview, setSendingAdminPreview] = useState(false)
    const [sendStatus, setSendStatus] = useState(null)

    // Load journalists for the team
    useEffect(() => {
        if (newsletter?.team_id) {
            loadJournalists()
        } else {
            setJournalists([])
            setSelectedJournalists([])
        }
    }, [newsletter])

    // Reset simulation state when opening new newsletter
    useEffect(() => {
        if (open) {
            setSimulateSubscription(false)
            setSelectedJournalists([])
            setRenderMode('web')
            setSendStatus(null)
            // Initial load (admin view - all content)
            loadPreview({ simulate: false })
        }
    }, [open, newsletter])

    const loadJournalists = async () => {
        try {
            // We need to fetch journalists assigned to this team.
            // Currently using the general journalists list and filtering client-side 
            // if the endpoint returns assignments.
            const allJournalists = await APIService.request('/journalists', { method: 'GET' })

            // Get the current newsletter's team info to find its API Team ID
            const currentTeam = await APIService.request(`/teams/${newsletter.team_id}`, { method: 'GET' })
            const apiTeamId = currentTeam.team_id // The API ID (e.g., 33 for Man Utd)

            // Filter for those assigned to this team (by API Team ID, not DB ID)
            // This ensures cross-season compatibility: if a journalist was assigned to
            // "2024 Man Utd" (team_id=33), they'll still show for "2025 Man Utd" (also team_id=33)
            const assigned = allJournalists.filter(j =>
                j.assigned_teams?.some(t => t.team_id === apiTeamId)
            )
            setJournalists(assigned)
        } catch (error) {
            console.error('Failed to load journalists', error)
        }
    }

    const loadPreview = async (overrides = {}) => {
        if (!newsletter) return

        setLoading(true)
        try {
            const isSimulating = overrides.simulate !== undefined ? overrides.simulate : simulateSubscription
            const mode = overrides.renderMode || renderMode
            const snippets = overrides.useSnippets !== undefined ? overrides.useSnippets : useSnippets
            const selected = overrides.selectedIds || selectedJournalists

            const payload = {
                render_mode: mode,
                use_snippets: mode === 'email' && snippets,
                // If simulating, pass selected IDs. If not, pass None (which backend treats as "all")
                journalist_ids: isSimulating ? selected : null
            }

            const res = await APIService.request(`/newsletters/${newsletter.id}/preview`, {
                method: 'POST',
                body: JSON.stringify(payload)
            }, { admin: true })

            setHtmlContent(res.html || '')
        } catch (error) {
            console.error('Preview generation failed', error)
            setHtmlContent('<div style="color:red;padding:20px;">Failed to generate preview.</div>')
        } finally {
            setLoading(false)
        }
    }

    const handleRefresh = () => {
        loadPreview()
    }

    const toggleJournalist = (id) => {
        const newSelected = selectedJournalists.includes(id)
            ? selectedJournalists.filter(jid => jid !== id)
            : [...selectedJournalists, id]
        setSelectedJournalists(newSelected)
        // Auto-refresh if in simulation mode? Or explicit refresh?
        // Let's wait for explicit refresh or handle it in useEffect if we want instant feedback.
        // Instant is better UX.
        if (simulateSubscription) {
            loadPreview({ selectedIds: newSelected })
        }
    }

    const toggleSimulation = (enabled) => {
        setSimulateSubscription(enabled)
        // If enabling, start with no journalists (or all? usually none is safer base)
        // If disabling, go back to "all" (null)
        loadPreview({ simulate: enabled })
    }

    const openInNewTab = () => {
        const newWindow = window.open('', '_blank')
        if (newWindow) {
            newWindow.document.write(htmlContent)
            newWindow.document.close()
            newWindow.document.title = `Preview - ${newsletter?.team_name}`
        }
    }

    const sendAdminPreview = async () => {
        if (!newsletter?.id) return
        setSendingAdminPreview(true)
        setSendStatus(null)
        try {
            const payload = buildAdminPreviewSendOptions({
                renderMode,
                useSnippets,
                simulateSubscription,
                selectedJournalists,
            })
            await APIService.adminNewsletterSendPreview(newsletter.id, payload)

            const simulatedCount = Array.isArray(payload.journalist_ids) ? payload.journalist_ids.length : 0
            const suffix = simulatedCount
                ? ` (simulating ${simulatedCount} journalist${simulatedCount === 1 ? '' : 's'})`
                : ''
            const text = `Sent admin preview for newsletter #${newsletter.id}${suffix}.`

            setSendStatus({ type: 'success', text })
            onStatus?.({ type: 'success', text })
        } catch (error) {
            const text = error?.body?.message || error?.message || 'Failed to send admin preview.'
            setSendStatus({ type: 'error', text })
            onStatus?.({ type: 'error', text })
        } finally {
            setSendingAdminPreview(false)
        }
    }

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-7xl h-[90vh] flex flex-col p-0 gap-0">
                <DialogHeader className="px-6 py-4 border-b flex flex-row items-center justify-between space-y-0">
                    <DialogTitle className="flex items-center gap-2">
                        <span>Newsletter Preview</span>
                        <span className="font-normal text-muted-foreground text-sm">
                            — {newsletter?.team_name} (#{newsletter?.id})
                        </span>
                    </DialogTitle>
                    <Button
                        variant="ghost"
                        size="sm"
                        className="gap-2"
                        onClick={openInNewTab}
                    >
                        <ExternalLink className="h-4 w-4" />
                        Open in New Tab
                    </Button>
                </DialogHeader>

                <div className="flex flex-1 overflow-hidden">
                    {/* Left Sidebar: Controls */}
                    <div className="w-80 border-r bg-muted/30 flex flex-col overflow-hidden">
                        <ScrollArea className="flex-1">
                            <div className="p-4 space-y-6">
                                {/* View Mode */}
                                <div className="space-y-3">
                                    <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">View Mode</Label>
                                    <div className="bg-background p-1 rounded-lg border flex">
                                        <Button
                                            variant={renderMode === 'web' ? 'secondary' : 'ghost'}
                                            size="sm"
                                            className="flex-1 gap-2"
                                            onClick={() => {
                                                setRenderMode('web')
                                                loadPreview({ renderMode: 'web' })
                                            }}
                                        >
                                            <Monitor className="h-4 w-4" />
                                            Web
                                        </Button>
                                        <Button
                                            variant={renderMode === 'email' ? 'secondary' : 'ghost'}
                                            size="sm"
                                            className="flex-1 gap-2"
                                            onClick={() => {
                                                setRenderMode('email')
                                                loadPreview({ renderMode: 'email' })
                                            }}
                                        >
                                            <Mail className="h-4 w-4" />
                                            Email
                                        </Button>
                                    </div>
                                </div>

                                {/* Simulation Toggle */}
                                <div className="space-y-3">
                                    <div className="flex items-center justify-between">
                                        <Label htmlFor="sim-mode" className="font-medium">Simulate Subscriber</Label>
                                        <Switch
                                            id="sim-mode"
                                            checked={simulateSubscription}
                                            onCheckedChange={toggleSimulation}
                                        />
                                    </div>
                                    <p className="text-xs text-muted-foreground">
                                        Enable to preview what a specific user would see based on their journalist subscriptions.
                                    </p>
                                </div>

                                {/* Journalist Selection */}
                                {simulateSubscription && (
                                    <div className="space-y-3 animate-in slide-in-from-top-2 fade-in duration-200">
                                        <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                                            Journalist Subscriptions
                                        </Label>
                                        {journalists.length === 0 ? (
                                            <p className="text-sm text-muted-foreground italic">No journalists assigned to this team.</p>
                                        ) : (
                                            <div className="space-y-2">
                                                {journalists.map(j => (
                                                    <div key={j.id} className="flex items-center space-x-2">
                                                        <Checkbox
                                                            id={`j-${j.id}`}
                                                            checked={selectedJournalists.includes(j.id)}
                                                            onCheckedChange={() => toggleJournalist(j.id)}
                                                        />
                                                        <label
                                                            htmlFor={`j-${j.id}`}
                                                            className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70 cursor-pointer"
                                                        >
                                                            {j.display_name}
                                                        </label>
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                )}

                                {/* Email Options */}
                                {renderMode === 'email' && (
                                    <div className="space-y-3 pt-4 border-t">
                                        <div className="flex items-center justify-between">
                                            <Label htmlFor="use-snippets" className="font-medium">Use Snippets</Label>
                                            <Switch
                                                id="use-snippets"
                                                checked={useSnippets}
                                                onCheckedChange={(v) => {
                                                    setUseSnippets(v)
                                                    loadPreview({ useSnippets: v })
                                                }}
                                            />
                                        </div>
                                        <p className="text-xs text-muted-foreground">
                                            Collapse full articles into "Headlines" with read-more links.
                                        </p>
                                    </div>
                                )}
                            </div>
                        </ScrollArea>
                        <div className="p-4 border-t bg-background space-y-2" aria-live="polite">
                            {sendStatus && (
                                <div className={`text-sm ${sendStatus.type === 'error' ? 'text-rose-600' : 'text-emerald-700'}`}>
                                    {sendStatus.text}
                                </div>
                            )}
                            <div className="flex flex-col gap-2">
                                <Button
                                    onClick={sendAdminPreview}
                                    className="w-full"
                                    disabled={loading || sendingAdminPreview}
                                >
                                    {sendingAdminPreview ? (
                                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                    ) : (
                                        <Send className="mr-2 h-4 w-4" />
                                    )}
                                    Send to Admins for Review
                                </Button>
                                <Button onClick={handleRefresh} className="w-full" variant="outline" disabled={loading}>
                                    {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
                                    Refresh Preview
                                </Button>
                            </div>
                        </div>
                    </div>

                    {/* Right Panel: Preview */}
                    <div className="flex-1 bg-secondary/50 relative overflow-hidden">
                        {loading && (
                            <div className="absolute inset-0 bg-background/50 backdrop-blur-sm flex items-center justify-center z-10">
                                <Loader2 className="h-8 w-8 animate-spin text-primary" />
                            </div>
                        )}
                        <iframe
                            srcDoc={htmlContent}
                            title="Newsletter Preview"
                            className="w-full h-full border-none"
                            sandbox="allow-same-origin allow-scripts"
                        />
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    )
}
