import { useEffect, useMemo, useRef, useState } from 'react'
import {
    AlertTriangle,
    Check,
    ChevronDown,
    Clock3,
    Crosshair,
    Loader2,
    Pause,
    Play,
    ShieldCheck,
    SkipBack,
    SkipForward,
    Unlink,
    UserX,
    Users,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { APIService, nextWindowIndex } from '@/lib/api'
import { formatSeconds } from '@/lib/video-utils'

// One bounded session cache shared by the review rows and player reels. Each
// part is loaded independently: card crops do not pull bbox tracks, and a reel
// only fetches the bbox payload for its live window.
const EVIDENCE_CACHE = new Map()
const EVIDENCE_CACHE_MAX = 40
const MAX_MEDIA_REMINTS = 2

function realNumber(value) {
    return Number.isInteger(value) && value >= 0 ? value : null
}

// eslint-disable-next-line react-refresh/only-export-components
export function formatVoteSummary(chains) {
    if (!Array.isArray(chains)) return 'model reads: no usable number'
    const reads = new Map()
    const suggestions = new Set()
    for (const chain of chains) {
        const voted = realNumber(chain?.voted_number)
        const suggested = realNumber(chain?.suggested_number)
        const total = Number.isInteger(chain?.vote_total) && chain.vote_total > 0 ? chain.vote_total : 0
        if (voted !== null && total) reads.set(voted, (reads.get(voted) || 0) + total)
        if (suggested !== null && suggested !== voted) suggestions.add(suggested)
    }
    const parts = [...reads]
        .sort(([numberA, countA], [numberB, countB]) => countB - countA || numberA - numberB)
        .map(([number, count]) => `#${number} × ${count}`)
    for (const number of [...suggestions].sort((a, b) => a - b)) {
        if (!reads.has(number)) parts.push(`#${number} suggested`)
    }
    return `model reads: ${parts.length ? parts.join(' · ') : 'no usable number'}`
}

// eslint-disable-next-line react-refresh/only-export-components
export function mismatchBadge(player) {
    if (!player?.number_mismatch) return null
    const jerseyNumber = realNumber(player.jersey_number)
    const voted = (player.chains || [])
        .map((chain) => ({
            number: realNumber(chain?.voted_number),
            total: Number.isInteger(chain?.vote_total) && chain.vote_total > 0 ? chain.vote_total : 0,
        }))
        .filter((candidate) => candidate.number !== null && candidate.number !== jerseyNumber)
        .sort((a, b) => b.total - a.total || a.number - b.number)[0]
    if (voted) return `reads say #${voted.number}`

    const suggested = (player.chains || [])
        .map((chain) => realNumber(chain?.suggested_number))
        .filter((number) => number !== null && number !== jerseyNumber)
        .sort((a, b) => a - b)[0]
    return suggested === undefined ? null : `model suggests #${suggested}`
}

// eslint-disable-next-line react-refresh/only-export-components
export function orderReelWindows(windows, ordering = 'chronological') {
    const copy = Array.isArray(windows) ? [...windows] : []
    if (ordering === 'ranked') {
        return copy.sort((a, b) => (a.rank ?? Number.MAX_SAFE_INTEGER) - (b.rank ?? Number.MAX_SAFE_INTEGER)
            || a.start_s - b.start_s
            || a.tracklet_id - b.tracklet_id)
    }
    return copy.sort((a, b) => a.start_s - b.start_s || a.end_s - b.end_s || a.tracklet_id - b.tracklet_id)
}

// eslint-disable-next-line react-refresh/only-export-components
export function matchCaptionToWindow(window, captions, player) {
    if (!window || !Array.isArray(captions) || player?.roster_entry_id == null) return null
    for (const caption of captions) {
        if (caption?.tracklet_id !== window.tracklet_id) continue
        if (caption.roster_entry_id == null || caption.roster_entry_id !== player.roster_entry_id) continue
        const windowDuration = window.end_s - window.start_s
        const captionDuration = caption.end_s - caption.start_s
        const shorter = Math.min(windowDuration, captionDuration)
        if (!(shorter > 0)) continue
        const overlap = Math.max(0, Math.min(window.end_s, caption.end_s) - Math.max(window.start_s, caption.start_s))
        if (overlap / shorter >= 0.5) return caption
    }
    return null
}

// eslint-disable-next-line react-refresh/only-export-components
export function captionPresentation(caption) {
    if (!caption) return null
    if (caption.player_visible === false) {
        return {
            kind: 'context',
            label: 'clip context — player not confirmed in frame',
            showActionType: false,
        }
    }
    return {
        kind: 'player',
        label: 'AI clip notes — qualitative',
        showActionType: true,
    }
}

function evidenceEntry(matchId, trackletId) {
    const key = `${matchId}:${trackletId}`
    let entry = EVIDENCE_CACHE.get(key)
    if (!entry) {
        if (EVIDENCE_CACHE.size >= EVIDENCE_CACHE_MAX) {
            EVIDENCE_CACHE.delete(EVIDENCE_CACHE.keys().next().value)
        }
        entry = {}
        EVIDENCE_CACHE.set(key, entry)
    }
    return entry
}

// eslint-disable-next-line react-refresh/only-export-components
export function loadTrackletCrops(matchId, trackletId) {
    const entry = evidenceEntry(matchId, trackletId)
    if (!entry.crops) {
        entry.crops = APIService.getVideoTrackletCrops(matchId, trackletId)
            .then((response) => response.crops || [])
            .catch(() => [])
    }
    return entry.crops
}

// eslint-disable-next-line react-refresh/only-export-components
export function loadTrackletBbox(matchId, trackletId) {
    const entry = evidenceEntry(matchId, trackletId)
    if (!entry.bbox) {
        entry.bbox = APIService.getVideoTrackletBbox(matchId, trackletId)
            .then((response) => ({ boxes: response.boxes || [], available: !!response.available }))
            .catch(() => ({ boxes: [], available: false }))
    }
    return entry.bbox
}

// eslint-disable-next-line react-refresh/only-export-components
export function useBboxOverlay(videoRef, canvasRef, boxesRef, label) {
    useEffect(() => {
        let raf = 0
        let lastT = -1
        let lastW = 0
        let lastH = 0

        function draw() {
            const video = videoRef.current
            const canvas = canvasRef.current
            if (video && canvas) {
                const width = video.clientWidth
                const height = video.clientHeight
                const time = video.currentTime
                if (width && height && (time !== lastT || width !== lastW || height !== lastH)) {
                    lastT = time
                    lastW = width
                    lastH = height
                    if (canvas.width !== width) canvas.width = width
                    if (canvas.height !== height) canvas.height = height
                    const context = canvas.getContext('2d')
                    context.clearRect(0, 0, width, height)
                    const boxes = boxesRef.current
                    if (boxes.length && video.videoWidth && video.videoHeight) {
                        let low = 0
                        let high = boxes.length - 1
                        let best = -1
                        let bestDistance = Infinity
                        while (low <= high) {
                            const middle = (low + high) >> 1
                            const distance = Math.abs(boxes[middle][0] - time)
                            if (distance < bestDistance) {
                                bestDistance = distance
                                best = middle
                            }
                            if (boxes[middle][0] < time) low = middle + 1
                            else high = middle - 1
                        }
                        if (best >= 0 && bestDistance <= 0.25) {
                            const [, x1, y1, x2, y2] = boxes[best]
                            const scaleX = width / video.videoWidth
                            const scaleY = height / video.videoHeight
                            const boxX = x1 * scaleX
                            const boxY = y1 * scaleY
                            const boxWidth = (x2 - x1) * scaleX
                            const boxHeight = (y2 - y1) * scaleY
                            context.lineWidth = 3
                            context.strokeStyle = '#22d3ee'
                            context.strokeRect(boxX, boxY, boxWidth, boxHeight)
                            context.font = '600 13px ui-sans-serif, system-ui'
                            const textWidth = context.measureText(label).width + 8
                            context.fillStyle = '#22d3ee'
                            context.fillRect(boxX, Math.max(0, boxY - 18), textWidth, 18)
                            context.fillStyle = '#04222a'
                            context.fillText(label, boxX + 4, Math.max(12, boxY - 5))
                        }
                    }
                }
            }
            raf = requestAnimationFrame(draw)
        }

        raf = requestAnimationFrame(draw)
        return () => cancelAnimationFrame(raf)
    }, [boxesRef, canvasRef, label, videoRef])
}

function PlayerThumbnail({ matchId, trackletId, mediaToken, playerName }) {
    const [crop, setCrop] = useState(null)

    useEffect(() => {
        let alive = true
        if (!trackletId) return () => { alive = false }
        loadTrackletCrops(matchId, trackletId).then((crops) => {
            if (alive) setCrop(crops[0] || false)
        })
        return () => { alive = false }
    }, [matchId, trackletId])

    if (!crop || !mediaToken) {
        return (
            <div className="flex h-28 items-center justify-center bg-slate-950 text-slate-500">
                <Crosshair className="h-7 w-7" />
            </div>
        )
    }
    return (
        <img
            src={APIService.videoCropUrl(matchId, crop.file, mediaToken)}
            alt={`${playerName} on-camera crop`}
            className="h-28 w-full bg-slate-950 object-cover object-top"
            loading="lazy"
        />
    )
}

function ConfidenceBadge({ confidence }) {
    const classes = confidence === 'high'
        ? 'border-cyan-400/50 bg-cyan-400/10 text-cyan-700 dark:text-cyan-300'
        : confidence === 'low'
            ? 'border-amber-400/50 bg-amber-400/10 text-amber-700 dark:text-amber-300'
            : 'border-slate-400/50 bg-slate-400/10 text-slate-600 dark:text-slate-300'
    return <Badge variant="outline" className={classes}>{confidence}</Badge>
}

function ChainCropStrip({ matchId, trackletId, mediaToken, playerName }) {
    const [crops, setCrops] = useState(null)

    useEffect(() => {
        let alive = true
        loadTrackletCrops(matchId, trackletId).then((result) => {
            if (alive) setCrops(result.slice(0, 4))
        })
        return () => { alive = false }
    }, [matchId, trackletId])

    if (crops === null) {
        return <div className="flex h-20 items-center gap-2 text-xs text-slate-400"><Loader2 className="h-3.5 w-3.5 animate-spin" /> loading crops…</div>
    }
    if (!crops.length) return <p className="py-3 text-xs text-slate-400">No retained crops for this tracklet.</p>
    if (!mediaToken) return <p className="py-3 text-xs text-slate-400">media token…</p>

    return (
        <div className="flex gap-2 overflow-x-auto pb-1">
            {crops.map((crop) => (
                <img
                    key={crop.file}
                    src={APIService.videoCropUrl(matchId, crop.file, mediaToken)}
                    alt={`${playerName} identity crop`}
                    className="h-24 w-auto shrink-0 rounded-md border border-white/10 bg-black object-contain"
                    loading="lazy"
                />
            ))}
        </div>
    )
}

function VerifyIdentityPanel({ match, player, mediaToken, onAction, savingTrackletId }) {
    const [confirmDismissId, setConfirmDismissId] = useState(null)
    const roster = [...(match.roster || [])].sort((a, b) => a.jersey_number - b.jersey_number || a.id - b.id)
    const chains = player.chains || []

    return (
        <div className="border-t border-amber-400/25 bg-slate-950 p-3 text-slate-100 sm:p-5">
            <div className="mb-4 flex flex-wrap items-start justify-between gap-2">
                <div>
                    <p className="flex items-center gap-2 text-sm font-semibold"><ShieldCheck className="h-4 w-4 text-amber-300" /> Verify identity</p>
                    <p className="mt-1 text-xs text-slate-400">Check the crops and number reads, then correct this chain without leaving the reel.</p>
                </div>
                <Badge variant="outline" className="border-white/20 text-slate-300">{chains.length} chain{chains.length === 1 ? '' : 's'}</Badge>
            </div>

            <div className="space-y-4">
                {chains.map((chain) => {
                    const saving = savingTrackletId === chain.tracklet_id
                    const anySaving = savingTrackletId != null
                    return (
                        <section key={chain.tracklet_id} className="rounded-lg border border-white/10 bg-white/[0.035] p-3 sm:p-4">
                            <div className="flex flex-wrap items-center gap-2">
                                <span className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">tracklet {chain.tracklet_id}</span>
                                <ConfidenceBadge confidence={chain.confidence || 'unknown'} />
                                {chain.contaminated ? (
                                    <Badge variant="outline" className="border-amber-400/50 bg-amber-400/10 text-amber-200"><AlertTriangle className="mr-1 h-3 w-3" />mixed identity?</Badge>
                                ) : null}
                            </div>
                            <p className="mt-2 text-sm font-medium text-amber-100">{formatVoteSummary([chain])}</p>
                            <p className="mt-1 text-xs text-slate-400">Currently bound to <span className="text-slate-200">#{player.jersey_number} {player.player_name}</span></p>

                            <div className="mt-3">
                                <p className="mb-1.5 text-xs font-medium text-slate-300">Top crops</p>
                                <ChainCropStrip matchId={match.id} trackletId={chain.tracklet_id} mediaToken={mediaToken} playerName={player.player_name} />
                            </div>

                            <div className="mt-4 border-t border-white/10 pt-3">
                                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">Rebind to roster number</p>
                                <div className="mt-2 grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-6">
                                    {roster.map((entry) => {
                                        const current = entry.id === player.roster_entry_id
                                        const suggested = entry.jersey_number === chain.voted_number
                                        return (
                                            <button
                                                type="button"
                                                key={entry.id}
                                                disabled={anySaving || current}
                                                onClick={() => onAction(
                                                    { tracklet_id: chain.tracklet_id, roster_entry_id: entry.id, dismissed: false },
                                                    `Rebound tracklet ${chain.tracklet_id} to #${entry.jersey_number}.`,
                                                )}
                                                className={`relative min-h-14 rounded-md border px-2 py-2 text-left transition-colors disabled:cursor-not-allowed ${suggested ? 'border-amber-300 bg-amber-300/15 text-amber-50 hover:bg-amber-300/25' : current ? 'border-cyan-400/60 bg-cyan-400/10 text-cyan-100' : 'border-white/15 text-slate-200 hover:border-white/35 hover:bg-white/10'} ${anySaving && !current ? 'opacity-50' : ''}`}
                                            >
                                                <span className="block text-base font-bold tabular-nums">#{entry.jersey_number}</span>
                                                <span className="block truncate text-[10px] text-current/70">{current && suggested ? 'current · suggested' : current ? 'current' : suggested ? 'suggested' : entry.player_name}</span>
                                                {current ? <Check className="absolute right-1.5 top-1.5 h-3 w-3" /> : null}
                                            </button>
                                        )
                                    })}
                                </div>
                            </div>

                            <div className="mt-4 flex flex-wrap items-center gap-2">
                                <Button
                                    type="button"
                                    size="sm"
                                    variant="outline"
                                    disabled={anySaving}
                                    className="border-white/20 bg-transparent hover:bg-white/10 hover:text-white"
                                    onClick={() => onAction(
                                        { tracklet_id: chain.tracklet_id, roster_entry_id: null },
                                        `Unbound tracklet ${chain.tracklet_id}.`,
                                    )}
                                >
                                    {saving ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Unlink className="mr-1 h-4 w-4" />}
                                    Unbind
                                </Button>
                                <span className="text-xs text-slate-400">keeps the tracklet, removes the name</span>
                                <span className="hidden h-4 w-px bg-white/15 sm:block" aria-hidden="true" />
                                {confirmDismissId === chain.tracklet_id ? (
                                    <Button
                                        type="button"
                                        size="sm"
                                        variant="destructive"
                                        disabled={anySaving}
                                        onClick={() => onAction(
                                            { tracklet_id: chain.tracklet_id, dismissed: true },
                                            `Marked tracklet ${chain.tracklet_id} as not a player.`,
                                        )}
                                    >
                                        {saving ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <UserX className="mr-1 h-4 w-4" />}
                                        Confirm — not a player
                                    </Button>
                                ) : (
                                    <Button type="button" size="sm" variant="ghost" disabled={anySaving} className="text-rose-300 hover:bg-rose-400/10 hover:text-rose-200" onClick={() => setConfirmDismissId(chain.tracklet_id)}>
                                        <UserX className="mr-1 h-4 w-4" /> Not a player
                                    </Button>
                                )}
                                <span className="text-xs text-slate-400">for referees or sideline people</span>
                            </div>
                        </section>
                    )
                })}
                {!chains.length ? <p className="text-sm text-slate-400">No bound chain evidence is available for this reel.</p> : null}
            </div>
        </div>
    )
}

function ReelPlayer({ matchId, player, mediaToken, captions, onMediaError }) {
    const videoRef = useRef(null)
    const canvasRef = useRef(null)
    const boxesRef = useRef([])
    const remintCountRef = useRef(0)
    const [activeIdx, setActiveIdx] = useState(0)
    const [position, setPosition] = useState(player.windows[0]?.start_s || 0)
    const [playing, setPlaying] = useState(false)
    const [bbox, setBbox] = useState({ available: false, count: 0, loading: true })
    const [mediaFailed, setMediaFailed] = useState(false)
    const [ordering, setOrdering] = useState('chronological')
    const windows = useMemo(() => orderReelWindows(player.windows, ordering), [ordering, player.windows])
    const activeWindow = windows[activeIdx]
    const activeCaption = matchCaptionToWindow(activeWindow, captions, player)
    const activeCaptionPresentation = captionPresentation(activeCaption)
    const footageUrl = mediaToken ? APIService.videoFootageUrl(matchId, mediaToken) : null
    const overlayLabel = `#${player.jersey_number} ${player.player_name}`

    useBboxOverlay(videoRef, canvasRef, boxesRef, overlayLabel)

    useEffect(() => {
        let alive = true
        boxesRef.current = []
        if (!activeWindow) return () => { alive = false }
        loadTrackletBbox(matchId, activeWindow.tracklet_id).then((track) => {
            if (!alive) return
            boxesRef.current = track.boxes
            setBbox({ available: track.available, count: track.boxes.length, loading: false })
        })
        return () => { alive = false }
    }, [activeWindow, matchId])

    const jumpTo = (index, shouldPlay = true) => {
        const window = windows[index]
        const video = videoRef.current
        if (!window || !video) return
        if (index !== activeIdx) {
            boxesRef.current = []
            setBbox({ available: false, count: 0, loading: true })
        }
        setActiveIdx(index)
        video.currentTime = window.start_s
        setPosition(window.start_s)
        if (shouldPlay) video.play().then(() => setPlaying(true)).catch(() => {})
    }
    const changeOrdering = (nextOrdering) => {
        if (nextOrdering === ordering) return
        const nextWindows = orderReelWindows(player.windows, nextOrdering)
        setOrdering(nextOrdering)
        setActiveIdx(0)
        if (nextWindows[0] && videoRef.current) {
            videoRef.current.currentTime = nextWindows[0].start_s
            setPosition(nextWindows[0].start_s)
        }
    }

    const handleLoadedMetadata = () => jumpTo(activeIdx)
    const handleLoadedData = () => {
        remintCountRef.current = 0
        setMediaFailed(false)
    }
    const handleMediaError = () => {
        if (remintCountRef.current >= MAX_MEDIA_REMINTS) {
            setMediaFailed(true)
            return
        }
        remintCountRef.current += 1
        onMediaError?.()
    }
    const handleTimeUpdate = () => {
        const video = videoRef.current
        if (!video || !activeWindow) return
        setPosition(video.currentTime)
        if (video.currentTime < activeWindow.start_s - 0.5) {
            video.currentTime = activeWindow.start_s
            return
        }
        const next = nextWindowIndex(video.currentTime, windows, activeIdx)
        if (next === -1) {
            video.pause()
            video.currentTime = activeWindow.end_s
            setPosition(activeWindow.end_s)
            setPlaying(false)
        } else if (next !== activeIdx) {
            jumpTo(next)
        }
    }
    const togglePlay = () => {
        const video = videoRef.current
        if (!video) return
        if (video.paused) {
            if (activeWindow && video.currentTime >= activeWindow.end_s) video.currentTime = activeWindow.start_s
            video.play().then(() => setPlaying(true)).catch(() => {})
        } else {
            video.pause()
            setPlaying(false)
        }
    }

    if (!windows.length) {
        return <p className="border-t p-4 text-sm text-muted-foreground">No playable on-camera windows for this player.</p>
    }

    return (
        <div className="border-t border-cyan-400/20 bg-slate-950 p-3 text-slate-100 sm:p-5">
            <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_15rem]">
                <div>
                    <div className="relative overflow-hidden rounded-md border border-white/10 bg-black shadow-2xl">
                        {mediaFailed ? (
                            <div className="flex aspect-video items-center justify-center text-xs text-slate-400">footage unavailable</div>
                        ) : footageUrl ? (
                            <video
                                ref={videoRef}
                                src={footageUrl}
                                preload="metadata"
                                playsInline
                                muted
                                className="block w-full"
                                onLoadedMetadata={handleLoadedMetadata}
                                onLoadedData={handleLoadedData}
                                onTimeUpdate={handleTimeUpdate}
                                onPlay={() => setPlaying(true)}
                                onPause={() => setPlaying(false)}
                                onError={handleMediaError}
                            />
                        ) : (
                            <div className="flex aspect-video items-center justify-center text-xs text-slate-400">media token…</div>
                        )}
                        <canvas ref={canvasRef} className="pointer-events-none absolute inset-0" aria-hidden="true" />
                    </div>

                    <div className="mt-3 flex flex-wrap items-center gap-2">
                        <Button type="button" size="sm" variant="secondary" onClick={togglePlay} disabled={!footageUrl || mediaFailed}>
                            {playing ? <Pause className="mr-1 h-4 w-4" /> : <Play className="mr-1 h-4 w-4" />}
                            {playing ? 'Pause' : 'Play'}
                        </Button>
                        <Button type="button" size="icon" variant="outline" className="border-white/20 bg-transparent hover:bg-white/10 hover:text-white" onClick={() => jumpTo(activeIdx - 1)} disabled={activeIdx === 0} aria-label="Previous window">
                            <SkipBack className="h-4 w-4" />
                        </Button>
                        <Button type="button" size="icon" variant="outline" className="border-white/20 bg-transparent hover:bg-white/10 hover:text-white" onClick={() => jumpTo(activeIdx + 1)} disabled={activeIdx === windows.length - 1} aria-label="Next window">
                            <SkipForward className="h-4 w-4" />
                        </Button>
                        <span className="ml-auto text-xs tabular-nums text-slate-400">
                            {formatSeconds(position)} · window {activeIdx + 1}/{windows.length}
                        </span>
                    </div>
                    <p className="mt-2 flex items-center gap-1 text-xs text-slate-400">
                        <Crosshair className="h-3 w-3" />
                        {bbox.loading
                            ? 'loading tracking box…'
                            : bbox.available && bbox.count
                                ? `box follows this player (${bbox.count} detections)`
                                : 'box overlay unavailable for this window'}
                    </p>
                </div>

                <div>
                    <div className="mb-2 flex items-center justify-between gap-2">
                        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-300">On-camera playlist</p>
                        <div className="inline-flex rounded border border-white/10 bg-white/[0.04] p-0.5" aria-label="Playlist ordering">
                            {[
                                ['chronological', 'Chronological'],
                                ['ranked', 'Top moments'],
                            ].map(([value, label]) => (
                                <button
                                    type="button"
                                    key={value}
                                    onClick={() => changeOrdering(value)}
                                    aria-pressed={ordering === value}
                                    className={`rounded-sm px-2 py-1 text-[10px] font-medium transition-colors ${ordering === value ? 'bg-cyan-300 text-slate-950' : 'text-slate-400 hover:text-white'}`}
                                >
                                    {label}
                                </button>
                            ))}
                        </div>
                    </div>
                    <div className="space-y-1.5">
                        {windows.map((window, index) => {
                            const caption = matchCaptionToWindow(window, captions, player)
                            const presentation = captionPresentation(caption)
                            return (
                                <button
                                    type="button"
                                    key={`${window.start_s}-${window.tracklet_id}`}
                                    onClick={() => jumpTo(index)}
                                    aria-current={activeIdx === index ? 'true' : undefined}
                                    className={`w-full rounded border px-3 py-2 text-left text-xs tabular-nums transition-colors ${activeIdx === index ? 'border-cyan-300 bg-cyan-300/15 text-white' : 'border-white/10 text-slate-400 hover:border-white/30 hover:text-white'}`}
                                >
                                    <span className="flex items-center justify-between gap-2">
                                        <span>
                                            {ordering === 'ranked' ? `#${window.rank ?? '—'}` : `${window.rank <= 3 ? '★ ' : ''}${String(index + 1).padStart(2, '0')}`} · {formatSeconds(window.start_s)}
                                        </span>
                                        <span>{formatSeconds(window.end_s - window.start_s)}</span>
                                    </span>
                                    {caption && presentation ? (
                                        <span className="mt-1.5 flex flex-wrap gap-1 text-[9px] font-semibold uppercase tracking-wide">
                                            {presentation.showActionType ? <span className="rounded-sm bg-cyan-300/15 px-1.5 py-0.5 text-cyan-200">{caption.action_type?.replace('_', ' ')}</span> : <span className="rounded-sm bg-white/[0.06] px-1.5 py-0.5 text-slate-500">clip context</span>}
                                            {caption.visible_pitch_zone ? <span className="rounded-sm bg-white/10 px-1.5 py-0.5 text-slate-300">{caption.visible_pitch_zone} zone</span> : null}
                                        </span>
                                    ) : null}
                                </button>
                            )
                        })}
                    </div>
                </div>
            </div>
            {activeCaption && activeCaptionPresentation ? (
                <div className={`mt-4 border-l-2 px-3 py-2.5 ${activeCaptionPresentation.kind === 'context' ? 'border-slate-600 bg-white/[0.03]' : 'border-cyan-300 bg-cyan-300/[0.07]'}`}>
                    <p className={`text-[10px] font-semibold uppercase tracking-[0.17em] ${activeCaptionPresentation.kind === 'context' ? 'text-slate-500' : 'text-cyan-300'}`}>{activeCaptionPresentation.label}</p>
                    <p className={`mt-1 text-sm ${activeCaptionPresentation.kind === 'context' ? 'text-slate-400' : 'text-slate-200'}`}>{activeCaption.caption}</p>
                </div>
            ) : null}
        </div>
    )
}

