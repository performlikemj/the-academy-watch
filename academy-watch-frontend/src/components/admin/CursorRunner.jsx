import { useRef, useState } from 'react'
import { AlertCircle, CheckCircle2, Loader2, Play, ShieldAlert, Square } from 'lucide-react'

import { ConfirmGate } from '@/components/admin/ConfirmGate'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'

const MAX_EXAMPLES_SHOWN = 30

function formatExample(example) {
    if (example == null) return ''
    if (typeof example === 'string') return example
    if (typeof example !== 'object') return String(example)
    return Object.entries(example)
        .filter(([, v]) => v !== null && v !== undefined && typeof v !== 'object')
        .map(([k, v]) => `${k}: ${v}`)
        .join(' · ')
}

/**
 * CursorRunner — drives any cursor-paged admin operation. Public contract:
 *
 *   <CursorRunner
 *     title="Provenance repair (recompute-academy)"
 *     description="…"
 *     runPage={async ({ dryRun, cursor }) => {
 *       const r = await APIService.adminRecomputeAcademy({ dryRun, cursor, limit: 100 })
 *       return { nextCursor: r.next_cursor, counters: {…}, examples: r.examples, applied: r.applied }
 *     }}
 *     dryRunDefault={true}
 *     confirmWord="APPLY"     // required before the first non-dry page
 *   />
 *
 * Behavior: "Dry run (one page)" runs ONE page and renders counters +
 * examples; "Run all (dry)" loops pages until nextCursor is null,
 * accumulating counters with a progress line; switching dry-run OFF
 * requires ConfirmGate(confirmWord); the live run loops with the same
 * progress UI; errors surface inline and pause the loop with a
 * resume-from-cursor field.
 */
