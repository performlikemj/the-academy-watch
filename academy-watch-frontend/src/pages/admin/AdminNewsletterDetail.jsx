import { useState, useEffect, useMemo, useCallback } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { APIService } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Skeleton } from '@/components/ui/skeleton'
import { ConfirmGate } from '@/components/admin/ConfirmGate'
import { CommentaryManager } from '@/components/CommentaryManager.jsx'
import { buildSofascoreEmbedUrl } from '@/lib/sofascore.js'
import { ArrowLeft, Copy, Send } from 'lucide-react'

// Pull the player list out of newsletter content (for YouTube link + commentary pickers)
function extractPlayersFromNewsletter(newsletter) {
    if (!newsletter) return []
    try {
        const content = typeof newsletter.content === 'string' ? JSON.parse(newsletter.content) : newsletter.content
        const enrichedContent = newsletter.enriched_content || content
        const players = []
        const sections = enrichedContent?.sections || []
        for (const section of sections) {
            const items = section?.items || []
            for (const item of items) {
                if (item.player_name) {
                    players.push({
                        player_name: item.player_name,
                        player_id: item.player_id || null,
                        loan_team: item.loan_team || item.loan_team_name || '',
                    })
                }
            }
        }
        return players
    } catch {
        return []
    }
}

function describeSendOutcome(result) {
    if (!result || typeof result !== 'object') return 'Send request completed.'
    const parts = []
    if (result.status) parts.push(`status: ${result.status}`)
    if (typeof result.recipient_count === 'number') parts.push(`recipients: ${result.recipient_count}`)
    if (typeof result.delivered_count === 'number') parts.push(`delivered: ${result.delivered_count}`)
    if (result.dry_run) parts.push('dry run — nothing was actually sent')
    return parts.length ? parts.join(' · ') : 'Send request completed.'
}