function TeamOverview({ match, overview }) {
    const clusters = overview?.clusters || []
    const analysis = match.capture_meta?.qwen_analysis
    return (
        <div className="space-y-3">
            <div className="grid gap-2 sm:grid-cols-2">
                {clusters.map((team) => {
                    const label = team.is_ours === true ? 'Our side' : team.is_ours === false ? 'Opposition' : `Side ${team.cluster === 0 ? 'A' : 'B'}`
                    const color = team.is_ours === true ? match.our_kit_color : team.is_ours === false ? match.opponent_kit_color : null
                    return (
                        <div key={team.cluster} className="flex items-center gap-3 rounded-md border bg-muted/30 px-3 py-2.5">
                            <span className="h-9 w-2 rounded-full border border-black/10 bg-slate-400" style={color ? { backgroundColor: color } : undefined} aria-hidden="true" />
                            <div className="min-w-0 flex-1">
                                <p className="font-medium">{label}{color ? ` · ${color} kit` : ''}</p>
                                <p className="text-xs text-muted-foreground">
                                    {team.players.length} player{team.players.length === 1 ? '' : 's'} · {formatSeconds(team.total_visible_s)} visible
                                </p>
                            </div>
                        </div>
                    )
                })}
            </div>

            {overview?.qwen_analysis_present && analysis && (
                <details className="group rounded-md border bg-muted/20">
                    <summary className="flex cursor-pointer list-none items-center justify-between px-3 py-2.5 text-sm font-medium">
                        <span>AI match read (qualitative)</span>
                        <span className="flex items-center gap-2 text-xs font-normal text-muted-foreground">
                            sampled-frame qualitative analysis
                            <ChevronDown className="h-4 w-4 transition-transform group-open:rotate-180" />
                        </span>
                    </summary>
                    <div className="space-y-3 border-t px-3 py-3 text-sm">
                        {analysis.match_summary && <p>{analysis.match_summary}</p>}
                        {(analysis.team_analysis || []).map((team, index) => (
                            <div key={`${team.kit_color || 'team'}-${index}`} className="rounded border bg-background p-3">
                                <p className="font-medium">{team.is_ours === true ? 'Our side' : team.is_ours === false ? 'Opposition' : team.kit_color || 'Team'}{team.kit_color ? ` · ${team.kit_color} kit` : ''}</p>
                                {team.style && <p className="mt-1 text-muted-foreground">{team.style}</p>}
                                {team.strengths?.length ? <p className="mt-2"><span className="font-medium">Strengths:</span> {team.strengths.join(' · ')}</p> : null}
                                {team.weaknesses?.length ? <p className="mt-1"><span className="font-medium">Weaknesses:</span> {team.weaknesses.join(' · ')}</p> : null}
                            </div>
                        ))}
                    </div>
                </details>
            )}
        </div>
    )
}

