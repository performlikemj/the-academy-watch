import { useState } from 'react'
import {
    ArrowRight,
    ArrowRightLeft,
    CheckCircle2,
    Eye,
    Loader2,
} from 'lucide-react'

import TeamSelect from '@/components/ui/TeamSelect'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'
import {
    Table,
    TableBody,
    TableCaption,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table'
import { Textarea } from '@/components/ui/textarea'
import { APIService } from '@/lib/api'
import { STATUS_BADGE_CLASSES } from '@/lib/theme-constants'

const TRANSFER_TYPES = [
    { value: 'signed', label: 'Signed' },
    { value: 'loan', label: 'Loan' },
    { value: 'loan_return', label: 'Loan return' },
    { value: 'released', label: 'Released' },
    { value: 'sold', label: 'Sold' },
]

function localDateValue() {
    const now = new Date()
    const localTime = new Date(now.getTime() - now.getTimezoneOffset() * 60_000)
    return localTime.toISOString().slice(0, 10)
}

function initialForm(player) {
    return {
        player_api_id: player?.player_api_id ? String(player.player_api_id) : '',
        from_team_api_id: '',
        to_team_api_id: '',
        to_team_name: '',
        destination_team_db_id: null,
        transfer_type: 'signed',
        effective_date: localDateValue(),
        fee_text: '',
        source_note: '',
    }
}

function positiveInteger(value, label, { required = false } = {}) {
    const normalized = String(value ?? '').trim()
    if (!normalized) {
        if (required) throw new Error(`${label} is required`)
        return null
    }

    const parsed = Number(normalized)
    if (!Number.isInteger(parsed) || parsed <= 0) {
        throw new Error(`${label} must be a positive integer`)
    }
    return parsed
}

function payloadFromForm(form) {
    const sourceNote = form.source_note.trim()
    if (!sourceNote) throw new Error('Source note is required')
    if (!form.effective_date) throw new Error('Effective date is required')

    const payload = {
        player_api_id: positiveInteger(form.player_api_id, 'Player API ID', { required: true }),
        transfer_type: form.transfer_type,
        effective_date: form.effective_date,
        source_note: sourceNote,
        dry_run: true,
    }

    const fromTeamApiId = positiveInteger(form.from_team_api_id, 'From team API ID')
    const toTeamApiId = positiveInteger(form.to_team_api_id, 'To team API ID')
    const toTeamName = form.to_team_name.trim()
    const feeText = form.fee_text.trim()

    if (fromTeamApiId) payload.from_team_api_id = fromTeamApiId
    if (toTeamApiId) payload.to_team_api_id = toTeamApiId
    if (!toTeamApiId && toTeamName) payload.to_team_name = toTeamName
    if (feeText) payload.fee_text = feeText

    return payload
}

function formatStatus(status) {
    if (!status) return 'Not set'
    return String(status)
        .replaceAll('_', ' ')
        .replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function StatusPill({ status }) {
    if (!status) {
        return <span className="text-xs text-muted-foreground">Not set</span>
    }
    return (
        <Badge variant="outline" className={STATUS_BADGE_CLASSES[status] || undefined}>
            {formatStatus(status)}
        </Badge>
    )
}

function StatusTransition({ oldValue, newValue }) {
    return (
        <div className="flex min-w-max items-center gap-2">
            <StatusPill status={oldValue} />
            <ArrowRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
            <StatusPill status={newValue} />
        </div>
    )
}

function ActiveTransition({ oldValue, newValue }) {
    const label = (value) => (value ? 'Active' : 'Inactive')
    return (
        <div className="flex min-w-max items-center gap-2 text-sm">
            <span>{label(oldValue)}</span>
            <ArrowRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
            <span className="font-medium">{label(newValue)}</span>
        </div>
    )
}

function transferSummary(transfer) {
    if (!transfer) return null
    const from = transfer.from_team?.name || transfer.from_team?.api_id
    const to = transfer.to_team?.name || transfer.to_team?.api_id

    if (from && to) return `${from} → ${to}`
    if (from) return `${from} → no destination`
    if (to) return `Destination: ${to}`
    return 'No club destination recorded'
}

export function ManualTransferDialog({
    open,
    onOpenChange,
    teams,
    initialPlayer = null,
    onCommitted,
}) {
    const [form, setForm] = useState(() => initialForm(initialPlayer))
    const [preview, setPreview] = useState(null)
    const [previewPayload, setPreviewPayload] = useState(null)
    const [commitResult, setCommitResult] = useState(null)
    const [busy, setBusy] = useState(null)
    const [error, setError] = useState(null)

    const clearPreview = () => {
        setPreview(null)
        setPreviewPayload(null)
        setCommitResult(null)
        setError(null)
    }

    const updateField = (field, value) => {
        setForm((current) => ({ ...current, [field]: value }))
        clearPreview()
    }

    const updateTransferType = (transferType) => {
        setForm((current) => ({
            ...current,
            transfer_type: transferType,
            ...(transferType === 'released'
                ? {
                    to_team_api_id: '',
                    to_team_name: '',
                    destination_team_db_id: null,
                }
                : {}),
        }))
        clearPreview()
    }

    const selectDestinationTeam = (teamDbId) => {
        const selectedTeam = teams.find((team) => team.id === teamDbId)
        setForm((current) => ({
            ...current,
            destination_team_db_id: teamDbId,
            to_team_api_id: selectedTeam?.team_id ? String(selectedTeam.team_id) : '',
            to_team_name: '',
        }))
        clearPreview()
    }

    const handlePreview = async (event) => {
        event.preventDefault()
        setBusy('preview')
        setError(null)

        try {
            const payload = payloadFromForm(form)
            const response = await APIService.adminRecordManualTransfer(payload)
            setPreviewPayload(payload)
            setPreview(response)
        } catch (requestError) {
            setError(requestError?.body?.error || requestError?.message || 'Unable to preview this transfer')
        } finally {
            setBusy(null)
        }
    }

    const handleCommit = async () => {
        if (!previewPayload) return
        setBusy('commit')
        setError(null)

        try {
            const response = await APIService.adminRecordManualTransfer({
                ...previewPayload,
                dry_run: false,
            })
            setCommitResult(response)
            onCommitted?.(response)
        } catch (requestError) {
            setError(requestError?.body?.error || requestError?.message || 'Unable to record this transfer')
        } finally {
            setBusy(null)
        }
    }

    const handleOpenChange = (nextOpen) => {
        if (busy && !nextOpen) return
        onOpenChange(nextOpen)
    }

    const affectedRows = preview?.affected_rows || []
    const canCommit = Boolean(previewPayload)

    return (
        <Dialog open={open} onOpenChange={handleOpenChange}>
            <DialogContent className="sm:max-w-4xl">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <ArrowRightLeft className="h-5 w-5 text-primary" aria-hidden="true" />
                        Record transfer
                    </DialogTitle>
                    <DialogDescription>
                        Add one known signing or move without running an API-Football sync. Every change is previewed
                        through the same transfer classifier before it is written.
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4">
                    {error ? (
                        <Alert className="border-rose-300 bg-rose-50">
                            <AlertDescription className="text-rose-800">{error}</AlertDescription>
                        </Alert>
                    ) : null}

                    {commitResult ? (
                        <div className="space-y-5">
                            <div
                                role="status"
                                aria-live="polite"
                                className="rounded-lg border border-emerald-200 bg-emerald-50 p-4"
                            >
                                <div className="flex items-start gap-3">
                                    <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-emerald-700" aria-hidden="true" />
                                    <div>
                                        <p className="font-semibold text-emerald-900">
                                            {commitResult.idempotent ? 'Transfer already recorded' : 'Transfer recorded'}
                                        </p>
                                        <p className="mt-1 text-sm text-emerald-800">
                                            {commitResult.idempotent
                                                ? 'The existing event was reused; no duplicate was created.'
                                                : 'Tracked-player and journey surfaces now reflect this event.'}
                                        </p>
                                    </div>
                                </div>
                            </div>

                            {commitResult.record_ids ? (
                                <dl className="grid gap-3 rounded-lg border bg-muted/20 p-4 text-sm sm:grid-cols-2">
                                    <div>
                                        <dt className="text-muted-foreground">Transfer event ID</dt>
                                        <dd className="font-mono font-medium">
                                            {commitResult.record_ids.transfer_event_id ?? '—'}
                                        </dd>
                                    </div>
                                    <div>
                                        <dt className="text-muted-foreground">Audit event ID</dt>
                                        <dd className="font-mono font-medium">
                                            {commitResult.record_ids.audit_event_id ?? '—'}
                                        </dd>
                                    </div>
                                </dl>
                            ) : null}

                            <DialogFooter>
                                <Button type="button" onClick={() => onOpenChange(false)}>
                                    Close
                                </Button>
                            </DialogFooter>
                        </div>
                    ) : preview ? (
                        <div className="space-y-4">
                            <div
                                role="status"
                                aria-live="polite"
                                className="rounded-lg border border-amber-200 bg-amber-50/70 p-4"
                            >
                                <div className="flex flex-wrap items-center justify-between gap-2">
                                    <div>
                                        <p className="text-sm font-semibold text-amber-950">
                                            {preview.idempotent ? 'Existing transfer found' : 'Dry-run preview'}
                                        </p>
                                        <p className="mt-1 text-sm text-amber-900">
                                            {transferSummary(preview.transfer)}
                                        </p>
                                        {preview.idempotent ? (
                                            <p className="mt-1 text-xs text-amber-800">
                                                Confirming reuses the stored transfer and appends this source note as
                                                corroborating audit evidence.
                                            </p>
                                        ) : null}
                                    </div>
                                    {preview.transfer?.destination_resolution ? (
                                        <Badge
                                            variant="outline"
                                            className="border-amber-300 bg-white/70 text-amber-900"
                                        >
                                            Resolved via{' '}
                                            {String(preview.transfer.destination_resolution).replaceAll('_', ' ')}
                                        </Badge>
                                    ) : null}
                                </div>
                            </div>

                            <dl className="grid gap-x-6 gap-y-3 rounded-lg border bg-muted/20 p-4 text-sm sm:grid-cols-2">
                                <div>
                                    <dt className="text-muted-foreground">Transfer type</dt>
                                    <dd className="font-medium">{formatStatus(preview.transfer?.transfer_type)}</dd>
                                </div>
                                <div>
                                    <dt className="text-muted-foreground">Effective date</dt>
                                    <dd className="font-medium">{preview.transfer?.effective_date || '—'}</dd>
                                </div>
                                <div>
                                    <dt className="text-muted-foreground">Fee</dt>
                                    <dd className="font-medium">{preview.transfer?.fee_text || 'Not recorded'}</dd>
                                </div>
                                <div className="sm:col-span-2">
                                    <dt className="text-muted-foreground">Source note</dt>
                                    <dd className="whitespace-pre-wrap font-medium">
                                        {previewPayload?.source_note || '—'}
                                    </dd>
                                </div>
                            </dl>

                            {affectedRows.length > 0 ? (
                                <div className="rounded-lg border">
                                    <Table>
                                        <TableCaption className="sr-only">
                                            Manual transfer status preview
                                        </TableCaption>
                                        <TableHeader>
                                            <TableRow>
                                                <TableHead>Tracked player</TableHead>
                                                <TableHead>Status</TableHead>
                                                <TableHead>Tracking</TableHead>
                                                <TableHead>Journey current status</TableHead>
                                            </TableRow>
                                        </TableHeader>
                                        <TableBody>
                                            {affectedRows.map((row) => (
                                                <TableRow key={row.tracked_player_id}>
                                                    <TableCell className="whitespace-normal">
                                                        <div className="font-medium">
                                                            {row.player_name || `Player ${preview.transfer?.player_api_id}`}
                                                        </div>
                                                        <div className="text-xs text-muted-foreground">
                                                            {row.parent_team_name || 'Unknown parent'} · tracked #{row.tracked_player_id}
                                                        </div>
                                                    </TableCell>
                                                    <TableCell>
                                                        <StatusTransition
                                                            oldValue={row.old_status}
                                                            newValue={row.would_be_status}
                                                        />
                                                    </TableCell>
                                                    <TableCell>
                                                        <ActiveTransition
                                                            oldValue={row.old_is_active}
                                                            newValue={row.would_be_is_active}
                                                        />
                                                    </TableCell>
                                                    <TableCell>
                                                        <StatusTransition
                                                            oldValue={row.journey_current_status?.old}
                                                            newValue={row.journey_current_status?.new}
                                                        />
                                                    </TableCell>
                                                </TableRow>
                                            ))}
                                        </TableBody>
                                    </Table>
                                </div>
                            ) : (
                                <Alert>
                                    <AlertDescription>
                                        No tracked-player status would change. You can still record this transfer fact
                                        and its provenance.
                                    </AlertDescription>
                                </Alert>
                            )}

                            <DialogFooter>
                                <Button
                                    type="button"
                                    variant="outline"
                                    disabled={Boolean(busy)}
                                    onClick={clearPreview}
                                >
                                    Edit details
                                </Button>
                                <Button
                                    type="button"
                                    disabled={!canCommit || Boolean(busy)}
                                    onClick={handleCommit}
                                >
                                    {busy === 'commit' ? (
                                        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                                    ) : (
                                        <ArrowRightLeft className="h-4 w-4" aria-hidden="true" />
                                    )}
                                    {preview.idempotent ? 'Confirm corroboration' : 'Confirm & record'}
                                </Button>
                            </DialogFooter>
                        </div>
                    ) : (
                        <form className="space-y-5" onSubmit={handlePreview}>
                            {initialPlayer ? (
                                <div className="rounded-lg border bg-muted/25 px-4 py-3">
                                    <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                                        Selected player
                                    </p>
                                    <p className="mt-1 font-medium">{initialPlayer.player_name}</p>
                                    <p className="text-xs text-muted-foreground">
                                        API #{initialPlayer.player_api_id}
                                        {initialPlayer.team_name ? ` · ${initialPlayer.team_name}` : ''}
                                    </p>
                                </div>
                            ) : null}

                            <div className="grid gap-4 sm:grid-cols-2">
                                <div className="space-y-2">
                                    <Label htmlFor="manual-transfer-player-id">Player API ID *</Label>
                                    <Input
                                        id="manual-transfer-player-id"
                                        type="number"
                                        min="1"
                                        inputMode="numeric"
                                        required
                                        name="player_api_id"
                                        disabled={Boolean(initialPlayer)}
                                        value={form.player_api_id}
                                        onChange={(event) => updateField('player_api_id', event.target.value)}
                                        placeholder="e.g. 284324"
                                    />
                                </div>
                                <div className="space-y-2">
                                    <Label htmlFor="manual-transfer-type">Transfer type *</Label>
                                    <Select value={form.transfer_type} onValueChange={updateTransferType}>
                                        <SelectTrigger id="manual-transfer-type">
                                            <SelectValue placeholder="Choose transfer type" />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {TRANSFER_TYPES.map((option) => (
                                                <SelectItem key={option.value} value={option.value}>
                                                    {option.label}
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>
                                <div className="space-y-2">
                                    <Label htmlFor="manual-transfer-from-team-id">From team API ID</Label>
                                    <Input
                                        id="manual-transfer-from-team-id"
                                        type="number"
                                        min="1"
                                        inputMode="numeric"
                                        name="from_team_api_id"
                                        value={form.from_team_api_id}
                                        onChange={(event) => updateField('from_team_api_id', event.target.value)}
                                        placeholder="Optional"
                                    />
                                    <p className="text-xs text-muted-foreground">
                                        Leave blank when the stored journey supplies the origin.
                                    </p>
                                </div>
                                <div className="space-y-2">
                                    <Label htmlFor="manual-transfer-date">Effective date *</Label>
                                    <Input
                                        id="manual-transfer-date"
                                        type="date"
                                        required
                                        name="effective_date"
                                        value={form.effective_date}
                                        onChange={(event) => updateField('effective_date', event.target.value)}
                                    />
                                </div>
                            </div>

                            <div className="space-y-3 rounded-lg border bg-muted/15 p-4">
                                <div>
                                    <p className="text-sm font-semibold">Destination</p>
                                    <p className="text-xs text-muted-foreground">
                                        Choose an existing team, enter its API ID, or provide a name already known to
                                        the platform. API ID takes precedence.
                                    </p>
                                </div>

                                {form.transfer_type === 'released' ? (
                                    <p className="rounded-md bg-background px-3 py-2 text-sm text-muted-foreground">
                                        Released records intentionally have no destination.
                                    </p>
                                ) : (
                                    <div className="grid gap-4 sm:grid-cols-2">
                                        <div className="space-y-2 sm:col-span-2">
                                            <Label htmlFor="manual-transfer-destination-team">
                                                Existing destination team
                                            </Label>
                                            <TeamSelect
                                                teams={teams}
                                                value={form.destination_team_db_id}
                                                onChange={selectDestinationTeam}
                                                placeholder="Search existing teams…"
                                                className="w-full"
                                                triggerId="manual-transfer-destination-team"
                                                ariaLabel="Existing destination team"
                                            />
                                        </div>
                                        <div className="space-y-2">
                                            <Label htmlFor="manual-transfer-to-team-id">To team API ID</Label>
                                            <Input
                                                id="manual-transfer-to-team-id"
                                                type="number"
                                                min="1"
                                                inputMode="numeric"
                                                name="to_team_api_id"
                                                value={form.to_team_api_id}
                                                onChange={(event) => {
                                                    setForm((current) => ({
                                                        ...current,
                                                        destination_team_db_id: null,
                                                        to_team_api_id: event.target.value,
                                                        to_team_name: '',
                                                    }))
                                                    clearPreview()
                                                }}
                                                placeholder="Preferred when known"
                                            />
                                        </div>
                                        <div className="space-y-2">
                                            <Label htmlFor="manual-transfer-to-team-name">Destination name</Label>
                                            <Input
                                                id="manual-transfer-to-team-name"
                                                name="to_team_name"
                                                value={form.to_team_name}
                                                onChange={(event) => {
                                                    setForm((current) => ({
                                                        ...current,
                                                        destination_team_db_id: null,
                                                        to_team_api_id: '',
                                                        to_team_name: event.target.value,
                                                    }))
                                                    clearPreview()
                                                }}
                                                placeholder="Must match an existing club or program"
                                            />
                                        </div>
                                    </div>
                                )}
                            </div>

                            <div className="grid gap-4 sm:grid-cols-2">
                                <div className="space-y-2">
                                    <Label htmlFor="manual-transfer-fee">Fee text</Label>
                                    <Input
                                        id="manual-transfer-fee"
                                        name="fee_text"
                                        value={form.fee_text}
                                        onChange={(event) => updateField('fee_text', event.target.value)}
                                        placeholder="Optional, e.g. €5m or Free"
                                    />
                                </div>
                                <div className="space-y-2 sm:col-span-2">
                                    <Label htmlFor="manual-transfer-source-note">Source note *</Label>
                                    <Textarea
                                        id="manual-transfer-source-note"
                                        required
                                        rows={3}
                                        name="source_note"
                                        value={form.source_note}
                                        onChange={(event) => updateField('source_note', event.target.value)}
                                        placeholder="Where this fact came from — club announcement, registration notice, or operator note"
                                    />
                                    <p className="text-xs text-muted-foreground">
                                        Required provenance retained with the manual event and admin audit trail.
                                    </p>
                                </div>
                            </div>

                            <DialogFooter>
                                <Button
                                    type="button"
                                    variant="outline"
                                    disabled={Boolean(busy)}
                                    onClick={() => onOpenChange(false)}
                                >
                                    Cancel
                                </Button>
                                <Button type="submit" disabled={Boolean(busy)}>
                                    {busy === 'preview' ? (
                                        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                                    ) : (
                                        <Eye className="h-4 w-4" aria-hidden="true" />
                                    )}
                                    Preview change
                                </Button>
                            </DialogFooter>
                        </form>
                    )}
                </div>
            </DialogContent>
        </Dialog>
    )
}
