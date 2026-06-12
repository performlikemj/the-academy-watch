import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import { Textarea } from '@/components/ui/textarea'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'
import {
    AlertTriangle,
    CheckCircle2,
    Coins,
    Loader2,
    Play,
    RefreshCw,
    Upload,
    UserX,
} from 'lucide-react'
import { APIService } from '@/lib/api'
import { formatSeconds, parseRosterText, parseTimeInput } from '@/lib/video-utils'
import { VideoStatusBadge } from './AdminVideo'

const POLL_STATUSES = new Set(['queued', 'processing', 'preflight'])

export function AdminVideoMatch() {
    const { matchId } = useParams()
    const [match, setMatch] = useState(null)
    const [error, setError] = useState(null)
    const [notice, setNotice] = useState(null)

    const [uploadState, setUploadState] = useState({ phase: 'idle', progress: 0 })
    const [markers, setMarkers] = useState({ kickoff: '', halftime: '', secondHalf: '' })
    const fileRef = useRef(null)
    const uploadInfoRef = useRef(null)

    const [rosterText, setRosterText] = useState('')
    const [rosterSaving, setRosterSaving] = useState(false)

    const [processing, setProcessing] = useState(false)

    const [tracklets, setTracklets] = useState([])
    const [pendingTags, setPendingTags] = useState({})
    const [tagsSaving, setTagsSaving] = useState(false)
    const [report, setReport] = useState(null)

    const load = useCallback(async () => {
        try {
            const data = await APIService.getVideoMatch(matchId)
            setMatch(data)
            if (data.status === 'needs_tagging' || data.status === 'finalized') {
                const t = await APIService.getVideoTracklets(matchId)
                setTracklets(t.tracklets || [])
            }
            if (data.status === 'finalized') {
                const r = await APIService.getVideoReport(matchId)
                setReport(r)
            }
            return data
        } catch (err) {
            setError(err.message)
            return null
        }
    }, [matchId])

    useEffect(() => { load() }, [load])

    // poll while the pipeline owns the match
    useEffect(() => {
        if (!match || !POLL_STATUSES.has(match.status)) return undefined
        const id = setInterval(load, 5000)
        return () => clearInterval(id)
    }, [match, load])

    useEffect(() => {
        if (match) {
            setMarkers({
                kickoff: match.kickoff_s != null ? formatSeconds(match.kickoff_s) : '',
                halftime: match.halftime_s != null ? formatSeconds(match.halftime_s) : '',
                secondHalf: match.second_half_kickoff_s != null ? formatSeconds(match.second_half_kickoff_s) : '',
            })
            if (!rosterText && match.roster?.length) {
                setRosterText(match.roster.map((r) => `${r.jersey_number} ${r.player_name}`).join('\n'))
            }
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [match?.id, match?.status])

    const rosterByEntryId = useMemo(() => {
        const map = {}
        for (const r of match?.roster || []) map[r.id] = r
        return map
    }, [match])

    const handleUpload = async () => {
        const file = fileRef.current?.files?.[0]
        if (!file) { setError('Choose a video file first'); return }
        setError(null)
        setUploadState({ phase: 'uploading', progress: 0 })
        try {
            if (!uploadInfoRef.current) {
                uploadInfoRef.current = await APIService.remintVideoUploadSas(matchId)
            }
            try {
                await APIService.uploadVideoToBlob(uploadInfoRef.current.upload_url, file, (p) => setUploadState({ phase: 'uploading', progress: p }))
            } catch (err) {
                if (err.status === 403) { // SAS expired mid-upload — re-mint once and retry
                    uploadInfoRef.current = await APIService.remintVideoUploadSas(matchId)
                    await APIService.uploadVideoToBlob(uploadInfoRef.current.upload_url, file, (p) => setUploadState({ phase: 'uploading', progress: p }))
                } else {
                    throw err
                }
            }
            setUploadState({ phase: 'uploaded', progress: 100 })
            setNotice('Upload complete — mark kickoff below, then confirm.')
        } catch (err) {
            setError(err.message)
            setUploadState({ phase: 'idle', progress: 0 })
        }
    }

    const handleConfirmUpload = async () => {
        const kickoff = parseTimeInput(markers.kickoff)
        if (kickoff === undefined || kickoff === null) {
            setError('Kickoff time is required (mm:ss into the video)')
            return
        }
        const halftime = parseTimeInput(markers.halftime)
        const secondHalf = parseTimeInput(markers.secondHalf)
        if (halftime === undefined || secondHalf === undefined) {
            setError('Times must be mm:ss or seconds')
            return
        }
        setError(null)
        try {
            await APIService.videoUploadComplete(matchId, {
                kickoff_s: kickoff,
                halftime_s: halftime,
                second_half_kickoff_s: secondHalf,
            })
            setNotice('Footage verified.')
            await load()
        } catch (err) {
            setError(err.message)
        }
    }

    const handleSaveMarkers = async () => {
        const kickoff = parseTimeInput(markers.kickoff)
        const halftime = parseTimeInput(markers.halftime)
        const secondHalf = parseTimeInput(markers.secondHalf)
        if ([kickoff, halftime, secondHalf].includes(undefined)) {
            setError('Times must be mm:ss or seconds')
            return
        }
        setError(null)
        try {
            await APIService.updateVideoMatch(matchId, {
                kickoff_s: kickoff,
                halftime_s: halftime,
                second_half_kickoff_s: secondHalf,
            })
            setNotice('Markers saved.')
            await load()
        } catch (err) {
            setError(err.message)
        }
    }

    const handleSaveRoster = async () => {
        const entries = parseRosterText(rosterText)
        if (!entries.length) { setError('Roster needs lines like "10 John Smith"'); return }
        setRosterSaving(true)
        setError(null)
        try {
            await APIService.upsertVideoRoster(matchId, entries)
            setNotice(`Roster saved (${entries.length} players).`)
            await load()
        } catch (err) {
            setError(err.message)
        } finally {
            setRosterSaving(false)
        }
    }

    const handleProcess = async () => {
        setProcessing(true)
        setError(null)
        try {
            await APIService.processVideoMatch(matchId)
            setNotice('Queued for processing — this page polls automatically.')
            await load()
        } catch (err) {
            setError(err.status === 402 ? 'No credits — grant credits from the Video Analysis page first.' : err.message)
        } finally {
            setProcessing(false)
        }
    }

    const handlePickSide = async (cluster) => {
        setError(null)
        try {
            const res = await APIService.updateVideoMatch(matchId, { our_team_cluster: cluster })
            setNotice(res.auto_bound ? `Side confirmed — ${res.auto_bound} high-confidence players auto-tagged.` : 'Side confirmed.')
            await load()
        } catch (err) {
            setError(err.message)
        }
    }

    const stageTag = (trackletId, change) => {
        setPendingTags((prev) => ({ ...prev, [trackletId]: { ...prev[trackletId], ...change } }))
    }

    const handleSaveTags = async () => {
        const tags = Object.entries(pendingTags).map(([trackletId, change]) => ({
            tracklet_id: Number(trackletId),
            ...change,
        }))
        if (!tags.length) return
        setTagsSaving(true)
        setError(null)
        try {
            await APIService.bindVideoTags(matchId, tags)
            setPendingTags({})
            setNotice(`${tags.length} tag change${tags.length === 1 ? '' : 's'} saved.`)
            await load()
        } catch (err) {
            setError(err.message)
        } finally {
            setTagsSaving(false)
        }
    }

    const handleFinalize = async () => {
        setError(null)
        try {
            const res = await APIService.finalizeVideoMatch(matchId)
            setNotice(`Finalized — ${res.reports} player report${res.reports === 1 ? '' : 's'}.`)
            await load()
        } catch (err) {
            setError(err.message)
        }
    }

    if (!match) {
        return error
            ? <p className="text-sm text-destructive">{error}</p>
            : <div className="flex items-center gap-2 text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Loading…</div>
    }

    const job = match.job
    const trackletValue = (t, field, fallback) => {
        const pending = pendingTags[t.id]
        return pending && field in pending ? pending[field] : fallback
    }

    return (
        <div className="space-y-6 max-w-4xl">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                    <h1 className="text-2xl font-bold">vs {match.opponent_name || 'Unknown opponent'}</h1>
                    <p className="text-sm text-muted-foreground">
                        Match #{match.id}{match.match_date ? ` · ${match.match_date}` : ''}{match.competition ? ` · ${match.competition}` : ''}
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <Badge variant="secondary"><Coins className="h-3.5 w-3.5 mr-1" />{match.credit_balance}</Badge>
                    <VideoStatusBadge status={match.status} />
                    <Button variant="ghost" size="icon" onClick={load} aria-label="Refresh"><RefreshCw className="h-4 w-4" /></Button>
                </div>
            </div>

            {error && <p className="text-sm text-destructive">{error}</p>}
            {notice && <p className="text-sm text-emerald-600">{notice}</p>}

            {match.status === 'created' && (
                <Card>
                    <CardHeader>
                        <CardTitle className="text-base flex items-center gap-2"><Upload className="h-4 w-4" /> Upload footage</CardTitle>
                        <CardDescription>
                            Goes directly to storage — keep this tab open. Mark kickoff when the upload finishes:
                            ten seconds of your time beats any auto-detection.
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <Input ref={fileRef} type="file" accept="video/mp4,video/*" disabled={uploadState.phase === 'uploading'} />
                        {uploadState.phase === 'uploading' && (
                            <div className="space-y-1">
                                <Progress value={uploadState.progress} />
                                <p className="text-xs text-muted-foreground">{uploadState.progress}% uploaded</p>
                            </div>
                        )}
                        {uploadState.phase !== 'uploaded' ? (
                            <Button onClick={handleUpload} disabled={uploadState.phase === 'uploading'}>
                                {uploadState.phase === 'uploading' ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Upload className="h-4 w-4 mr-1" />}
                                Upload
                            </Button>
                        ) : (
                            <div className="space-y-3 rounded-lg border p-3">
                                <p className="text-sm font-medium">Mark the match timeline (mm:ss into the video)</p>
                                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                                    <div>
                                        <Label htmlFor="vm-kick">Kickoff *</Label>
                                        <Input id="vm-kick" placeholder="15:00" value={markers.kickoff} onChange={(e) => setMarkers({ ...markers, kickoff: e.target.value })} />
                                    </div>
                                    <div>
                                        <Label htmlFor="vm-half">Halftime whistle</Label>
                                        <Input id="vm-half" placeholder="62:30" value={markers.halftime} onChange={(e) => setMarkers({ ...markers, halftime: e.target.value })} />
                                    </div>
                                    <div>
                                        <Label htmlFor="vm-second">2nd-half kickoff</Label>
                                        <Input id="vm-second" placeholder="78:00" value={markers.secondHalf} onChange={(e) => setMarkers({ ...markers, secondHalf: e.target.value })} />
                                    </div>
                                </div>
                                <Button onClick={handleConfirmUpload}><CheckCircle2 className="h-4 w-4 mr-1" /> Confirm upload</Button>
                            </div>
                        )}
                    </CardContent>
                </Card>
            )}

            {match.status !== 'finalized' && match.status !== 'created' && (
                <Card>
                    <CardHeader>
                        <CardTitle className="text-base">Timeline markers</CardTitle>
                        <CardDescription>Kickoff is required before processing.</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-3">
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                            <div>
                                <Label htmlFor="vm-kick2">Kickoff *</Label>
                                <Input id="vm-kick2" placeholder="15:00" value={markers.kickoff} onChange={(e) => setMarkers({ ...markers, kickoff: e.target.value })} />
                            </div>
                            <div>
                                <Label htmlFor="vm-half2">Halftime whistle</Label>
                                <Input id="vm-half2" placeholder="62:30" value={markers.halftime} onChange={(e) => setMarkers({ ...markers, halftime: e.target.value })} />
                            </div>
                            <div>
                                <Label htmlFor="vm-second2">2nd-half kickoff</Label>
                                <Input id="vm-second2" placeholder="78:00" value={markers.secondHalf} onChange={(e) => setMarkers({ ...markers, secondHalf: e.target.value })} />
                            </div>
                        </div>
                        <Button variant="outline" size="sm" onClick={handleSaveMarkers}>Save markers</Button>
                    </CardContent>
                </Card>
            )}

            {match.status !== 'finalized' && (
                <Card>
                    <CardHeader>
                        <CardTitle className="text-base">Squad list ({match.roster?.length || 0})</CardTitle>
                        <CardDescription>One player per line: number then name — e.g. “10 John Smith”. Your team only; opposition stays numbers-only.</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-3">
                        <Textarea rows={6} value={rosterText} onChange={(e) => setRosterText(e.target.value)} placeholder={'1 Sam Keeper\n10 John Smith\n…'} />
                        <Button variant="outline" size="sm" onClick={handleSaveRoster} disabled={rosterSaving}>
                            {rosterSaving && <Loader2 className="h-4 w-4 mr-1 animate-spin" />} Save squad
                        </Button>
                    </CardContent>
                </Card>
            )}

            {match.status === 'uploaded' && (
                <Card>
                    <CardHeader>
                        <CardTitle className="text-base">Process</CardTitle>
                        <CardDescription>Debits 1 credit and queues the analysis. Most matches finish within a few hours.</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <Button onClick={handleProcess} disabled={processing || !match.roster?.length || match.kickoff_s == null}>
                            {processing ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Play className="h-4 w-4 mr-1" />}
                            Process match (1 credit)
                        </Button>
                        {(!match.roster?.length || match.kickoff_s == null) && (
                            <p className="text-xs text-muted-foreground mt-2">
                                Needs {!match.roster?.length ? 'a squad list' : ''}{!match.roster?.length && match.kickoff_s == null ? ' and ' : ''}{match.kickoff_s == null ? 'a kickoff marker' : ''}.
                            </p>
                        )}
                    </CardContent>
                </Card>
            )}

            {POLL_STATUSES.has(match.status) && job && (
                <Card>
                    <CardHeader>
                        <CardTitle className="text-base flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin" /> Processing</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                        <Progress value={job.progress || 0} />
                        <p className="text-sm text-muted-foreground">
                            {job.status === 'queued' ? 'Waiting for a worker…' : `Stage: ${job.stage || '—'} (attempt ${job.attempt})`}
                        </p>
                    </CardContent>
                </Card>
            )}

            {match.status === 'failed' && (
                <Card>
                    <CardHeader>
                        <CardTitle className="text-base flex items-center gap-2 text-destructive"><AlertTriangle className="h-4 w-4" /> Processing failed</CardTitle>
                        <CardDescription className="break-words">{job?.error || 'Unknown error'}</CardDescription>
                    </CardHeader>
                    <CardContent className="flex gap-2">
                        <Button variant="outline" size="sm" onClick={async () => { await APIService.requeueVideoMatch(matchId); load() }}>Requeue (no charge)</Button>
                        <Button variant="outline" size="sm" onClick={async () => { await APIService.refundVideoMatch(matchId); setNotice('Refunded.'); load() }}>Refund credit</Button>
                    </CardContent>
                </Card>
            )}

            {(match.status === 'needs_tagging' || match.status === 'finalized') && (
                <Card>
                    <CardHeader>
                        <CardTitle className="text-base">Tag review</CardTitle>
                        <CardDescription>
                            Confirm who is who. High-confidence suggestions are accepted automatically once you pick your side;
                            review the rest — usually a few minutes, not a re-watch.
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        {match.our_team_cluster == null && (
                            <div className="rounded-lg border p-3 space-y-2">
                                <p className="text-sm font-medium">Which side is your team?</p>
                                <div className="flex gap-2">
                                    <Button variant="outline" onClick={() => handlePickSide(0)}>
                                        Team A{match.our_kit_color ? ` (${match.our_kit_color}?)` : ''}
                                    </Button>
                                    <Button variant="outline" onClick={() => handlePickSide(1)}>Team B</Button>
                                </div>
                                <p className="text-xs text-muted-foreground">Check a few suggested numbers below against your squad to tell the sides apart.</p>
                            </div>
                        )}

                        <div className="space-y-2">
                            {tracklets.map((t) => {
                                const boundTo = trackletValue(t, 'roster_entry_id', t.roster_entry_id)
                                const dismissed = trackletValue(t, 'dismissed', t.dismissed)
                                const entry = boundTo ? rosterByEntryId[boundTo] : null
                                return (
                                    <div key={t.id} className={`rounded-lg border p-3 flex flex-wrap items-center gap-3 ${dismissed ? 'opacity-50' : ''}`}>
                                        <div className="min-w-0 flex-1">
                                            <div className="flex items-center gap-2 flex-wrap">
                                                <span className="font-medium">
                                                    {t.kind === 'chain' && t.suggested_number != null ? `#${t.suggested_number}` : t.pipeline_key}
                                                </span>
                                                {t.kind === 'chain' && (
                                                    <Badge variant={t.confidence === 'high' ? 'default' : 'secondary'}>
                                                        {t.confidence === 'high' ? 'confident' : 'uncertain'}
                                                    </Badge>
                                                )}
                                                {t.team_cluster != null && t.team_cluster >= 0 && (
                                                    <Badge variant="outline">{match.our_team_cluster == null ? `side ${t.team_cluster === 0 ? 'A' : 'B'}` : (t.team_cluster === match.our_team_cluster ? 'us' : 'opposition')}</Badge>
                                                )}
                                                {t.contaminated && (
                                                    <Badge variant="destructive"><AlertTriangle className="h-3 w-3 mr-1" />mixed identity</Badge>
                                                )}
                                                {t.tag_source === 'auto' && !pendingTags[t.id] && <Badge variant="secondary">auto</Badge>}
                                            </div>
                                            <p className="text-xs text-muted-foreground">
                                                visible {Math.round((t.visible_s || 0) / 60)}m · {formatSeconds(t.first_s)}–{formatSeconds(t.last_s)}
                                            </p>
                                        </div>
                                        <div className="flex items-center gap-2">
                                            <Select
                                                value={boundTo ? String(boundTo) : 'none'}
                                                onValueChange={(v) => stageTag(t.id, { roster_entry_id: v === 'none' ? null : Number(v), dismissed: false })}
                                                disabled={dismissed}
                                            >
                                                <SelectTrigger className="w-44">
                                                    <SelectValue placeholder="Assign player…">
                                                        {entry ? `#${entry.jersey_number} ${entry.player_name}` : 'Unassigned'}
                                                    </SelectValue>
                                                </SelectTrigger>
                                                <SelectContent>
                                                    <SelectItem value="none">Unassigned</SelectItem>
                                                    {(match.roster || []).map((r) => (
                                                        <SelectItem key={r.id} value={String(r.id)}>#{r.jersey_number} {r.player_name}</SelectItem>
                                                    ))}
                                                </SelectContent>
                                            </Select>
                                            <Button
                                                variant="ghost"
                                                size="icon"
                                                aria-label="Not a player"
                                                title="Not a player (spectator/staff)"
                                                onClick={() => stageTag(t.id, { dismissed: !dismissed })}
                                            >
                                                <UserX className={`h-4 w-4 ${dismissed ? 'text-destructive' : ''}`} />
                                            </Button>
                                        </div>
                                    </div>
                                )
                            })}
                            {tracklets.length === 0 && <p className="text-sm text-muted-foreground">No tracklets yet.</p>}
                        </div>

                        <div className="flex flex-wrap gap-2">
                            <Button onClick={handleSaveTags} disabled={tagsSaving || Object.keys(pendingTags).length === 0}>
                                {tagsSaving && <Loader2 className="h-4 w-4 mr-1 animate-spin" />}
                                Save tags ({Object.keys(pendingTags).length})
                            </Button>
                            <Button variant="outline" onClick={handleFinalize}>
                                <CheckCircle2 className="h-4 w-4 mr-1" /> {match.status === 'finalized' ? 'Re-finalize' : 'Finalize match'}
                            </Button>
                        </div>
                    </CardContent>
                </Card>
            )}

            {match.status === 'finalized' && report && (
                <Card>
                    <CardHeader>
                        <CardTitle className="text-base">Player reports</CardTitle>
                        <CardDescription>
                            On-camera minutes from a single panning camera — players out of frame aren’t counted, so
                            these are visibility numbers, not full-match totals.
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-1">
                            {(report.reports || []).map((r) => (
                                <div key={r.id} className="flex items-center justify-between rounded border px-3 py-2">
                                    <span className="font-medium">#{r.jersey_number} {r.player_name}</span>
                                    <span className="text-sm text-muted-foreground">{r.minutes_visible ?? '—'} min on camera</span>
                                </div>
                            ))}
                            {(report.reports || []).length === 0 && (
                                <p className="text-sm text-muted-foreground">No reports — bind tracklets to players, then re-finalize.</p>
                            )}
                        </div>
                    </CardContent>
                </Card>
            )}
        </div>
    )
}

export default AdminVideoMatch