// Structured fallback body shown when the server-side HTML render is unavailable.
// Receives pre-normalized data (see fallbackData below) — no parsing happens here.
function NewsletterFallbackBody({ data }) {
    return (
        <div className="space-y-6">
            <div className="bg-gradient-to-r from-secondary to-background p-6 rounded-lg border-l-4 border-primary/20">
                <h2 className="text-2xl font-bold text-foreground mb-3">{data.title}</h2>
                {data.range && (
                    <div className="text-sm text-muted-foreground mb-3">
                        Week: {data.range[0]} - {data.range[1]}
                    </div>
                )}
                {data.summary && (
                    <div className="text-foreground/80 leading-relaxed text-lg">
                        {data.summary}
                    </div>
                )}
            </div>

            {data.highlights.length > 0 && (
                <div className="bg-amber-50 p-5 rounded-lg border-l-4 border-amber-400">
                    <h3 className="text-lg font-bold text-foreground mb-3">Key Highlights</h3>
                    <ul className="space-y-2">
                        {data.highlights.map((highlight, idx) => (
                            <li key={idx} className="flex items-start">
                                <span className="bg-amber-400 text-amber-900 rounded-full w-6 h-6 flex items-center justify-center text-xs font-bold mr-3 mt-0.5 flex-shrink-0">
                                    {idx + 1}
                                </span>
                                <span className="text-foreground/80">{highlight}</span>
                            </li>
                        ))}
                    </ul>
                </div>
            )}

            {data.sections.map((section, index) => {
                const items = Array.isArray(section?.items) ? section.items : []
                if (!items.length) return null
                return (
                    <div key={index} className="space-y-4">
                        {section?.title && (
                            <div className="border-b pb-2">
                                <h3 className="text-xl font-semibold text-foreground">{section.title}</h3>
                                {section?.subtitle && (
                                    <p className="text-sm text-muted-foreground">{section.subtitle}</p>
                                )}
                            </div>
                        )}
                        <div className="space-y-4">
                            {items.map((item, itemIdx) => (
                                <div key={itemIdx} className="border rounded-lg p-4 bg-card shadow-sm">
                                    <div className="flex items-start gap-3">
                                        {item.player_photo && (
                                            <img
                                                src={item.player_photo}
                                                alt={item.player_name}
                                                className="w-14 h-14 rounded-full object-cover bg-secondary flex-shrink-0 border-2 border-white shadow-sm"
                                            />
                                        )}
                                        <div className="flex-1">
                                            <div className="flex flex-wrap items-start justify-between gap-3">
                                                <div>
                                                    {(item.player_api_id || item.player_id) ? (
                                                        <Link
                                                            to={`/players/${item.player_api_id || item.player_id}`}
                                                            className="text-lg font-semibold text-foreground hover:text-primary hover:underline transition-colors"
                                                        >
                                                            {item.player_name}
                                                        </Link>
                                                    ) : (
                                                        <div className="text-lg font-semibold text-foreground">{item.player_name}</div>
                                                    )}
                                                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                                        {item.loan_team_logo && (
                                                            <img
                                                                src={item.loan_team_logo}
                                                                alt={item.loan_team || item.loan_team_name}
                                                                className="w-5 h-5 rounded-full object-cover bg-secondary"
                                                            />
                                                        )}
                                                        <span>{item.loan_team || item.loan_team_name}</span>
                                                    </div>
                                                </div>
                                                <div className="text-sm text-muted-foreground">
                                                    {item.competition || item.match_name}
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                    {item.week_summary && (
                                        <p className="mt-3 text-foreground/80 leading-relaxed">{item.week_summary}</p>
                                    )}
                                    {item.matches && Array.isArray(item.matches) && item.matches.length > 0 && (
                                        <div className="mt-3 p-3 bg-secondary rounded-lg border border-border">
                                            <h5 className="text-sm font-semibold text-foreground/80 mb-2">This Week's Matches</h5>
                                            <div className="space-y-2">
                                                {item.matches.map((match, mIdx) => (
                                                    <div key={mIdx} className="flex items-center gap-3 p-2 bg-card rounded border border-border">
                                                        {match.opponent_logo && (
                                                            <img
                                                                src={match.opponent_logo}
                                                                alt={match.opponent}
                                                                className="w-7 h-7 rounded-full object-cover bg-secondary flex-shrink-0"
                                                            />
                                                        )}
                                                        <div className="flex-1">
                                                            <span className="font-medium text-sm">{match.home ? 'vs' : '@'} {match.opponent}</span>
                                                            {match.competition && <span className="text-xs text-muted-foreground ml-2">({match.competition})</span>}
                                                        </div>
                                                        {match.score && (
                                                            <span className={`px-2 py-1 rounded text-xs font-bold ${match.result === 'W' ? 'bg-emerald-50 text-emerald-800' :
                                                                match.result === 'D' ? 'bg-secondary text-foreground/80' :
                                                                    'bg-rose-50 text-rose-800'
                                                                }`}>
                                                                {match.score.home ?? 0}-{match.score.away ?? 0}
                                                            </span>
                                                        )}
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    )}
                                    {item.match_notes && Array.isArray(item.match_notes) && item.match_notes.length > 0 && !item.matches && (
                                        <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                                            {item.match_notes.map((note, noteIndex) => (
                                                <li key={noteIndex}>{note}</li>
                                            ))}
                                        </ul>
                                    )}
                                    <SofascoreEmbed item={item} />
                                </div>
                            ))}
                        </div>
                    </div>
                )
            })}
        </div>
    )
}

function SofascoreEmbed({ item }) {
    const embedUrl = buildSofascoreEmbedUrl(item.sofascore_player_id ?? item.sofascoreId)
    if (!embedUrl) return null
    return (
        <div className="mt-4">
            <iframe
                title={`Sofascore profile for ${item.player_name || item.player_id}`}
                src={embedUrl}
                frameBorder="0"
                scrolling="no"
                className="h-[568px] w-full max-w-xs rounded-md border"
            />
            <p className="mt-2 text-xs text-muted-foreground">
                Player stats provided by{' '}
                <a
                    href="https://sofascore.com/"
                    className="text-primary hover:underline"
                    target="_blank"
                    rel="noopener"
                >
                    Sofascore
                </a>
            </p>
        </div>
    )
}

export function AdminNewsletterDetail() {
    const { newsletterId } = useParams()
    const navigate = useNavigate()
    const [loading, setLoading] = useState(true)
    const [newsletter, setNewsletter] = useState(null)
    const [error, setError] = useState('')
    const [renderHtml, setRenderHtml] = useState('')
    const [htmlError, setHtmlError] = useState('')
    const [copyLabel, setCopyLabel] = useState('Copy ID')

    // Send controls
    const [testTo, setTestTo] = useState('__admins__')
    const [dryRun, setDryRun] = useState(true)
    const [sending, setSending] = useState(false)
    const [sendNotice, setSendNotice] = useState(null) // { type: 'success'|'error', text }
    const [confirmSendOpen, setConfirmSendOpen] = useState(false)

    // YouTube links
    const [youtubeLinks, setYoutubeLinks] = useState([])
    const [youtubeForm, setYoutubeForm] = useState({ player_name: '', youtube_link: '', player_id: null })
    const [editingYoutubeLink, setEditingYoutubeLink] = useState(null)
    const [youtubeNotice, setYoutubeNotice] = useState(null)

    const players = useMemo(() => extractPlayersFromNewsletter(newsletter), [newsletter])

    const loadYoutubeLinks = useCallback(async (id) => {
        try {
            const links = await APIService.adminNewsletterYoutubeLinksList(id)
            setYoutubeLinks(Array.isArray(links) ? links : [])
        } catch {
            setYoutubeLinks([])
        }
    }, [])

    useEffect(() => {
        let cancelled = false
        const load = async () => {
            const trimmedId = (newsletterId || '').trim()
            if (!trimmedId) {
                setError('Newsletter id is required')
                setLoading(false)
                return
            }

            setLoading(true)
            setError('')
            setHtmlError('')
            try {
                const data = await APIService.adminNewsletterGet(trimmedId)
                if (cancelled) return
                setNewsletter(data)
                loadYoutubeLinks(trimmedId)
                try {
                    const html = await APIService.adminNewsletterRender(trimmedId, 'web')
                    if (!cancelled) {
                        setRenderHtml(html)
                    }
                } catch (renderErr) {
                    if (!cancelled) {
                        setHtmlError(renderErr?.message || 'Unable to load rendered preview')
                    }
                }
            } catch (err) {
                if (!cancelled) {
                    setError(err?.message || 'Failed to load newsletter')
                }
            } finally {
                if (!cancelled) {
                    setLoading(false)
                }
            }
        }

        load()
        return () => {
            cancelled = true
        }
    }, [newsletterId, loadYoutubeLinks])

    const newsletterDbId = newsletter?.id

    const handleCopyId = useCallback(() => {
        if (!newsletterDbId) return
        const idStr = String(newsletterDbId)
        if (navigator?.clipboard?.writeText) {
            navigator.clipboard.writeText(idStr)
                .then(() => {
                    setCopyLabel('Copied!')
                    setTimeout(() => setCopyLabel('Copy ID'), 2000)
                })
                .catch(() => setCopyLabel('Copy ID'))
        }
    }, [newsletterDbId])

    const handleOpenPreview = useCallback(() => {
        if (!renderHtml) return
        const blob = new Blob([renderHtml], { type: 'text/html' })
        const url = URL.createObjectURL(blob)
        window.open(url, '_blank', 'noopener')
        setTimeout(() => URL.revokeObjectURL(url), 60_000)
    }, [renderHtml])

    const handleTestSend = useCallback(async () => {
        if (!newsletterDbId) return
        const recipient = (testTo || '').trim()
        if (!recipient) {
            setSendNotice({ type: 'error', text: 'Enter a test recipient (email or __admins__).' })
            return
        }
        setSending(true)
        setSendNotice(null)
        try {
            const result = await APIService.adminNewsletterSend(newsletterDbId, { testTo: recipient, dryRun })
            setSendNotice({ type: 'success', text: `Test send → ${describeSendOutcome(result)}` })
        } catch (err) {
            setSendNotice({ type: 'error', text: err?.message || 'Test send failed' })
        } finally {
            setSending(false)
        }
    }, [newsletterDbId, testTo, dryRun])

    const handleRealSend = useCallback(async () => {
        if (!newsletterDbId) return
        setSending(true)
        setSendNotice(null)
        try {
            const result = await APIService.adminNewsletterSend(newsletterDbId, { dryRun: false })
            setSendNotice({ type: 'success', text: `Live send → ${describeSendOutcome(result)}` })
            try {
                const refreshed = await APIService.adminNewsletterGet(newsletterDbId)
                setNewsletter(refreshed)
            } catch {
                /* keep stale copy if refresh fails */
            }
        } catch (err) {
            setSendNotice({ type: 'error', text: err?.message || 'Send failed' })
        } finally {
            setSending(false)
        }
    }, [newsletterDbId])

    const handleYoutubeCreate = useCallback(async () => {
        if (!newsletterDbId) return
        if (!youtubeForm.player_name || !youtubeForm.youtube_link) {
            setYoutubeNotice({ type: 'error', text: 'Player and YouTube link are required' })
            return
        }
        try {
            await APIService.adminNewsletterYoutubeLinkCreate(newsletterDbId, {
                player_name: youtubeForm.player_name,
                youtube_link: youtubeForm.youtube_link,
                player_id: youtubeForm.player_id,
            })
            setYoutubeNotice({ type: 'success', text: 'YouTube link added' })
            setYoutubeForm({ player_name: '', youtube_link: '', player_id: null })
            await loadYoutubeLinks(newsletterDbId)
        } catch (err) {
            setYoutubeNotice({ type: 'error', text: `Failed to add YouTube link: ${err?.body?.error || err?.message}` })
        }
    }, [newsletterDbId, youtubeForm, loadYoutubeLinks])

    const handleYoutubeUpdate = useCallback(async (linkId) => {
        if (!newsletterDbId || !editingYoutubeLink?.youtube_link) {
            setYoutubeNotice({ type: 'error', text: 'YouTube link is required' })
            return
        }
        try {
            await APIService.adminNewsletterYoutubeLinkUpdate(newsletterDbId, linkId, {
                youtube_link: editingYoutubeLink.youtube_link,
            })
            setYoutubeNotice({ type: 'success', text: 'YouTube link updated' })
            setEditingYoutubeLink(null)
            await loadYoutubeLinks(newsletterDbId)
        } catch (err) {
            setYoutubeNotice({ type: 'error', text: `Failed to update YouTube link: ${err?.body?.error || err?.message}` })
        }
    }, [newsletterDbId, editingYoutubeLink, loadYoutubeLinks])

    const handleYoutubeDelete = useCallback(async (linkId) => {
        if (!newsletterDbId) return
        try {
            await APIService.adminNewsletterYoutubeLinkDelete(newsletterDbId, linkId)
            setYoutubeNotice({ type: 'success', text: 'YouTube link deleted' })
            await loadYoutubeLinks(newsletterDbId)
        } catch (err) {
            setYoutubeNotice({ type: 'error', text: `Failed to delete YouTube link: ${err?.body?.error || err?.message}` })
        }
    }, [newsletterDbId, loadYoutubeLinks])

    // Normalized content for the fallback body — parsing stays out of the JSX.
    const fallbackData = useMemo(() => {
        let obj = null
        if (newsletter?.enriched_content && typeof newsletter.enriched_content === 'object') {
            obj = newsletter.enriched_content
        } else if (newsletter?.content) {
            try {
                obj = typeof newsletter.content === 'string' ? JSON.parse(newsletter.content) : (newsletter.content || {})
            } catch {
                obj = null
            }
        }

        if (!obj || typeof obj !== 'object') {
            return null
        }

        return {
            title: obj.title || newsletter?.title || '',
            range: Array.isArray(obj.range) && obj.range.length >= 2 ? obj.range : null,
            summary: typeof obj.summary === 'string' ? obj.summary : '',
            highlights: Array.isArray(obj.highlights) ? obj.highlights : [],
            sections: Array.isArray(obj.sections) ? obj.sections : [],
        }
    }, [newsletter])

    const metaEntries = useMemo(() => {
        if (!newsletter) return []
        const items = []
        items.push({ label: 'Newsletter ID', value: newsletter.id })
        if (newsletter.team_name) items.push({ label: 'Team', value: newsletter.team_name })
        if (newsletter.week_start_date || newsletter.week_end_date) {
            const range = [newsletter.week_start_date, newsletter.week_end_date].filter(Boolean).join(' → ')
            items.push({ label: 'Week', value: range })
        }
        if (newsletter.issue_date) items.push({ label: 'Issue Date', value: newsletter.issue_date })
        if (newsletter.published_date) items.push({ label: 'Published', value: newsletter.published_date })
        if (newsletter.generated_date) items.push({ label: 'Generated', value: newsletter.generated_date })
        if (newsletter.email_sent_date) items.push({ label: 'Email Sent', value: newsletter.email_sent_date })
        if (typeof newsletter.subscriber_count === 'number') {
            items.push({ label: 'Subscriber Count', value: newsletter.subscriber_count })
        }
        return items
    }, [newsletter])

    const liveSendBlocked = !newsletter?.published || !!newsletter?.email_sent
    const liveSendBlockReason = !newsletter?.published
        ? 'Newsletter must be published before a live send.'
        : newsletter?.email_sent
            ? 'This newsletter has already been sent.'
            : ''

    if (loading) {
        return (
            <div className="space-y-6">
                <Skeleton className="h-9 w-40" />
                <Skeleton className="h-44 w-full" />
                <Skeleton className="h-64 w-full" />
            </div>
        )
    }

    if (error) {
        return (
            <div className="space-y-6">
                <Card>
                    <CardHeader>
                        <CardTitle className="text-lg text-rose-600">Unable to load newsletter</CardTitle>
                        <CardDescription>{error}</CardDescription>
                    </CardHeader>
                    <CardFooter>
                        <Button variant="outline" onClick={() => navigate('/admin/newsletters')} data-testid="newsletter-detail-back-error">
                            Return to newsletters
                        </Button>
                    </CardFooter>
                </Card>
            </div>
        )
    }

    return (
        <div className="space-y-6">
            <header className="flex flex-wrap items-start justify-between gap-3">
                <div>
                    <h2 className="text-3xl font-bold tracking-tight">{newsletter?.title || 'Newsletter detail'}</h2>
                    <p className="text-muted-foreground mt-1">
                        Review the generated newsletter, manage video links and commentary, then send.
                    </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={newsletter?.published ? 'default' : 'secondary'}>
                        {newsletter?.published ? 'Published' : 'Draft'}
                    </Badge>
                    {newsletter?.email_sent && (
                        <Badge variant="outline" className="border-emerald-200 text-emerald-700">
                            Email sent
                        </Badge>
                    )}
                    <Button size="sm" variant="outline" onClick={handleCopyId} data-testid="newsletter-detail-copy-id">
                        <Copy className="mr-2 h-4 w-4" />
                        {copyLabel}
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => navigate('/admin/newsletters')} data-testid="newsletter-detail-back">
                        <ArrowLeft className="mr-2 h-4 w-4" />
                        All newsletters
                    </Button>
                </div>
            </header>

            <Card>
                <CardHeader>
                    <CardTitle>Metadata</CardTitle>
                </CardHeader>
                <CardContent>
                    {metaEntries.length > 0 ? (
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                            {metaEntries.map((item) => (
                                <div key={item.label} className="flex flex-col rounded border bg-secondary p-3">
                                    <span className="text-xs uppercase tracking-wide text-muted-foreground">{item.label}</span>
                                    <span className="text-foreground font-medium break-words">{item.value || '—'}</span>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <p className="text-sm text-muted-foreground">No metadata available.</p>
                    )}
                </CardContent>
            </Card>

            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Send className="h-4 w-4" />
                        Send
                    </CardTitle>
                    <CardDescription>
                        Test sends go to a specific address (or all admins with <span className="font-mono">__admins__</span>) and
                        never mark the newsletter as sent. Live sends go to every active subscriber.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="flex flex-wrap items-end gap-3">
                        <div className="space-y-1">
                            <Label htmlFor="newsletter-test-to" className="text-xs">Test recipient</Label>
                            <Input
                                id="newsletter-test-to"
                                data-testid="newsletter-send-testto"
                                value={testTo}
                                onChange={(e) => setTestTo(e.target.value)}
                                placeholder="email@example.com or __admins__"
                                className="w-72"
                            />
                        </div>
                        <label className="flex items-center gap-2 text-sm cursor-pointer pb-2">
                            <input
                                type="checkbox"
                                data-testid="newsletter-send-dryrun"
                                checked={dryRun}
                                onChange={(e) => setDryRun(e.target.checked)}
                                className="rounded border-border"
                            />
                            Dry run (no email is delivered)
                        </label>
                        <Button
                            size="sm"
                            onClick={handleTestSend}
                            disabled={sending}
                            data-testid="newsletter-send-test"
                        >
                            {sending ? 'Sending…' : 'Send test'}
                        </Button>
                        <Button
                            size="sm"
                            variant="destructive"
                            onClick={() => setConfirmSendOpen(true)}
                            disabled={sending || liveSendBlocked}
                            data-testid="newsletter-send-live"
                        >
                            Send to subscribers
                        </Button>
                    </div>
                    {liveSendBlocked && liveSendBlockReason && (
                        <p className="text-xs text-muted-foreground">{liveSendBlockReason}</p>
                    )}
                    {sendNotice && (
                        <Alert variant={sendNotice.type === 'error' ? 'destructive' : 'default'}>
                            <AlertDescription>{sendNotice.text}</AlertDescription>
                        </Alert>
                    )}
                </CardContent>
            </Card>

            <ConfirmGate
                open={confirmSendOpen}
                onOpenChange={setConfirmSendOpen}
                title="Send newsletter to all subscribers"
                description={`This emails "${newsletter?.title || 'this newsletter'}" to every active subscriber and marks it as sent. This cannot be undone.`}
                confirmWord="SEND"
                confirmLabel="Send it"
                destructive
                onConfirm={handleRealSend}
            />

            <Card>
                <CardHeader>
                    <CardTitle>Web preview</CardTitle>
                    {htmlError && (
                        <CardDescription className="text-rose-600">{htmlError}</CardDescription>
                    )}
                </CardHeader>
                <CardContent className="space-y-4">
                    <Button size="sm" disabled={!renderHtml} onClick={handleOpenPreview} data-testid="newsletter-detail-open-preview">
                        Open web preview in new tab
                    </Button>
                    <div className="rounded-lg border bg-card p-6">
                        {renderHtml ? (
                            <div dangerouslySetInnerHTML={{ __html: renderHtml }} className="prose max-w-none" />
                        ) : fallbackData ? (
                            <NewsletterFallbackBody data={fallbackData} />
                        ) : (
                            <div className="text-sm text-muted-foreground">No content available for this newsletter.</div>
                        )}
                    </div>
                </CardContent>
            </Card>

            <Card>
                <CardHeader>
                    <CardTitle>YouTube links</CardTitle>
                    <CardDescription>Attach highlight links to players featured in this newsletter.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    {youtubeNotice && (
                        <Alert variant={youtubeNotice.type === 'error' ? 'destructive' : 'default'}>
                            <AlertDescription>{youtubeNotice.text}</AlertDescription>
                        </Alert>
                    )}
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                        <select
                            className="h-9 rounded-md border border-input bg-background px-3 text-sm"
                            data-testid="youtube-link-player"
                            value={youtubeForm.player_name}
                            onChange={(e) => {
                                const selectedPlayer = players.find((p) => p.player_name === e.target.value)
                                setYoutubeForm((prev) => ({
                                    ...prev,
                                    player_name: e.target.value,
                                    player_id: selectedPlayer?.player_id || null,
                                }))
                            }}
                        >
                            <option value="">Select player...</option>
                            {players.map((player, idx) => (
                                <option key={idx} value={player.player_name}>
                                    {player.player_name}{player.loan_team ? ` (${player.loan_team})` : ''}
                                </option>
                            ))}
                        </select>
                        <Input
                            data-testid="youtube-link-url"
                            placeholder="YouTube URL"
                            value={youtubeForm.youtube_link}
                            onChange={(e) => setYoutubeForm((prev) => ({ ...prev, youtube_link: e.target.value }))}
                        />
                        <Button size="sm" onClick={handleYoutubeCreate} data-testid="youtube-link-add">Add link</Button>
                    </div>
                    <div className="space-y-2">
                        {youtubeLinks.length === 0 ? (
                            <p className="text-sm text-muted-foreground">No YouTube links added yet.</p>
                        ) : (
                            youtubeLinks.map((link) => (
                                <div key={link.id} className="bg-card border rounded p-2 flex items-center gap-2">
                                    <div className="flex-1 min-w-0">
                                        <div className="text-sm font-medium">{link.player_name}</div>
                                        {editingYoutubeLink?.id === link.id ? (
                                            <Input
                                                className="mt-1 h-8 text-xs"
                                                value={editingYoutubeLink.youtube_link}
                                                onChange={(e) => setEditingYoutubeLink({ ...editingYoutubeLink, youtube_link: e.target.value })}
                                            />
                                        ) : (
                                            <a
                                                href={link.youtube_link}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="text-xs text-primary hover:underline truncate block"
                                            >
                                                {link.youtube_link}
                                            </a>
                                        )}
                                    </div>
                                    <div className="flex gap-1">
                                        {editingYoutubeLink?.id === link.id ? (
                                            <>
                                                <Button size="sm" variant="outline" onClick={() => handleYoutubeUpdate(link.id)}>Save</Button>
                                                <Button size="sm" variant="ghost" onClick={() => setEditingYoutubeLink(null)}>Cancel</Button>
                                            </>
                                        ) : (
                                            <>
                                                <Button size="sm" variant="outline" onClick={() => setEditingYoutubeLink(link)}>Edit</Button>
                                                <Button size="sm" variant="destructive" onClick={() => handleYoutubeDelete(link.id)}>Delete</Button>
                                            </>
                                        )}
                                    </div>
                                </div>
                            ))
                        )}
                    </div>
                </CardContent>
            </Card>

            <Card>
                <CardHeader>
                    <CardTitle>Author commentary</CardTitle>
                    <CardDescription>Intro, summary, and per-player commentary attached to this newsletter.</CardDescription>
                </CardHeader>
                <CardContent>
                    {newsletterDbId ? (
                        <CommentaryManager
                            newsletterId={newsletterDbId}
                            players={players}
                            apiService={APIService}
                        />
                    ) : null}
                </CardContent>
            </Card>
        </div>
    )
}

export default AdminNewsletterDetail