export function CursorRunner({
    title,
    description,
    runPage,
    dryRunDefault = true,
    confirmWord = 'APPLY',
}) {
    const [dryRun, setDryRun] = useState(dryRunDefault !== false)
    const [confirmOpen, setConfirmOpen] = useState(false)
    const [running, setRunning] = useState(false)
    const [pagesRun, setPagesRun] = useState(0)
    const [cursor, setCursor] = useState(0)
    const [counters, setCounters] = useState(null)
    const [examples, setExamples] = useState([])
    const [error, setError] = useState(null)
    const [done, setDone] = useState(false)
    const [lastApplied, setLastApplied] = useState(null)
    const [lastRunWasDry, setLastRunWasDry] = useState(null)
    const [resumeCursor, setResumeCursor] = useState('')
    const stopRef = useRef(false)

    const resetRunState = () => {
        setPagesRun(0)
        setCounters(null)
        setExamples([])
        setError(null)
        setDone(false)
        setLastApplied(null)
    }

    const mergeCounters = (prev, next) => {
        const merged = { ...(prev || {}) }
        for (const [key, value] of Object.entries(next || {})) {
            const num = Number(value)
            if (Number.isFinite(num)) {
                merged[key] = (Number(merged[key]) || 0) + num
            } else if (merged[key] === undefined) {
                merged[key] = value
            }
        }
        return merged
    }

    const runOnePage = async ({ isDry, startCursor }) => {
        const result = (await runPage({ dryRun: isDry, cursor: startCursor })) || {}
        setPagesRun((p) => p + 1)
        setCounters((prev) => mergeCounters(prev, result.counters))
        if (Array.isArray(result.examples) && result.examples.length) {
            setExamples((prev) => [...prev, ...result.examples].slice(0, MAX_EXAMPLES_SHOWN))
        }
        if (result.applied !== undefined) setLastApplied(Boolean(result.applied))
        return result.nextCursor ?? null
    }

    const run = async ({ loop, startCursor = 0, forceDry = false }) => {
        if (running || typeof runPage !== 'function') return
        const isDry = forceDry || dryRun
        stopRef.current = false
        setRunning(true)
        setLastRunWasDry(isDry)
        resetRunState()
        setCursor(startCursor)

        let currentCursor = startCursor
        try {
            for (;;) {
                const nextCursor = await runOnePage({ isDry, startCursor: currentCursor })
                if (nextCursor === null || nextCursor === undefined) {
                    setDone(true)
                    break
                }
                // Defensive: a cursor that does not advance would loop forever.
                if (nextCursor === currentCursor) {
                    setError(`Cursor did not advance (stuck at ${currentCursor}); stopping.`)
                    break
                }
                currentCursor = nextCursor
                setCursor(nextCursor)
                if (!loop) break
                if (stopRef.current) break
            }
        } catch (err) {
            setError(err?.message || 'Page failed')
            setResumeCursor(String(currentCursor))
        } finally {
            setRunning(false)
        }
    }

    const resume = async () => {
        const parsed = Number.parseInt(resumeCursor, 10)
        const startCursor = Number.isFinite(parsed) && parsed >= 0 ? parsed : cursor
        await run({ loop: true, startCursor })
    }

    const handleDryRunToggle = (next) => {
        if (running) return
        if (next) {
            setDryRun(true)
        } else {
            // Switching dry-run OFF requires typing the confirm word.
            setConfirmOpen(true)
        }
    }

    const counterEntries = Object.entries(counters || {})

    return (
        <Card data-testid="cursor-runner">
            <CardHeader>
                <CardTitle className="text-base">{title}</CardTitle>
                {description && <CardDescription>{description}</CardDescription>}
            </CardHeader>
            <CardContent className="space-y-4">
                <div className="flex flex-wrap items-center gap-3">
                    <div className="flex items-center gap-2 rounded-lg border bg-muted/30 px-3 py-2">
                        <Switch
                            checked={dryRun}
                            onCheckedChange={handleDryRunToggle}
                            disabled={running}
                            data-testid="cursor-runner-dryrun-toggle"
                            aria-label="Dry run mode"
                        />
                        <span className="text-sm font-medium">
                            {dryRun ? 'Dry run (no writes)' : (
                                <span className="text-destructive flex items-center gap-1">
                                    <ShieldAlert className="h-4 w-4" /> LIVE — writes enabled
                                </span>
                            )}
                        </span>
                    </div>

                    <Button
                        size="sm"
                        variant="outline"
                        data-testid="cursor-runner-dry"
                        disabled={running}
                        onClick={() => run({ loop: false, forceDry: true })}
                    >
                        <Play className="h-4 w-4" /> Dry run (one page)
                    </Button>
                    <Button
                        size="sm"
                        variant="outline"
                        data-testid="cursor-runner-dry-all"
                        disabled={running}
                        onClick={() => run({ loop: true, forceDry: true })}
                    >
                        <Play className="h-4 w-4" /> Run all (dry)
                    </Button>
                    <Button
                        size="sm"
                        variant="destructive"
                        data-testid="cursor-runner-live"
                        disabled={running || dryRun}
                        onClick={() => run({ loop: true })}
                    >
                        <Play className="h-4 w-4" /> Run all (live)
                    </Button>
                    {running && (
                        <Button
                            size="sm"
                            variant="ghost"
                            data-testid="cursor-runner-stop"
                            onClick={() => { stopRef.current = true }}
                        >
                            <Square className="h-4 w-4" /> Stop after page
                        </Button>
                    )}
                </div>

                <div
                    className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground"
                    data-testid="cursor-runner-progress"
                >
                    {running && <Loader2 className="h-4 w-4 animate-spin text-primary" />}
                    <span>
                        {running
                            ? `Running ${lastRunWasDry ? 'dry' : 'LIVE'}… pages: ${pagesRun}, cursor: ${cursor}`
                            : pagesRun > 0
                                ? `${done ? 'Complete' : 'Paused'} — pages: ${pagesRun}, cursor: ${cursor}`
                                : 'Not run yet.'}
                    </span>
                    {done && !running && <CheckCircle2 className="h-4 w-4 text-emerald-600" />}
                    {lastApplied !== null && !running && (
                        <Badge variant={lastApplied ? 'default' : 'secondary'}>
                            {lastApplied ? 'applied' : 'not applied (dry run)'}
                        </Badge>
                    )}
                </div>

                {error && (
                    <Alert className="border-rose-500 bg-rose-50">
                        <AlertCircle className="h-4 w-4 text-rose-600" />
                        <AlertDescription className="text-rose-800 space-y-2">
                            <div>Loop paused: {error}</div>
                            <div className="flex items-center gap-2">
                                <Label htmlFor="cursor-runner-resume" className="text-xs whitespace-nowrap">
                                    Resume from cursor
                                </Label>
                                <Input
                                    id="cursor-runner-resume"
                                    data-testid="cursor-runner-resume"
                                    className="h-8 w-32 bg-white"
                                    value={resumeCursor}
                                    onChange={(e) => setResumeCursor(e.target.value)}
                                    placeholder={String(cursor)}
                                />
                                <Button size="sm" variant="outline" disabled={running} onClick={resume}>
                                    Resume
                                </Button>
                            </div>
                        </AlertDescription>
                    </Alert>
                )}

                {counterEntries.length > 0 && (
                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2" data-testid="cursor-runner-counters">
                        {counterEntries.map(([key, value]) => (
                            <div key={key} className="rounded-lg border bg-muted/30 p-2">
                                <div className="text-lg font-semibold">{String(value)}</div>
                                <div className="text-xs text-muted-foreground break-all">{key.replaceAll('_', ' ')}</div>
                            </div>
                        ))}
                    </div>
                )}

                {examples.length > 0 && (
                    <div className="space-y-1" data-testid="cursor-runner-examples">
                        <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                            Examples (first {Math.min(examples.length, MAX_EXAMPLES_SHOWN)})
                        </div>
                        <ul className="max-h-56 overflow-y-auto rounded-md border bg-muted/20 divide-y text-xs">
                            {examples.map((example, idx) => (
                                <li key={idx} className="px-3 py-1.5 font-mono break-all">
                                    {formatExample(example)}
                                </li>
                            ))}
                        </ul>
                    </div>
                )}
            </CardContent>

            <ConfirmGate
                open={confirmOpen}
                onOpenChange={setConfirmOpen}
                title={`Disable dry-run for: ${title}`}
                description="The next run will WRITE changes. Dry-run counters look identical to live counters — verify applied state afterwards."
                confirmWord={confirmWord}
                confirmLabel="Enable live mode"
                destructive
                onConfirm={() => setDryRun(false)}
            />
        </Card>
    )
}

export default CursorRunner