export function PlayerReels({
    match,
    reel,
    mediaToken,
    openPlayerId,
    openVerifyPlayerId,
    onTogglePlayer,
    onToggleVerify,
    onIdentityAction,
    identitySavingTrackletId,
    onMediaError,
    onReviewUnassigned,
}) {
    const players = reel?.players || []
    const unassigned = reel?.unassigned || { count: 0, visible_s: 0 }

    return (
        <section className="overflow-hidden rounded-xl border bg-card shadow-sm" aria-labelledby="player-reels-heading">
            <div className="border-b bg-gradient-to-r from-slate-950 via-slate-900 to-cyan-950 px-4 py-5 text-slate-100 sm:px-6">
                <div className="flex flex-wrap items-end justify-between gap-3">
                    <div>
                        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-cyan-300">Film Room · contact sheet</p>
                        <h2 id="player-reels-heading" className="mt-1 text-xl font-semibold">Player reels</h2>
                    </div>
                    <p className="max-w-md text-xs text-slate-300">On-camera windows only — a panning camera does not see everyone.</p>
                </div>
            </div>

            <div className="space-y-5 p-4 sm:p-6">
                <TeamOverview match={match} overview={reel?.team_overview} />

                <button
                    type="button"
                    onClick={onReviewUnassigned}
                    className="flex w-full items-center gap-3 rounded-md border border-dashed border-amber-500/50 bg-amber-500/5 px-3 py-3 text-left transition-colors hover:bg-amber-500/10"
                >
                    <Users className="h-5 w-5 text-amber-600" />
                    <span className="text-sm">
                        <strong>{unassigned.count} unassigned identities · {formatSeconds(unassigned.visible_s)}</strong>
                        <span className="text-muted-foreground"> — tag them in review below</span>
                    </span>
                </button>

                {players.length ? (
                    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                        {players.map((player) => {
                            const reelOpen = openPlayerId === player.roster_entry_id
                            const verifyOpen = openVerifyPlayerId === player.roster_entry_id
                            const open = reelOpen || verifyOpen
                            const mismatch = mismatchBadge(player)
                            return (
                                <article key={player.roster_entry_id} className={`overflow-hidden rounded-lg border transition-shadow ${open ? 'border-cyan-500 shadow-lg shadow-cyan-500/10 sm:col-span-2 lg:col-span-3' : 'hover:shadow-md'}`}>
                                    <button
                                        type="button"
                                        onClick={() => onTogglePlayer(player.roster_entry_id)}
                                        aria-expanded={reelOpen}
                                        className={`grid w-full text-left ${open ? 'sm:grid-cols-[10rem_1fr]' : ''}`}
                                    >
                                        <PlayerThumbnail matchId={match.id} trackletId={player.thumbnail_tracklet_id ?? player.tracklet_ids[0]} mediaToken={mediaToken} playerName={player.player_name} />
                                        <div className="p-3">
                                            <div className="flex items-start justify-between gap-2">
                                                <div className="min-w-0">
                                                    <div className="flex flex-wrap items-center gap-1.5">
                                                        <p className="truncate font-semibold">#{player.jersey_number} {player.player_name}</p>
                                                        {mismatch ? (
                                                            <Badge variant="outline" className="border-amber-500/60 bg-amber-500/10 text-amber-700 dark:text-amber-300">
                                                                <AlertTriangle className="mr-1 h-3 w-3" />{mismatch}
                                                            </Badge>
                                                        ) : null}
                                                    </div>
                                                    {player.position && <p className="text-xs text-muted-foreground">{player.position}</p>}
                                                </div>
                                                <ConfidenceBadge confidence={player.confidence} />
                                            </div>
                                            <div className="mt-3 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
                                                <span className="flex items-center gap-1"><Clock3 className="h-3.5 w-3.5" /> {formatSeconds(player.total_visible_s)} visible</span>
                                                <span>{player.windows.length} window{player.windows.length === 1 ? '' : 's'}</span>
                                            </div>
                                        </div>
                                    </button>
                                    <div className="flex items-center justify-between gap-3 border-t bg-muted/20 px-3 py-2">
                                        <span className="text-[11px] text-muted-foreground">Open the reel to watch · verify to inspect each chain</span>
                                        <Button
                                            type="button"
                                            size="sm"
                                            variant={verifyOpen ? 'secondary' : 'outline'}
                                            onClick={() => onToggleVerify(player.roster_entry_id)}
                                            aria-expanded={verifyOpen}
                                            className={mismatch && !verifyOpen ? 'border-amber-500/50 text-amber-700 hover:bg-amber-500/10 dark:text-amber-300' : ''}
                                        >
                                            <ShieldCheck className="mr-1 h-4 w-4" /> Verify identity
                                        </Button>
                                    </div>
                                    {reelOpen ? <ReelPlayer matchId={match.id} player={player} mediaToken={mediaToken} captions={match.capture_meta?.qwen_analysis?.window_captions || []} onMediaError={onMediaError} /> : null}
                                    {verifyOpen ? (
                                        <VerifyIdentityPanel
                                            match={match}
                                            player={player}
                                            mediaToken={mediaToken}
                                            onAction={onIdentityAction}
                                            savingTrackletId={identitySavingTrackletId}
                                        />
                                    ) : null}
                                </article>
                            )
                        })}
                    </div>
                ) : (
                    <p className="text-sm text-muted-foreground">No player reels yet — bind identities in Tag review below.</p>
                )}
            </div>
        </section>
    )
}
