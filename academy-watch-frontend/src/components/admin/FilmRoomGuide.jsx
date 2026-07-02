import React, { useState } from 'react'
import {
    BookOpen,
    CheckCircle2,
    ChevronDown,
    ChevronRight,
    Crosshair,
    ListChecks,
    Play,
    Upload,
    Users,
} from 'lucide-react'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { cn } from '@/lib/utils'

// The canonical Film Room pipeline, in the order the operator works through it.
// Copy mirrors docs/film-room.md §4-9 so the in-app guide and the manual never drift.
const STEPS = [
    { Icon: Upload, title: 'Upload footage', body: 'Browser uploads the match video straight to storage (multi-GB, resumable) — keep the tab open until it finishes.' },
    { Icon: Crosshair, title: 'Mark the timeline', body: 'Type the kickoff time (required) — analysis starts there, so warm-ups aren’t processed. Add halftime + 2nd-half kickoff and the pipeline also skips the halftime gap, processing only the in-play minutes (no wasted GPU). Ten seconds of your input beats fragile auto-detection.' },
    { Icon: Users, title: 'Enter your squad', body: 'One player per line — “10 John Smith”. Your team only; opposition stays numbers-only (consent / safeguarding).' },
    { Icon: Play, title: 'Process (1 credit)', body: 'Queues the GPU job: detect players → track them → cluster the two teams by kit → read jersey numbers → chain fragments into one player. Most matches finish within a few hours.' },
    { Icon: Crosshair, title: 'Pick your side', body: 'Tell it which colour is your team. High-confidence players on your side are auto-tagged for you immediately — you just confirm or correct.' },
    { Icon: ListChecks, title: 'Tag review — the heart of it', body: 'Each detected player is a row. Expand ›  to watch that player’s looping video window with a cyan tracking box, then confirm (“Looks right”), reassign the number, mark “not a player”, or split a row that’s really two players. Then Save tags.' },
    { Icon: CheckCircle2, title: 'Finalize → report', body: 'Builds the per-player report from your confirmed identities. Re-finalizing never re-runs the GPU — it just re-aggregates, so correct freely and re-finalize.' },
]

// Plain-English meanings for the badges/terms that appear during review and in the report.
const GLOSSARY = [
    ['tracklet / chain', 'One detected player. A “chain” stitches fragments that share the same (team, number) into a single player.'],
    ['confident / uncertain', 'The model’s confidence in the jersey number it read for this player.'],
    ['mixed identity?', 'The chain’s frames disagree on the number (below 70% agreement) — treat with suspicion; auto-tagging is disabled for these. Often a Split fixes it.'],
    ['us / opposition', 'Which side a player is on, once you’ve picked your team.'],
    ['auto', 'Auto-tagged for you (high confidence). Confirm it or correct it.'],
    ['number agreement', 'How internally consistent this player’s number reads are across frames.'],
    ['identity confidence', 'On the report: you confirmed > high > low > unverified. A stat is only as trustworthy as the identity it hangs on.'],
    ['coverage / % of match', 'How much of the player we actually saw — a panning camera never sees everyone, so this is on-camera time, never a full-match total.'],
    ['pending calibration / beta', 'Distance / speed / sprints / heatmap need pitch calibration (not wired yet); touches is beta. Shown honestly as pending, never guessed.'],
]

const STORAGE_KEY = 'filmroom-guide-open'

/**
 * FilmRoomGuide — a collapsible "How Film Room works" panel: the end-to-end workflow plus a
 * glossary of the badges/terms. Remembers open/closed across visits (defaults open the first
 * time so a new operator gets oriented, then stays out of the way).
 */
