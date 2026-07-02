import React, { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'
import { Coins, Loader2, Plus, Video, Wrench } from 'lucide-react'
import { APIService } from '@/lib/api'
import { FilmRoomGuide } from '@/components/admin/FilmRoomGuide'
import { HelpHint } from '@/components/ui/help-hint'

const STATUS_VARIANTS = {
    created: 'outline',
    uploaded: 'secondary',
    preflight: 'secondary',
    queued: 'secondary',
    processing: 'default',
    needs_tagging: 'default',
    finalized: 'default',
    failed: 'destructive',
    expired: 'outline',
}

export function VideoStatusBadge({ status }) {
    return <Badge variant={STATUS_VARIANTS[status] || 'outline'}>{(status || '').replace(/_/g, ' ')}</Badge>
}

export function AdminVideo() {
    const navigate = useNavigate()
    const [teams, setTeams] = useState([])
    const [teamId, setTeamId] = useState('')
    const [matches, setMatches] = useState([])
    const [balance, setBalance] = useState(null)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState(null)

    const [createOpen, setCreateOpen] = useState(false)
    const [creating, setCreating] = useState(false)
    const [form, setForm] = useState({ opponent_name: '', match_date: '', competition: '', our_kit_color: '', opponent_kit_color: '' })

    const [grantOpen, setGrantOpen] = useState(false)
    const [grantDelta, setGrantDelta] = useState(1)
    const [grantNote, setGrantNote] = useState('')
    const [granting, setGranting] = useState(false)

    const [reaping, setReaping] = useState(false)
    const [reapResult, setReapResult] = useState(null)

    useEffect(() => {
        APIService.getTeams()
            .then((res) => setTeams(res?.teams || (Array.isArray(res) ? res : [])))
            .catch((err) => setError(err.message))
    }, [])

    const loadMatches = useCallback(async (tid) => {
        if (!tid) return
        setLoading(true)
        setError(null)
        try {
            const res = await APIService.getTeamVideoMatches(tid)
            setMatches(res.matches || [])
            setBalance(res.credit_balance)
        } catch (err) {
            setError(err.message)
        } finally {
            setLoading(false)
        }
    }, [])

    useEffect(() => {
        // Data fetch on team change — the loader owns loading/error state.
        // eslint-disable-next-line react-hooks/set-state-in-effect
        if (teamId) loadMatches(teamId)
    }, [teamId, loadMatches])

    const handleCreate = async () => {
        setCreating(true)
        setError(null)
        try {
            const payload = { team_id: Number(teamId) }
            for (const [key, value] of Object.entries(form)) {
                if (value) payload[key] = value
            }
            const match = await APIService.createVideoMatch(payload)
            setCreateOpen(false)
            navigate(`/admin/video/${match.id}`)
        } catch (err) {
            setError(err.message)
        } finally {
            setCreating(false)
        }
    }

    const handleReapStale = async () => {
        setReaping(true)
        setError(null)
        try {
            const res = await APIService.adminVideoReapStaleJobs()
            setReapResult(Number(res?.stale_failed ?? 0))
        } catch (err) {
            setError(err.message)
        } finally {
            setReaping(false)
        }
    }

    const handleGrant = async () => {
        setGranting(true)
        setError(null)
        try {
            const res = await APIService.grantVideoCredits(Number(teamId), { delta: Number(grantDelta), note: grantNote || undefined })
            setBalance(res.balance)
            setGrantOpen(false)
            setGrantNote('')
        } catch (err) {
            setError(err.message)
        } finally {
            setGranting(false)
        }
    }

    return (
        <div className="space-y-6">
            <header className="flex flex-wrap items-center justify-between gap-3">
                <div>
                    <h1 className="text-2xl font-bold flex items-center gap-2"><Video className="h-6 w-6" /> Film Room</h1>
                    <p className="text-sm text-muted-foreground">Match uploads, processing and tag review (concierge)</p>
                </div>
                <div className="flex items-center gap-2">
                    {balance !== null && (
                        <Badge variant="secondary" className="text-sm">
                            <Coins className="h-3.5 w-3.5 mr-1" /> {balance} credit{balance === 1 ? '' : 's'}
                            <HelpHint label="Credits" className="ml-1" iconClassName="h-3 w-3">
                                One credit is spent per match when you press Process. Failed jobs can be refunded.
                                Grant credits to the paying club with the button on the right.
                            </HelpHint>
                        </Badge>
                    )}
                    <Button variant="outline" size="sm" disabled={!teamId} onClick={() => setGrantOpen(true)}>Grant credits</Button>
                    <Button size="sm" disabled={!teamId} onClick={() => setCreateOpen(true)}>
                        <Plus className="h-4 w-4 mr-1" /> New match
                    </Button>
                </div>
            </header>

            {error && <p className="text-sm text-destructive">{error}</p>}

            <FilmRoomGuide />

            <Card>
                <CardHeader>
                    <CardTitle className="text-base">Team</CardTitle>
                    <CardDescription>Video matches belong to the paying club</CardDescription>
                </CardHeader>
                <CardContent>
                    <Select value={teamId} onValueChange={setTeamId}>
                        <SelectTrigger className="w-full sm:w-96">
                            <SelectValue placeholder="Select a team…" />
                        </SelectTrigger>
                        <SelectContent>
                            {teams.map((t) => (
                                <SelectItem key={t.id} value={String(t.id)}>{t.name}</SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </CardContent>
            </Card>

            {teamId && (
                <Card>
                    <CardHeader>
                        <CardTitle className="text-base">Matches</CardTitle>
                    </CardHeader>
                    <CardContent>
                        {loading ? (
                            <div className="flex items-center gap-2 text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Loading…</div>
                        ) : matches.length === 0 ? (
                            <p className="text-sm text-muted-foreground">No video matches yet — create one to start.</p>
                        ) : (
                            <div className="space-y-2">
                                {matches.map((m) => (
                                    <button
                                        key={m.id}
                                        type="button"
                                        onClick={() => navigate(`/admin/video/${m.id}`)}
                                        className="w-full flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3 text-left hover:bg-accent"
                                    >
                                        <div className="min-w-0">
                                            <div className="font-medium truncate">
                                                vs {m.opponent_name || 'Unknown opponent'}
                                                {m.match_date ? <span className="text-muted-foreground font-normal"> · {m.match_date}</span> : null}
                                            </div>
                                            <div className="text-xs text-muted-foreground">
                                                #{m.id}{m.competition ? ` · ${m.competition}` : ''}
                                                {m.job?.stage && m.status === 'processing' ? ` · ${m.job.stage}` : ''}
                                            </div>
                                        </div>
                                        <VideoStatusBadge status={m.status} />
                                    </button>
                                ))}
                            </div>
                        )}
                    </CardContent>
                </Card>
            )}

            <Card>
                <CardHeader>
                    <CardTitle className="text-base flex items-center gap-2"><Wrench className="h-4 w-4" /> Maintenance</CardTitle>
                    <CardDescription>
                        GPU jobs stuck in processing for over 6 hours are marked failed so their matches can be requeued.
                        Nothing runs this on a schedule — poke it manually when a job looks stuck.
                    </CardDescription>
                </CardHeader>
                <CardContent className="flex flex-wrap items-center gap-3">
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={handleReapStale}
                        disabled={reaping}
                        data-testid="video-reap-stale-jobs"
                    >
                        {reaping && <Loader2 className="h-4 w-4 mr-1 animate-spin" />} Reap stale jobs
                    </Button>
                    {reapResult !== null && (
                        <Badge
                            variant={reapResult > 0 ? 'destructive' : 'secondary'}
                            data-testid="video-reap-stale-result"
                        >
                            {reapResult > 0
                                ? `${reapResult} stale job${reapResult === 1 ? '' : 's'} marked failed`
                                : 'No stale jobs found'}
                        </Badge>
                    )}
                </CardContent>
            </Card>

            <Dialog open={createOpen} onOpenChange={setCreateOpen}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>New video match</DialogTitle>
                        <DialogDescription>Creates the match shell and an upload link.</DialogDescription>
                    </DialogHeader>
                    <div className="space-y-3">
                        <div>
                            <Label htmlFor="vm-opponent">Opponent</Label>
                            <Input id="vm-opponent" value={form.opponent_name} onChange={(e) => setForm({ ...form, opponent_name: e.target.value })} placeholder="AFC Wyke" />
                        </div>
                        <div className="grid grid-cols-2 gap-3">
                            <div>
                                <Label htmlFor="vm-date">Match date</Label>
                                <Input id="vm-date" type="date" value={form.match_date} onChange={(e) => setForm({ ...form, match_date: e.target.value })} />
                            </div>
                            <div>
                                <Label htmlFor="vm-comp">Competition</Label>
                                <Input id="vm-comp" value={form.competition} onChange={(e) => setForm({ ...form, competition: e.target.value })} placeholder="League / friendly" />
                            </div>
                        </div>
                        <div className="grid grid-cols-2 gap-3">
                            <div>
                                <Label htmlFor="vm-kit">Our kit color</Label>
                                <Input id="vm-kit" value={form.our_kit_color} onChange={(e) => setForm({ ...form, our_kit_color: e.target.value })} placeholder="red" />
                            </div>
                            <div>
                                <Label htmlFor="vm-okit">Opponent kit color</Label>
                                <Input id="vm-okit" value={form.opponent_kit_color} onChange={(e) => setForm({ ...form, opponent_kit_color: e.target.value })} placeholder="blue" />
                            </div>
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setCreateOpen(false)}>Cancel</Button>
                        <Button onClick={handleCreate} disabled={creating}>
                            {creating && <Loader2 className="h-4 w-4 mr-1 animate-spin" />} Create
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            <Dialog open={grantOpen} onOpenChange={setGrantOpen}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Grant credits</DialogTitle>
                        <DialogDescription>Concierge credit movement (Stripe checkout arrives in Phase B). Negative values remove credits.</DialogDescription>
                    </DialogHeader>
                    <div className="space-y-3">
                        <div>
                            <Label htmlFor="vm-grant-delta">Credits</Label>
                            <Input id="vm-grant-delta" type="number" value={grantDelta} onChange={(e) => setGrantDelta(e.target.value)} />
                        </div>
                        <div>
                            <Label htmlFor="vm-grant-note">Note</Label>
                            <Input id="vm-grant-note" value={grantNote} onChange={(e) => setGrantNote(e.target.value)} placeholder="paid via invoice #…" />
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setGrantOpen(false)}>Cancel</Button>
                        <Button onClick={handleGrant} disabled={granting || !Number(grantDelta)}>
                            {granting && <Loader2 className="h-4 w-4 mr-1 animate-spin" />} Apply
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    )
}

export default AdminVideo
