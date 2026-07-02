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
    Brain,
    CheckCircle2,
    ChevronDown,
    ChevronRight,
    Coins,
    Crosshair,
    Download,
    Loader2,
    Play,
    RefreshCw,
    Scissors,
    ThumbsUp,
    Upload,
    UserX,
} from 'lucide-react'
import { APIService } from '@/lib/api'
import { Slider } from '@/components/ui/slider'
import { formatSeconds, parseRosterText, parseTimeInput } from '@/lib/video-utils'
import { VideoStatusBadge } from './AdminVideo'
import { FilmRoomGuide, MatchProgress } from '@/components/admin/FilmRoomGuide'
import { HelpHint } from '@/components/ui/help-hint'

const POLL_STATUSES = new Set(['queued', 'processing', 'preflight'])

const IDENTITY_BADGE = {
    human_confirmed: { label: 'confirmed', variant: 'default' },
    high: { label: 'high confidence', variant: 'default' },
    low: { label: 'low confidence', variant: 'secondary' },
    unverified: { label: 'unverified', variant: 'outline' },
}

const METRIC_LABELS = {
    minutes_on_camera: 'Minutes on camera',
    distance_m: 'Distance',
    fastest_sustained_kmh: 'Top sustained speed',
    sprint_count: 'Sprints',
    touches: 'Touches',
    heatmap: 'Heatmap',
}

function metricDisplay(m) {
    if (m.value === null || m.value === undefined) {
        return m.kind === 'beta' ? 'beta — coming soon' : 'pending calibration'
    }
    const v = `${m.value}${m.unit ? ' ' + m.unit : ''}`
    return m.kind === 'lower_bound' ? `≥ ${v}` : v
}

function votesSummary(votes) {
    if (!votes || typeof votes !== 'object') return null
    const parts = Object.entries(votes).map(([n, c]) => `${n}×${c}`)
    return parts.length ? parts.join(' · ') : null
}

function Stat({ label, value, hint }) {
    return (
        <div className="rounded-lg border p-2">
            <p className="text-lg font-semibold tabular-nums">{value}</p>
            <p className="text-xs text-muted-foreground flex items-center gap-1">
                {label}
                {hint && <HelpHint label={label} iconClassName="h-3 w-3">{hint}</HelpHint>}
            </p>
        </div>
    )
}

// session cache of per-tracklet crops + bbox, so re-expanding a row (single-open
// collapses others) doesn't refetch — the bbox payload can be thousands of rows.
const EVIDENCE_CACHE = new Map()