export function FilmRoomGuide({ defaultOpen, className }) {
    // Read the saved preference once. Guarded: window.localStorage throws (not just returns
    // null) when storage is blocked — sandboxed iframes, "block all cookies", some webviews.
    const [open, setOpen] = useState(() => {
        try {
            const saved = window.localStorage.getItem(STORAGE_KEY)
            return saved == null ? (defaultOpen ?? true) : saved === '1'
        } catch { return defaultOpen ?? true }
    })
    // Persist only on an explicit user toggle — never on mount. Writing the default at mount
    // would let one page's default clobber the shared key and override the other page's
    // intended defaultOpen (the list opens by default, the match page starts collapsed).
    const toggle = () => setOpen((v) => {
        const next = !v
        try { window.localStorage.setItem(STORAGE_KEY, next ? '1' : '0') } catch { /* private mode */ }
        return next
    })

    return (
        <Card className={className}>
            <CardHeader className="cursor-pointer select-none" onClick={toggle}>
                <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                        <BookOpen className="h-4 w-4 text-muted-foreground" />
                        <span className="text-base font-semibold">How Film Room works</span>
                    </div>
                    <button
                        type="button"
                        aria-label={open ? 'Hide guide' : 'Show guide'}
                        aria-expanded={open}
                        className="text-muted-foreground hover:text-foreground"
                        onClick={(e) => { e.stopPropagation(); toggle() }}
                    >
                        {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                    </button>
                </div>
                {!open && (
                    <p className="text-xs text-muted-foreground">
                        Upload → mark kickoff → squad → process → pick your side → tag review → finalize. Tap to expand.
                    </p>
                )}
            </CardHeader>
            {open && (
                <CardContent className="space-y-5">
                    <ol className="space-y-3">
                        {STEPS.map((s, i) => (
                            <li key={s.title} className="flex gap-3">
                                <div className="flex flex-col items-center">
                                    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border bg-muted text-xs font-semibold tabular-nums">
                                        {i + 1}
                                    </div>
                                    {i < STEPS.length - 1 && <div className="mt-1 w-px flex-1 bg-border" />}
                                </div>
                                <div className="pb-1">
                                    <p className="flex items-center gap-1.5 text-sm font-medium">
                                        <s.Icon className="h-3.5 w-3.5 text-muted-foreground" /> {s.title}
                                    </p>
                                    <p className="text-xs text-muted-foreground leading-relaxed">{s.body}</p>
                                </div>
                            </li>
                        ))}
                    </ol>

                    <div className="rounded-lg border bg-muted/30 p-3">
                        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">What the badges mean</p>
                        <dl className="grid gap-x-4 gap-y-2 sm:grid-cols-2">
                            {GLOSSARY.map(([term, def]) => (
                                <div key={term}>
                                    <dt className="text-xs font-medium">{term}</dt>
                                    <dd className="text-xs text-muted-foreground leading-snug">{def}</dd>
                                </div>
                            ))}
                        </dl>
                    </div>

                    <p className="text-xs text-muted-foreground">
                        The model learns from your corrections (RLHF-style): confirming, reassigning, splitting and
                        “not a player” all feed the accuracy report and the fine-tune manifest. Opposition crops never
                        enter training.
                    </p>
                </CardContent>
            )}
        </Card>
    )
}

// match.status → current pipeline step (and whether it errored).
const STATUS_STEP = {
    created: 0,
    uploaded: 1,
    preflight: 2,
    queued: 2,
    processing: 2,
    needs_tagging: 3,
    finalized: 4,
    failed: 2,
    expired: 0,
}

const PROGRESS_STEPS = [
    { label: 'Upload', Icon: Upload, hint: 'Upload the video and mark kickoff.' },
    { label: 'Prepare', Icon: Users, hint: 'Enter your squad, then process (1 credit).' },
    { label: 'Process', Icon: Play, hint: 'GPU pipeline: detect, track, cluster teams, read numbers.' },
    { label: 'Tag review', Icon: ListChecks, hint: 'Confirm who is who.' },
    { label: 'Report', Icon: CheckCircle2, hint: 'Per-player report from your confirmed identities.' },
]

/**
 * MatchProgress — a horizontal stepper showing where this match is in the pipeline, so the
 * operator always knows what the current step is and what comes next.
 */
export function MatchProgress({ status, className }) {
    const current = STATUS_STEP[status] ?? 0
    const failed = status === 'failed'
    return (
        <nav aria-label="Match progress" className={cn('flex items-center', className)}>
            {PROGRESS_STEPS.map((s, i) => {
                const done = i < current
                const active = i === current
                const errored = active && failed
                return (
                    <React.Fragment key={s.label}>
                        <div className="flex flex-col items-center gap-1 px-1 text-center" title={s.hint}>
                            <div
                                className={cn(
                                    'flex h-8 w-8 items-center justify-center rounded-full border text-xs',
                                    errored && 'border-destructive bg-destructive/10 text-destructive',
                                    !errored && active && 'border-primary bg-primary text-primary-foreground',
                                    !errored && done && 'border-primary/40 bg-primary/10 text-primary',
                                    !active && !done && 'border-border bg-muted text-muted-foreground',
                                )}
                            >
                                {done ? <CheckCircle2 className="h-4 w-4" /> : <s.Icon className="h-4 w-4" />}
                            </div>
                            <span
                                className={cn(
                                    'text-[11px] leading-none whitespace-nowrap',
                                    active ? 'font-medium text-foreground' : 'text-muted-foreground',
                                )}
                            >
                                {s.label}
                            </span>
                        </div>
                        {i < PROGRESS_STEPS.length - 1 && (
                            // self-start + mt-4 puts the 1px connector at the circle's vertical
                            // centre (h-8 = 32px → 16px), not the centre of the taller circle+label column.
                            <div className={cn('mx-1 mt-4 h-px flex-1 min-w-3 self-start', i < current ? 'bg-primary/40' : 'bg-border')} />
                        )}
                    </React.Fragment>
                )
            })}
        </nav>
    )
}

export default FilmRoomGuide