// Expandable per-row evidence: the match-video window for this tracklet (auto-seek +
// loop), a box that follows the exact player synced to the playhead, and the sharpest
// crops. The reviewer watches, then confirms / reassigns / dismisses in the row header.
function TrackletEvidencePanel({ matchId, tracklet, mediaToken, onAffirm, onMediaError, onSplit }) {
    const videoRef = useRef(null)
    const canvasRef = useRef(null)
    const boxesRef = useRef([])
    const [crops, setCrops] = useState(null)
    const [bbox, setBbox] = useState({ available: false, count: 0 })
    const [pos, setPos] = useState(tracklet.first_s || 0)
    const [playing, setPlaying] = useState(false)

    const first = tracklet.first_s ?? 0
    const last = Math.max(tracklet.last_s ?? first, first + 4)
    const footageUrl = mediaToken ? APIService.videoFootageUrl(matchId, mediaToken) : null

    useEffect(() => {
        let alive = true
        const key = `${matchId}:${tracklet.id}`
        const apply = ({ crops: cr, bbox: bx }) => {
            if (!alive) return
            setCrops(cr)
            boxesRef.current = bx.boxes
            setBbox({ available: bx.available, count: bx.boxes.length })
        }
        const cached = EVIDENCE_CACHE.get(key)
        if (cached) { apply(cached); return () => { alive = false } }
        Promise.all([
            APIService.getVideoTrackletCrops(matchId, tracklet.id).then((r) => r.crops || []).catch(() => []),
            APIService.getVideoTrackletBbox(matchId, tracklet.id)
                .then((r) => ({ boxes: r.boxes || [], available: !!r.available }))
                .catch(() => ({ boxes: [], available: false })),
        ]).then(([cr, bx]) => {
            EVIDENCE_CACHE.set(key, { crops: cr, bbox: bx })
            apply({ crops: cr, bbox: bx })
        })
        return () => { alive = false }
    }, [matchId, tracklet.id])

    // rAF loop: draw the detection nearest the playhead, scaling source px → displayed px
    useEffect(() => {
        const label = tracklet.suggested_number != null ? `#${tracklet.suggested_number}` : tracklet.pipeline_key
        let raf = 0, lastT = -1, lastW = 0, lastH = 0
        function loop() {
            const v = videoRef.current
            const c = canvasRef.current
            if (v && c) {
                const w = v.clientWidth, h = v.clientHeight
                const t = v.currentTime
                if (w && h && (t !== lastT || w !== lastW || h !== lastH)) {  // skip redraw while idle
                    lastT = t; lastW = w; lastH = h
                    if (c.width !== w) c.width = w
                    if (c.height !== h) c.height = h
                    const ctx = c.getContext('2d')
                    ctx.clearRect(0, 0, w, h)
                    const boxes = boxesRef.current
                    const vw = v.videoWidth, vh = v.videoHeight
                    if (boxes.length && vw && vh) {
                        let lo = 0, hi = boxes.length - 1, best = -1, bd = Infinity
                        while (lo <= hi) {
                            const mid = (lo + hi) >> 1
                            const d = Math.abs(boxes[mid][0] - t)
                            if (d < bd) { bd = d; best = mid }
                            if (boxes[mid][0] < t) lo = mid + 1; else hi = mid - 1
                        }
                        if (best >= 0 && bd <= 0.25) {  // gate: don't interpolate across gaps
                            const [, x1, y1, x2, y2] = boxes[best]
                            const sx = w / vw, sy = h / vh
                            const bx = x1 * sx, by = y1 * sy, bw = (x2 - x1) * sx, bh = (y2 - y1) * sy
                            ctx.lineWidth = 3
                            ctx.strokeStyle = '#22d3ee'
                            ctx.strokeRect(bx, by, bw, bh)
                            ctx.font = '600 13px ui-sans-serif, system-ui'
                            const tw = ctx.measureText(label).width + 8
                            ctx.fillStyle = '#22d3ee'
                            ctx.fillRect(bx, Math.max(0, by - 18), tw, 18)
                            ctx.fillStyle = '#04222a'
                            ctx.fillText(label, bx + 4, Math.max(12, by - 5))
                        }
                    }
                }
            }
            raf = requestAnimationFrame(loop)
        }
        raf = requestAnimationFrame(loop)
        return () => cancelAnimationFrame(raf)
    }, [tracklet.suggested_number, tracklet.pipeline_key])

    const onLoadedMetadata = () => {
        const v = videoRef.current
        if (v) { try { v.currentTime = first } catch { /* seek before ready */ } v.play().then(() => setPlaying(true)).catch(() => {}) }
    }
    const onTimeUpdate = () => {
        const v = videoRef.current
        if (!v) return
        setPos(v.currentTime)
        if (v.currentTime >= last || v.currentTime < first - 0.5) v.currentTime = first  // loop the window
    }
    const seek = (s) => { const v = videoRef.current; if (v) { v.currentTime = s; setPos(s) } }
    const togglePlay = () => { const v = videoRef.current; if (!v) return; if (v.paused) { v.play(); setPlaying(true) } else { v.pause(); setPlaying(false) } }

    return (
        <div className="mt-3 border-t pt-3 space-y-3">
            <div className="relative w-full max-w-xl bg-black rounded-md overflow-hidden cursor-pointer" onClick={togglePlay}>
                {footageUrl ? (
                    <video
                        ref={videoRef}
                        src={footageUrl}
                        preload="metadata"
                        playsInline
                        muted
                        className="w-full block"
                        onLoadedMetadata={onLoadedMetadata}
                        onTimeUpdate={onTimeUpdate}
                        onPlay={() => setPlaying(true)}
                        onPause={() => setPlaying(false)}
                        onError={() => onMediaError && onMediaError()}
                    />
                ) : (
                    <div className="aspect-video flex items-center justify-center text-xs text-muted-foreground">media token…</div>
                )}
                <canvas ref={canvasRef} className="absolute inset-0 pointer-events-none" />
                {!playing && footageUrl && (
                    <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                        <Play className="h-10 w-10 text-white/80" />
                    </div>
                )}
            </div>

            <div className="flex items-center gap-2 max-w-xl">
                <span className="text-xs tabular-nums text-muted-foreground w-12">{formatSeconds(pos)}</span>
                <Slider value={[Math.min(Math.max(pos, first), last)]} min={first} max={last} step={0.2} onValueChange={([v]) => seek(v)} className="flex-1" />
                <span className="text-xs tabular-nums text-muted-foreground w-12 text-right">{formatSeconds(last)}</span>
            </div>

            <p className="text-xs text-muted-foreground flex items-center gap-1">
                <Crosshair className="h-3 w-3" />
                {bbox.available && bbox.count
                    ? `box tracks this player (${bbox.count} detections)`
                    : 'box overlay unavailable for this tracklet'}
                {' · '}window {formatSeconds(first)}–{formatSeconds(last)}
            </p>

            <div>
                <p className="text-xs font-medium mb-1">Sharpest crops {crops?.length ? `(${crops.length})` : ''}</p>
                {crops === null ? (
                    <div className="flex items-center gap-1 text-xs text-muted-foreground"><Loader2 className="h-3 w-3 animate-spin" /> loading…</div>
                ) : crops.length ? (
                    <div className="flex gap-2 overflow-x-auto pb-1">
                        {crops.map((c) => (
                            <button
                                key={c.file}
                                type="button"
                                onClick={() => seek(c.t)}
                                title={`jump to ${formatSeconds(c.t)} · sharpness ${c.laplacian_var}`}
                                className="shrink-0 rounded border hover:ring-2 hover:ring-cyan-400"
                            >
                                <img src={APIService.videoCropUrl(matchId, c.file, mediaToken)} alt="player crop" className="h-24 w-auto rounded" loading="lazy" />
                            </button>
                        ))}
                    </div>
                ) : (
                    <p className="text-xs text-muted-foreground">no crops for this tracklet</p>
                )}
            </div>

            <div className="flex flex-wrap items-center gap-2">
                {onAffirm && <Button size="sm" variant="outline" onClick={onAffirm}><ThumbsUp className="h-4 w-4 mr-1" /> Looks right</Button>}
                {onSplit && tracklet.kind === 'chain' && (
                    <Button size="sm" variant="outline" onClick={() => onSplit(Math.round(pos))} title="Two players merged into one track? Cut it at the playhead">
                        <Scissors className="h-4 w-4 mr-1" /> Split here ({formatSeconds(pos)})
                    </Button>
                )}
                <span className="text-xs text-muted-foreground">…or reassign / “not a player” above, then <strong>Save tags</strong>.</span>
            </div>
        </div>
    )
}

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
    // review media: expanded rows + a match-scoped media token for <video>/<img> URLs
    const [expanded, setExpanded] = useState({})
    const [mediaToken, setMediaToken] = useState(null)
    const [exportingFeedback, setExportingFeedback] = useState(false)
    const [learning, setLearning] = useState(null)
    const [manifest, setManifest] = useState(null)
    const [splitHighlight, setSplitHighlight] = useState([])  // ids of just-split segments to surface
    const tagReviewRef = useRef(null)

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
                APIService.getVideoAccuracy(matchId).then(setLearning).catch(() => {})
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

    // mint a media token once the match has reviewable tracklets (covers all rows)
    useEffect(() => {
        if (!match || mediaToken) return
        if (match.status !== 'needs_tagging' && match.status !== 'finalized') return
        APIService.videoMediaToken(match.id).then((r) => setMediaToken(r.token)).catch(() => {})
    }, [match, mediaToken])

    // re-mint on demand when a media request 403s (the 30-min token expired mid-session);
    // URLs derive from mediaToken so updating it reloads the <video>/<img>.
    const refreshMediaToken = useCallback(() => {
        if (!match) return
        APIService.videoMediaToken(match.id).then((r) => setMediaToken(r.token)).catch(() => {})
    }, [match])

    // one panel open at a time — avoids many <video> elements each Range-streaming the match file
    const toggleExpand = (id) => setExpanded((p) => (p[id] ? {} : { [id]: true }))

    const handleSplit = async (trackletId, atS) => {
        setError(null)
        try {
            const res = await APIService.splitVideoTracklet(matchId, trackletId, atS)
            setExpanded({})  // the original tracklet is gone; collapse
            await load()
            const ids = (res.segments || []).map((s) => s.id)
            setSplitHighlight(ids)  // pin + highlight the new pieces so they're findable
            setNotice(`Split into ${ids.length} pieces — pinned to the top of Tag review. Tag each (confirm the number or “not a player”), then Re-finalize.`)
            requestAnimationFrame(() => tagReviewRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
        } catch (err) {
            setError(err.message)
        }
    }

    const handleExportFeedback = async () => {
        setExportingFeedback(true)
        setError(null)
        try {
            const { rows } = await APIService.downloadVideoFeedback(matchId, 'ours')
            setNotice(`Exported ${rows ?? ''} feedback row${rows === 1 ? '' : 's'} (our side, consented).`)
        } catch (err) {
            setError(err.message)
        } finally {
            setExportingFeedback(false)
        }
    }

    const handleBuildManifest = async () => {
        setError(null)
        try {
            const m = await APIService.getVideoTrainingManifest(matchId)
            setManifest(m)
            setNotice(`Fine-tune manifest: ${m.n_reader_examples} reader examples, ${m.n_reid_identities} ReID identities.`)
        } catch (err) {
            setError(err.message)
        }
    }

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
        setPendingTags((prev) => {
            const merged = { ...prev[trackletId], ...change }
            // a fresh roster reassignment supersedes a carried-over "looks right" affirm
            if ('roster_entry_id' in change && !('action' in change)) delete merged.action
            return { ...prev, [trackletId]: merged }
        })
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
            setSplitHighlight([])  // the just-split pieces have now been handled
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
    // surface just-split pieces at the top of the review list
    const reviewTracklets = splitHighlight.length
        ? [...tracklets].sort((a, b) => (splitHighlight.includes(b.id) ? 1 : 0) - (splitHighlight.includes(a.id) ? 1 : 0))
        : tracklets
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

            <MatchProgress status={match.status} className="rounded-lg border p-3" />

            <FilmRoomGuide defaultOpen={false} />

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
                        <CardTitle className="text-base flex items-center gap-1.5">
                            Timeline markers
                            <HelpHint label="Timeline markers">
                                Times are mm:ss into the video file (not the match clock). Kickoff is required. Kickoff and
                                end bound the analysed window, and — with halftime + 2nd-half kickoff — the pipeline skips
                                the halftime gap too, so only in-play minutes are processed (no wasted GPU on warm-ups,
                                halftime or post-match).
                            </HelpHint>
                        </CardTitle>
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
                        <CardTitle className="text-base flex items-center gap-1.5">
                            Squad list ({match.roster?.length || 0})
                            <HelpHint label="Squad list">
                                Only your own (club-owned) players get names and reports. Opposition players stay
                                numbers-only and never enter the training set — a consent / safeguarding rule.
                            </HelpHint>
                        </CardTitle>
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
                <Card ref={tagReviewRef}>
                    <CardHeader>
                        <CardTitle className="text-base">Tag review</CardTitle>
                        <CardDescription>
                            Confirm who is who. High-confidence suggestions are accepted automatically once you pick your side;
                            review the rest — usually a few minutes, not a re-watch. Tap <ChevronRight className="inline h-3 w-3" /> on
                            any row to watch that player’s video window with a tracking box, then confirm or correct.
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        {splitHighlight.length > 0 && (
                            <div className="rounded-lg border border-amber-400 bg-amber-50 dark:bg-amber-950/20 p-3 flex items-start gap-2">
                                <Scissors className="h-4 w-4 mt-0.5 text-amber-600 shrink-0" />
                                <p className="text-sm">
                                    Your split created <strong>{splitHighlight.length} new pieces</strong> (highlighted below). The
                                    original track was replaced. Tag each piece — confirm its number or mark “not a player” — then
                                    <strong> Save tags</strong> and <strong>Re-finalize</strong>.
                                    <button type="button" className="ml-2 underline text-muted-foreground" onClick={() => setSplitHighlight([])}>dismiss</button>
                                </p>
                            </div>
                        )}
                        {match.our_team_cluster == null && (
                            <div className="rounded-lg border p-3 space-y-2">
                                <p className="text-sm font-medium flex items-center gap-1.5">
                                    Which side is your team?
                                    <HelpHint label="Pick your side">
                                        The pipeline split the players into two kit-colour groups (A and B) but doesn’t know
                                        which is yours. Pick it and every high-confidence player on your side is auto-tagged
                                        instantly — you only review the rest. Check a few suggested numbers below against your
                                        squad to tell the sides apart.
                                    </HelpHint>
                                </p>
                                <div className="flex gap-2">
                                    <Button variant="outline" onClick={() => handlePickSide(0)}>
                                        Team A{match.our_kit_color ? ` (${match.our_kit_color}?)` : ''}
                                    </Button>
                                    <Button variant="outline" onClick={() => handlePickSide(1)}>Team B</Button>
                                </div>
                                <p className="text-xs text-muted-foreground">Check a few suggested numbers below against your squad to tell the sides apart.</p>
                            </div>
                        )}

                        {reviewTracklets.length > 0 && (
                            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
                                <span className="font-medium text-foreground">Each row is one detected player.</span>
                                <span className="inline-flex items-center gap-1">
                                    confident / uncertain
                                    <HelpHint label="confident / uncertain" iconClassName="h-3 w-3">The model’s confidence in the jersey number it read.</HelpHint>
                                </span>
                                <span className="inline-flex items-center gap-1">
                                    mixed identity?
                                    <HelpHint label="mixed identity" iconClassName="h-3 w-3">The track’s frames disagree on the number (under 70% agreement). Treat with suspicion — a Split often fixes it.</HelpHint>
                                </span>
                                <span className="inline-flex items-center gap-1">
                                    us / opposition · auto
                                    <HelpHint label="us / opposition / auto" iconClassName="h-3 w-3">“us/opposition” = which side, once you’ve picked your team. “auto” = auto-tagged for you (high confidence) — confirm or correct it.</HelpHint>
                                </span>
                                <span className="inline-flex items-center gap-1">
                                    controls
                                    <HelpHint label="row controls" iconClassName="h-3 w-3">Assign the right player from the dropdown, or the person-with-✗ to mark “not a player”. Tap › to watch this player’s looping window with a tracking box, confirm (“Looks right”), or Split a row that’s really two players.</HelpHint>
                                </span>
                            </div>
                        )}
                        <div className="space-y-2">
                            {reviewTracklets.map((t) => {
                                const boundTo = trackletValue(t, 'roster_entry_id', t.roster_entry_id)
                                const dismissed = trackletValue(t, 'dismissed', t.dismissed)
                                const entry = boundTo ? rosterByEntryId[boundTo] : null
                                const highlighted = splitHighlight.includes(t.id)
                                return (
                                    <div key={t.id} className={`rounded-lg border p-3 ${dismissed ? 'opacity-50' : ''} ${highlighted ? 'ring-2 ring-amber-400 ring-offset-1' : ''}`}>
                                        <div className="flex flex-wrap items-center gap-3">
                                            <button
                                                type="button"
                                                onClick={() => toggleExpand(t.id)}
                                                className="text-muted-foreground hover:text-foreground shrink-0"
                                                aria-label={expanded[t.id] ? 'Collapse' : 'Watch video'}
                                                title="Watch this player's video"
                                            >
                                                {expanded[t.id] ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                                            </button>
                                            <div className="min-w-0 flex-1">
                                                <div className="flex items-center gap-2 flex-wrap">
                                                    <span className="font-medium">
                                                        {t.kind === 'chain' && t.suggested_number != null ? `#${t.suggested_number}` : t.pipeline_key}
                                                    </span>
                                                    {t.kind === 'chain' && (t.contaminated ? (
                                                        <Badge variant="destructive"><AlertTriangle className="h-3 w-3 mr-1" />mixed identity?</Badge>
                                                    ) : (
                                                        <Badge variant={t.confidence === 'high' ? 'default' : 'secondary'}>
                                                            {t.confidence === 'high' ? 'confident' : 'uncertain'}
                                                        </Badge>
                                                    ))}
                                                    {t.team_cluster != null && t.team_cluster >= 0 && (
                                                        <Badge variant="outline">{match.our_team_cluster == null ? `side ${t.team_cluster === 0 ? 'A' : 'B'}` : (t.team_cluster === match.our_team_cluster ? 'us' : 'opposition')}</Badge>
                                                    )}
                                                    {t.tag_source === 'auto' && !pendingTags[t.id] && <Badge variant="secondary">auto</Badge>}
                                                    {t.review_action && !pendingTags[t.id] && (
                                                        <Badge variant="outline" className="text-emerald-600 border-emerald-500/40"><CheckCircle2 className="h-3 w-3 mr-1" />{t.review_action}</Badge>
                                                    )}
                                                </div>
                                                <p className="text-xs text-muted-foreground">
                                                    visible {Math.round((t.visible_s || 0) / 60)}m · {formatSeconds(t.first_s)}–{formatSeconds(t.last_s)}
                                                    {t.evidence?.number_agreement != null && t.evidence.number_agreement < 1
                                                        ? ` · ${Math.round(t.evidence.number_agreement * 100)}% number agreement` : ''}
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
                                        {expanded[t.id] && (
                                            <TrackletEvidencePanel
                                                matchId={matchId}
                                                tracklet={t}
                                                mediaToken={mediaToken}
                                                onMediaError={refreshMediaToken}
                                                onAffirm={boundTo != null ? () => stageTag(t.id, { roster_entry_id: boundTo, action: 'confirmed', dismissed: false }) : null}
                                                onSplit={(atS) => handleSplit(t.id, atS)}
                                            />
                                        )}
                                    </div>
                                )
                            })}
                            {tracklets.length === 0 && <p className="text-sm text-muted-foreground">No tracklets yet.</p>}
                        </div>

                        <div className="flex flex-wrap items-center gap-2">
                            <Button onClick={handleSaveTags} disabled={tagsSaving || Object.keys(pendingTags).length === 0}>
                                {tagsSaving && <Loader2 className="h-4 w-4 mr-1 animate-spin" />}
                                Save tags ({Object.keys(pendingTags).length})
                            </Button>
                            <HelpHint label="Save tags vs Finalize">
                                <strong>Save tags</strong> writes your staged changes (the number in the button) to the server.
                                <strong> Finalize</strong> then rebuilds the per-player report from your confirmed identities.
                                Re-finalizing never re-runs the GPU — it just re-aggregates, so correct and re-finalize freely.
                            </HelpHint>
                            <Button variant="outline" onClick={handleFinalize}>
                                <CheckCircle2 className="h-4 w-4 mr-1" /> {match.status === 'finalized' ? 'Re-finalize' : 'Finalize match'}
                            </Button>
                            {match.status === 'finalized' && (
                                <Button variant="ghost" onClick={handleExportFeedback} disabled={exportingFeedback} title="Per-crop labels from your corrections — feeds the identity model (our side only)">
                                    {exportingFeedback ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Download className="h-4 w-4 mr-1" />}
                                    Export feedback
                                </Button>
                            )}
                        </div>
                    </CardContent>
                </Card>
            )}

            {match.status === 'finalized' && report && (
                <Card>
                    <CardHeader>
                        <CardTitle className="text-base flex items-center gap-1.5">
                            Player reports
                            <HelpHint label="Player reports">
                                Identity confidence ranks <em>you confirmed</em> &gt; high &gt; low &gt; unverified — a stat is only as
                                trustworthy as the identity it hangs on. Coverage is on-camera time (a panning camera never sees
                                everyone). “pending calibration” = needs the pitch-homography stage (not wired yet); “beta” =
                                experimental. Both are shown honestly, never guessed. A player we never confidently saw still
                                gets a row (unverified / 0 min) — more honest than silent omission.
                            </HelpHint>
                        </CardTitle>
                        <CardDescription>
                            Every figure carries its own confidence, gated by identity — a stat is only as
                            trustworthy as the player it’s attributed to. Coverage shows how much of each player we
                            actually saw; metrics that need pitch calibration are shown as pending, never guessed.
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-3">
                            {(report.reports || []).map((r) => {
                                const idconf = r.identity_confidence || 'unverified'
                                const idb = IDENTITY_BADGE[idconf] || IDENTITY_BADGE.unverified
                                const cov = r.coverage || {}
                                const votes = votesSummary(r.identity_evidence?.votes)
                                return (
                                    <div key={r.id} className="rounded-lg border p-3 space-y-2">
                                        <div className="flex flex-wrap items-center gap-2">
                                            <span className="font-medium">#{r.jersey_number} {r.player_name}</span>
                                            <Badge variant={idb.variant}>{idb.label}</Badge>
                                            {r.identity_evidence?.splice_risk && (
                                                <Badge variant="destructive"><AlertTriangle className="h-3 w-3 mr-1" />mixed identity?</Badge>
                                            )}
                                            {r.identity_evidence?.source === 'human' && <Badge variant="outline">you confirmed</Badge>}
                                        </div>
                                        <p className="text-xs text-muted-foreground">
                                            {cov.on_camera_min ?? r.minutes_visible ?? '—'} min on camera
                                            {cov.confident_windows != null ? ` · ${cov.confident_windows} window${cov.confident_windows === 1 ? '' : 's'}` : ''}
                                            {cov.pct_of_match != null ? ` · ${Math.round(cov.pct_of_match * 100)}% of match` : ''}
                                            {votes ? ` · reads ${votes}` : ''}
                                        </p>
                                        <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-1">
                                            {(r.metrics || []).filter((m) => m && m.key).map((m) => (
                                                <div key={m.key} className="flex items-baseline justify-between gap-2 text-sm">
                                                    <span className="text-muted-foreground">{METRIC_LABELS[m.key] || m.key}</span>
                                                    <span className={m.suppressed ? 'text-muted-foreground/60 italic text-xs' : 'font-medium'}>
                                                        {metricDisplay(m)}
                                                        {!m.suppressed && m.confidence ? <span className="text-muted-foreground font-normal text-xs"> ({m.confidence})</span> : null}
                                                    </span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )
                            })}
                            {(report.reports || []).length === 0 && (
                                <p className="text-sm text-muted-foreground">No reports — bind tracklets to players, then re-finalize.</p>
                            )}
                        </div>
                    </CardContent>
                </Card>
            )}

            {match.status === 'finalized' && learning && (
                <Card>
                    <CardHeader>
                        <CardTitle className="text-base flex items-center gap-2"><Brain className="h-4 w-4" /> Model accuracy &amp; learning</CardTitle>
                        <CardDescription>
                            How the model did on this match vs your corrections — and how those corrections feed back to
                            improve it: recalibrate the thresholds + fine-tune the jersey reader. Your review IS the training signal.
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-3">
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                            <Stat label="Chains reviewed" value={`${learning.accuracy.reviewed}/${learning.accuracy.chains_total}`} hint="How many detected players you’ve acted on (confirmed/reassigned/dismissed/split) out of the total." />
                            <Stat label="Auto-tag precision" value={learning.accuracy.auto_tag_precision != null ? `${Math.round(learning.accuracy.auto_tag_precision * 100)}%` : '—'} hint="Of the players the model auto-tagged, the share you confirmed as correct (vs reassigned/dismissed)." />
                            <Stat label="Number-read accuracy" value={learning.accuracy.number_read_accuracy != null ? `${Math.round(learning.accuracy.number_read_accuracy * 100)}%` : '—'} hint="How often the jersey number it read matched the player you confirmed." />
                            <Stat label="Corrections" value={`${learning.accuracy.reassigned + learning.accuracy.dismissed + learning.accuracy.splits}`} hint="Total fixes you made: reassignments + “not a player” + splits. Each one is a training signal." />
                        </div>
                        <div className="text-xs text-muted-foreground flex flex-wrap gap-x-4 gap-y-1">
                            <span>confirmed {learning.accuracy.confirmed}</span>
                            <span>reassigned {learning.accuracy.reassigned}</span>
                            <span>dismissed {learning.accuracy.dismissed}</span>
                            <span>split {learning.accuracy.splits}</span>
                            <span>unreviewed {learning.accuracy.unreviewed}</span>
                        </div>
                        <div className="rounded-lg border p-3 space-y-1">
                            <p className="text-xs font-medium">Recalibration signals (tune thresholds next round)</p>
                            {(learning.recalibration.suggestions || []).map((s, i) => (
                                <p key={i} className="text-xs text-muted-foreground">• {s}</p>
                            ))}
                        </div>
                        <div className="flex flex-wrap items-center gap-2">
                            <Button variant="outline" size="sm" onClick={handleBuildManifest}><Brain className="h-4 w-4 mr-1" /> Build fine-tune manifest</Button>
                            <HelpHint label="Fine-tune manifest">
                                Turns your confirmed crops into a training set — “crop → number” for the jersey reader and
                                “identity → crops” for player-recognition. Consent-gated: only your own players’ crops, never
                                opposition. The actual retraining is a separate offline step.
                            </HelpHint>
                            {manifest && (
                                <span className="text-xs text-muted-foreground">
                                    {manifest.n_reader_examples} reader examples · {manifest.n_reid_identities} ReID identities · {manifest.n_negatives} negatives (consented, our side)
                                </span>
                            )}
                        </div>
                    </CardContent>
                </Card>
            )}
        </div>
    )
}

export default AdminVideoMatch
