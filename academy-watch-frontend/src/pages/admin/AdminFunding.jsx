import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
    AlertTriangle,
    BellRing,
    Check,
    CheckCircle2,
    Clock3,
    Database,
    ExternalLink,
    FileCheck2,
    Landmark,
    Link2,
    Loader2,
    MapPinned,
    Pencil,
    Plus,
    Search,
    ShieldCheck,
    Trash2,
    UsersRound,
    X,
} from 'lucide-react'

import { APIService } from '@/lib/api'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'

const LEVEL_OPTIONS = [
    ['pro_academy', 'Pro academy'],
    ['youth_national', 'Youth · national'],
    ['youth_regional', 'Youth · regional'],
    ['recreational', 'Recreational'],
]
const ADMISSION_OPTIONS = ['open', 'waitlisted', 'closed']
const REGISTRY_OPTIONS = ['approved', 'proposed', 'rejected']

const EMPTY_FORM = {
    name: '',
    country: '',
    region: '',
    level: 'youth_regional',
    ageBands: 'U12, U14, U16',
    gender_program: 'both',
    season_calendar: 'calendar_year',
    dataTier: 'self_reported',
    leagueApiId: '',
    registry_status: 'approved',
    admission_state: 'open',
    reason: '',
}

const STATUS_STYLES = {
    approved: 'border-emerald-200 bg-emerald-50 text-emerald-800',
    open: 'border-emerald-200 bg-emerald-50 text-emerald-800',
    pending: 'border-amber-200 bg-amber-50 text-amber-800',
    proposed: 'border-amber-200 bg-amber-50 text-amber-800',
    waitlisted: 'border-amber-200 bg-amber-50 text-amber-800',
    closed: 'border-stone-200 bg-stone-100 text-stone-700',
    rejected: 'border-rose-200 bg-rose-50 text-rose-800',
    revoked: 'border-stone-200 bg-stone-100 text-stone-700',
}

function title(value) {
    return String(value || '').replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function formatDate(value) {
    if (!value) return '—'
    const date = new Date(value)
    return Number.isNaN(date.getTime())
        ? '—'
        : date.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

function StatusBadge({ value }) {
    return <Badge className={STATUS_STYLES[value] || 'border-border bg-secondary text-foreground'}>{title(value)}</Badge>
}

function LoadingState({ label }) {
    return (
        <div className="flex items-center justify-center gap-2 py-16 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            {label}
        </div>
    )
}

function Field({ id, label, children, hint }) {
    return (
        <div className="space-y-2">
            <Label htmlFor={id}>{label}</Label>
            {children}
            {hint ? <p className="text-xs leading-relaxed text-muted-foreground">{hint}</p> : null}
        </div>
    )
}

function leagueForm(league) {
    if (!league) return EMPTY_FORM
    const apiTier = league.data_tier?.startsWith('api_football:')
    return {
        name: league.name || '',
        country: league.country || '',
        region: league.region || '',
        level: league.level || 'youth_regional',
        ageBands: (league.age_bands || []).join(', '),
        gender_program: league.gender_program || 'both',
        season_calendar: league.season_calendar || 'calendar_year',
        dataTier: apiTier ? 'api_football' : league.data_tier || 'self_reported',
        leagueApiId: apiTier ? String(league.league_api_id || '') : '',
        registry_status: league.registry_status || 'approved',
        admission_state: league.admission_state || 'waitlisted',
        reason: '',
    }
}

function LeagueDialog({ open, onOpenChange, league, onSaved }) {
    const [form, setForm] = useState(() => leagueForm(league))
    const [saving, setSaving] = useState(false)
    const [error, setError] = useState('')

    const update = (key, value) => setForm((current) => ({ ...current, [key]: value }))

    const submit = async (event) => {
        event.preventDefault()
        setSaving(true)
        setError('')
        const payload = {
            name: form.name,
            country: form.country,
            region: form.region,
            level: form.level,
            age_bands: form.ageBands.split(',').map((item) => item.trim()).filter(Boolean),
            gender_program: form.gender_program,
            season_calendar: form.season_calendar,
            data_tier: form.dataTier === 'api_football'
                ? `api_football:${form.leagueApiId}`
                : form.dataTier,
            registry_status: form.registry_status,
            admission_state: form.admission_state,
            reason: form.reason,
        }
        if (league?.is_provider_bridge) {
            delete payload.name
            delete payload.country
            delete payload.data_tier
        }
        try {
            if (league) await APIService.adminUpdateFundingLeague(league.id, payload)
            else await APIService.adminCreateFundingLeague(payload)
            onOpenChange(false)
            onSaved(league ? 'League registry updated.' : 'League admitted to the registry.')
        } catch (err) {
            setError(err.message || 'Unable to save league')
        } finally {
            setSaving(false)
        }
    }

    const identityLocked = Boolean(league?.is_provider_bridge)

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-h-[92vh] max-w-3xl overflow-y-auto border-0 p-0 shadow-2xl">
                <div className="border-b bg-[#0b1f19] px-6 py-5 text-white">
                    <DialogHeader>
                        <DialogTitle className="font-serif text-2xl tracking-tight">
                            {league ? 'Edit league admission' : 'Admit a league'}
                        </DialogTitle>
                        <DialogDescription className="text-emerald-100/70">
                            Registry facts control which club programs may enter verification.
                        </DialogDescription>
                    </DialogHeader>
                </div>
                <form onSubmit={submit} className="space-y-6 px-6 pb-6">
                    {identityLocked ? (
                        <Alert className="border-sky-200 bg-sky-50 text-sky-900">
                            <Link2 className="h-4 w-4" />
                            <AlertDescription>Provider identity is bridged read-only. Admission metadata remains editable.</AlertDescription>
                        </Alert>
                    ) : null}
                    {error ? (
                        <Alert variant="destructive"><AlertTriangle className="h-4 w-4" /><AlertDescription>{error}</AlertDescription></Alert>
                    ) : null}
                    <div className="grid gap-4 sm:grid-cols-2">
                        <Field id="funding-league-name" label="League name"><Input id="funding-league-name" name="name" autoComplete="off" value={form.name} onChange={(e) => update('name', e.target.value)} disabled={identityLocked} required /></Field>
                        <Field id="funding-league-country" label="Country"><Input id="funding-league-country" name="country" autoComplete="country-name" value={form.country} onChange={(e) => update('country', e.target.value)} disabled={identityLocked} required /></Field>
                        <Field id="funding-league-region" label="Region"><Input id="funding-league-region" name="region" autoComplete="address-level1" value={form.region} onChange={(e) => update('region', e.target.value)} required /></Field>
                        <Field id="funding-league-level" label="Competitive level">
                            <Select name="level" value={form.level} onValueChange={(value) => update('level', value)}>
                                <SelectTrigger id="funding-league-level"><SelectValue /></SelectTrigger>
                                <SelectContent>{LEVEL_OPTIONS.map(([value, label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}</SelectContent>
                            </Select>
                        </Field>
                        <Field id="funding-league-age-bands" label="Age bands" hint="Comma-separated, for example U10, U12, U14.">
                            <Input id="funding-league-age-bands" name="age_bands" autoComplete="off" value={form.ageBands} onChange={(e) => update('ageBands', e.target.value)} required />
                        </Field>
                        <Field id="funding-league-gender" label="Gender program">
                            <Select name="gender_program" value={form.gender_program} onValueChange={(value) => update('gender_program', value)}>
                                <SelectTrigger id="funding-league-gender"><SelectValue /></SelectTrigger>
                                <SelectContent><SelectItem value="boys">Boys</SelectItem><SelectItem value="girls">Girls</SelectItem><SelectItem value="both">Boys + girls</SelectItem></SelectContent>
                            </Select>
                        </Field>
                        <Field id="funding-league-season" label="Season calendar">
                            <Select name="season_calendar" value={form.season_calendar} onValueChange={(value) => update('season_calendar', value)}>
                                <SelectTrigger id="funding-league-season"><SelectValue /></SelectTrigger>
                                <SelectContent><SelectItem value="aug_may">August–May</SelectItem><SelectItem value="calendar_year">Calendar year</SelectItem><SelectItem value="fall_spring">Fall–spring</SelectItem></SelectContent>
                            </Select>
                        </Field>
                        <Field id="funding-league-data-tier" label="Data tier">
                            <Select name="data_tier" value={form.dataTier} onValueChange={(value) => update('dataTier', value)} disabled={identityLocked}>
                                <SelectTrigger id="funding-league-data-tier"><SelectValue /></SelectTrigger>
                                <SelectContent><SelectItem value="api_football">API-Football bridge</SelectItem><SelectItem value="film_room">Film Room</SelectItem><SelectItem value="self_reported">Self-reported</SelectItem></SelectContent>
                            </Select>
                        </Field>
                        {form.dataTier === 'api_football' ? (
                            <Field id="funding-league-api-id" label="API-Football league ID" hint="Existing provider records are linked, never duplicated.">
                                <Input id="funding-league-api-id" name="league_api_id" type="number" min="1" value={form.leagueApiId} onChange={(e) => update('leagueApiId', e.target.value)} disabled={identityLocked} required />
                            </Field>
                        ) : null}
                        <Field id="funding-league-registry-status" label="Registry review">
                            <Select name="registry_status" value={form.registry_status} onValueChange={(value) => update('registry_status', value)}>
                                <SelectTrigger id="funding-league-registry-status"><SelectValue /></SelectTrigger>
                                <SelectContent>{REGISTRY_OPTIONS.map((value) => <SelectItem key={value} value={value}>{title(value)}</SelectItem>)}</SelectContent>
                            </Select>
                        </Field>
                        <Field id="funding-league-admission-state" label="Admission state">
                            <Select name="admission_state" value={form.admission_state} onValueChange={(value) => update('admission_state', value)}>
                                <SelectTrigger id="funding-league-admission-state"><SelectValue /></SelectTrigger>
                                <SelectContent>{ADMISSION_OPTIONS.map((value) => <SelectItem key={value} value={value}>{title(value)}</SelectItem>)}</SelectContent>
                            </Select>
                        </Field>
                    </div>
                    <Field id="funding-league-reason" label="Audit reason" hint="Required. This explanation is retained in the funding audit trail.">
                        <Textarea id="funding-league-reason" name="reason" autoComplete="off" value={form.reason} onChange={(e) => update('reason', e.target.value)} placeholder="Explain why this league is being admitted or changed…" required />
                    </Field>
                    <DialogFooter>
                        <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
                        <Button type="submit" disabled={saving} className="bg-emerald-700 hover:bg-emerald-800">
                            {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <ShieldCheck className="mr-2 h-4 w-4" />}
                            {league ? 'Save admission' : 'Add league'}
                        </Button>
                    </DialogFooter>
                </form>
            </DialogContent>
        </Dialog>
    )
}

function RegistryTab({ leagues, loading, filters, setFilters, onEdit, onCreate, onDelete }) {
    return (
        <div className="space-y-4">
            <div className="grid gap-3 rounded-2xl border bg-card p-4 shadow-sm md:grid-cols-[1fr_180px_180px_auto]">
                <div className="relative">
                    <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                    <Input aria-label="Search leagues" name="funding_league_search" autoComplete="off" value={filters.q} onChange={(e) => setFilters((current) => ({ ...current, q: e.target.value }))} placeholder="Search by league or region…" className="pl-9" />
                </div>
                <Select value={filters.admission_state} onValueChange={(value) => setFilters((current) => ({ ...current, admission_state: value }))}>
                    <SelectTrigger aria-label="Filter by admission state"><SelectValue placeholder="Admission" /></SelectTrigger>
                    <SelectContent><SelectItem value="all">All admissions</SelectItem>{ADMISSION_OPTIONS.map((value) => <SelectItem key={value} value={value}>{title(value)}</SelectItem>)}</SelectContent>
                </Select>
                <Select value={filters.registry_status} onValueChange={(value) => setFilters((current) => ({ ...current, registry_status: value }))}>
                    <SelectTrigger aria-label="Filter by registry status"><SelectValue placeholder="Registry status" /></SelectTrigger>
                    <SelectContent><SelectItem value="all">All registry states</SelectItem>{REGISTRY_OPTIONS.map((value) => <SelectItem key={value} value={value}>{title(value)}</SelectItem>)}</SelectContent>
                </Select>
                <Button onClick={onCreate} className="bg-emerald-700 hover:bg-emerald-800"><Plus className="mr-2 h-4 w-4" />Add league</Button>
            </div>
            {loading ? <LoadingState label="Loading registry…" /> : leagues.length === 0 ? (
                <Card><CardContent className="py-14 text-center"><Landmark className="mx-auto mb-3 h-7 w-7 text-muted-foreground" /><p className="font-medium">No leagues match this view.</p><p className="mt-1 text-sm text-muted-foreground">Add one directly or review a proposed waitlist entry.</p></CardContent></Card>
            ) : (
                <div className="grid gap-4 xl:grid-cols-2">
                    {leagues.map((league) => (
                        <Card key={league.id} className="overflow-hidden border-l-4 border-l-emerald-700 shadow-sm">
                            <CardHeader className="pb-3">
                                <div className="flex items-start justify-between gap-4">
                                    <div>
                                        <div className="mb-2 flex flex-wrap gap-2"><StatusBadge value={league.registry_status} /><StatusBadge value={league.admission_state} />{league.is_provider_bridge ? <Badge variant="outline"><Database className="mr-1 h-3 w-3" />Provider bridge</Badge> : null}</div>
                                        <CardTitle className="font-serif text-xl">{league.name}</CardTitle>
                                        <CardDescription className="mt-1 flex items-center gap-1"><MapPinned className="h-3.5 w-3.5" />{league.region}, {league.country}</CardDescription>
                                    </div>
                                    <div className="flex gap-1"><Button size="icon" variant="ghost" aria-label={`Edit ${league.name}`} onClick={() => onEdit(league)}><Pencil className="h-4 w-4" /></Button>{league.is_provider_bridge ? null : <Button size="icon" variant="ghost" className="text-muted-foreground hover:text-destructive" aria-label={`Delete ${league.name}`} onClick={() => onDelete(league)}><Trash2 className="h-4 w-4" /></Button>}</div>
                                </div>
                            </CardHeader>
                            <CardContent className="grid grid-cols-2 gap-x-5 gap-y-3 text-sm">
                                <div><p className="text-xs uppercase tracking-wide text-muted-foreground">Level</p><p className="font-medium">{title(league.level)}</p></div>
                                <div><p className="text-xs uppercase tracking-wide text-muted-foreground">Program</p><p className="font-medium">{title(league.gender_program)}</p></div>
                                <div><p className="text-xs uppercase tracking-wide text-muted-foreground">Age bands</p><p className="font-medium">{(league.age_bands || []).join(' · ')}</p></div>
                                <div><p className="text-xs uppercase tracking-wide text-muted-foreground">Data</p><p className="font-medium">{league.data_tier?.replace('_', ' ')}</p></div>
                            </CardContent>
                        </Card>
                    ))}
                </div>
            )}
        </div>
    )
}

function safeHttpsUrl(value) {
    if (typeof value !== 'string') return null
    try {
        const parsed = new URL(value)
        return parsed.protocol === 'https:' ? parsed.href : null
    } catch {
        return null
    }
}

function EvidenceChecklist({ evidence }) {
    const rows = [
        { label: 'Adult authority', value: evidence?.adult_authority_attested, type: 'attestation' },
        { label: 'Authorization route', value: evidence?.authorization_method, type: 'enum' },
        { label: 'Official-domain email', value: evidence?.official_email },
        { label: 'Signed officer authorization', value: evidence?.authorization_reference },
        { label: 'Eligible organization form', value: evidence?.organization_form, type: 'enum' },
        { label: 'League / legal registration match', value: evidence?.registration_reference },
        { label: 'Official contact name', value: evidence?.official_contact_name },
        { label: 'Official contact cross-check', value: evidence?.official_contact_reference },
        { label: 'Safeguarding contact', value: evidence?.safeguarding_contact_email },
        { label: 'Safeguarding policy URL', value: evidence?.safeguarding_policy_url },
        { label: 'Safeguarding controls', value: evidence?.safeguarding_policy_attested, type: 'attestation' },
        { label: 'Organization-only recipient', value: evidence?.eligible_organization_attested, type: 'attestation' },
        { label: 'Organization payout control', value: evidence?.payout_control_attested, type: 'attestation' },
    ]
    return (
        <div className="grid gap-2 sm:grid-cols-2">
            {rows.map(({ label, value, type }) => {
                const isAttestation = type === 'attestation'
                const isPresent = isAttestation ? value === true : typeof value === 'string' && value.trim().length > 0
                const displayValue = type === 'enum' && isPresent ? title(value) : value
                const href = safeHttpsUrl(value)
                return (
                    <div key={label} className="flex min-w-0 items-start gap-2 rounded-lg border bg-background/70 px-3 py-2 text-xs">
                        {isPresent ? <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-700" /> : <X className="mt-0.5 h-3.5 w-3.5 shrink-0 text-rose-600" />}
                        <span className="min-w-0 flex-1">
                            <span className="block text-muted-foreground">{label}</span>
                            {isAttestation ? (
                                <span className="block font-medium text-foreground">{isPresent ? 'Attested' : 'Not attested'}</span>
                            ) : href ? (
                                <a href={href} target="_blank" rel="noreferrer" className="block break-words font-medium text-primary underline underline-offset-2 [overflow-wrap:anywhere]">
                                    {value}<ExternalLink className="ml-1 inline h-3 w-3" aria-hidden="true" />
                                </a>
                            ) : (
                                <span className="block break-words font-medium text-foreground [overflow-wrap:anywhere]">{isPresent ? displayValue : 'Not supplied'}</span>
                            )}
                        </span>
                    </div>
                )
            })}
        </div>
    )
}

function ClaimsTab({ claims, loading, status, setStatus, onReview, onSyncConnect }) {
    return (
        <div className="space-y-4">
            <div className="flex flex-col justify-between gap-3 rounded-2xl border bg-card p-4 shadow-sm sm:flex-row sm:items-center">
                <div><h3 className="font-serif text-xl font-semibold">Organization approval queue</h3><p className="text-sm text-muted-foreground">League eligibility never substitutes for the club evidence bar.</p></div>
                <Select value={status} onValueChange={setStatus}><SelectTrigger aria-label="Filter claims by status" className="w-44"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">All claims</SelectItem>{['pending', 'approved', 'rejected', 'revoked'].map((value) => <SelectItem key={value} value={value}>{title(value)}</SelectItem>)}</SelectContent></Select>
            </div>
            {loading ? <LoadingState label="Loading approval queue…" /> : claims.length === 0 ? (
                <Card><CardContent className="py-14 text-center"><CheckCircle2 className="mx-auto mb-3 h-7 w-7 text-emerald-700" /><p className="font-medium">No {status === 'all' ? '' : status} claims in the queue.</p></CardContent></Card>
            ) : claims.map((claim) => {
                const league = claim.program?.league
                const leagueReady = league?.registry_status === 'approved' && league?.admission_state === 'open'
                return (
                    <Card key={claim.id} className="overflow-hidden shadow-sm">
                        <div className={`h-1 ${claim.status === 'pending' ? 'bg-amber-400' : claim.status === 'approved' ? 'bg-emerald-600' : 'bg-rose-500'}`} />
                        <CardHeader>
                            <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-start">
                                <div className="space-y-2">
                                    <div className="flex flex-wrap gap-2"><StatusBadge value={claim.status} />{claim.program?.is_verified_program ? <Badge className="border-emerald-300 bg-emerald-700 text-white"><ShieldCheck className="mr-1 h-3 w-3" />Verified program</Badge> : <Badge variant="outline"><Clock3 className="mr-1 h-3 w-3" />Verification incomplete</Badge>}</div>
                                    <CardTitle className="font-serif text-2xl">{claim.program?.name}</CardTitle>
                                    <CardDescription>{claim.program?.legal_name} · {claim.applicant_email}</CardDescription>
                                </div>
                                {claim.status === 'pending' ? (
                                    <div className="flex gap-2"><Button size="sm" disabled={!leagueReady} onClick={() => onReview(claim, 'approve')} className="bg-emerald-700 hover:bg-emerald-800"><Check className="mr-1 h-4 w-4" />Approve</Button><Button size="sm" variant="outline" className="border-rose-300 text-rose-700" onClick={() => onReview(claim, 'reject')}><X className="mr-1 h-4 w-4" />Reject</Button></div>
                                ) : claim.status === 'approved' ? (
                                    <Button size="sm" variant="outline" className="border-rose-300 text-rose-700" onClick={() => onReview(claim, 'revoke')}><X className="mr-1 h-4 w-4" />Revoke access</Button>
                                ) : null}
                            </div>
                        </CardHeader>
                        <CardContent className="space-y-5">
                            <div className="grid gap-3 rounded-xl bg-secondary/60 p-4 md:grid-cols-3">
                                <div><p className="text-xs uppercase tracking-wide text-muted-foreground">League gate</p><p className="mt-1 font-medium">{league?.name}</p><div className="mt-2 flex gap-1"><StatusBadge value={league?.registry_status} /><StatusBadge value={league?.admission_state} /></div></div>
                                <div><p className="text-xs uppercase tracking-wide text-muted-foreground">Location</p><p className="mt-1 font-medium">{claim.program?.region}, {claim.program?.country}</p><p className="mt-1 text-xs text-muted-foreground">{claim.program?.provenance?.label}</p></div>
                                <div><p className="text-xs uppercase tracking-wide text-muted-foreground">Connect</p><p className="mt-1 font-medium">{claim.connect ? (claim.connect.is_ready ? 'Test account ready' : 'Onboarding pending') : 'Not required outside US'}</p>{claim.connect?.onboarding_url ? <a href={claim.connect.onboarding_url} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center text-xs text-primary underline">Open test onboarding <ExternalLink className="ml-1 h-3 w-3" /></a> : null}{claim.connect?.stripe_account_id && !claim.connect?.is_ready ? <Button size="sm" variant="link" className="mt-1 h-auto p-0 text-xs" onClick={() => onSyncConnect(claim)}>Sync test readiness</Button> : null}</div>
                            </div>
                            {!leagueReady && claim.status === 'pending' ? <Alert className="border-amber-200 bg-amber-50 text-amber-900"><AlertTriangle className="h-4 w-4" /><AlertDescription>Approve and open the proposed league before this club claim can be approved.</AlertDescription></Alert> : null}
                            <EvidenceChecklist evidence={claim.evidence} />
                            {claim.audit_trail?.length > 0 ? (
                                <details className="rounded-lg border px-4 py-3 text-sm"><summary className="cursor-pointer font-medium">Audit trail · {claim.audit_trail.length}</summary><div className="mt-3 space-y-2 border-l pl-4">{claim.audit_trail.map((event, index) => <div key={`${event.action}-${index}`}><p className="font-medium">{title(event.action)}</p><p className="text-xs text-muted-foreground">{event.reason} · {formatDate(event.created_at)}</p></div>)}</div></details>
                            ) : null}
                        </CardContent>
                    </Card>
                )
            })}
        </div>
    )
}

function DemandTab({ demand, loading }) {
    if (loading) return <LoadingState label="Reading future-support demand…" />
    const total = (demand.programs || []).reduce((sum, row) => sum + Number(row.saved_count || 0), 0)
    return (
        <div className="space-y-5">
            <div className="grid gap-4 md:grid-cols-3">
                <Card className="border-0 bg-[#0b1f19] text-white shadow-lg"><CardHeader><CardDescription className="text-emerald-100/60">Notify requests</CardDescription><CardTitle className="font-serif text-4xl">{total}</CardTitle></CardHeader></Card>
                <Card><CardHeader><CardDescription>Regions with demand</CardDescription><CardTitle className="font-serif text-4xl">{demand.by_region?.length || 0}</CardTitle></CardHeader></Card>
                <Card><CardHeader><CardDescription>Saved programs</CardDescription><CardTitle className="font-serif text-4xl">{demand.programs?.length || 0}</CardTitle></CardHeader></Card>
            </div>
            <div className="grid gap-5 lg:grid-cols-2">
                <Card><CardHeader><CardTitle className="flex items-center gap-2 font-serif"><MapPinned className="h-5 w-5 text-emerald-700" />By region</CardTitle></CardHeader><CardContent className="space-y-3">{demand.by_region?.length ? demand.by_region.map((row) => <div key={row.region} className="flex items-center justify-between border-b pb-3"><span className="font-medium">{row.region}</span><Badge variant="secondary">{row.saved_count} saves</Badge></div>) : <p className="text-sm text-muted-foreground">No future-support signals yet.</p>}</CardContent></Card>
                <Card><CardHeader><CardTitle className="flex items-center gap-2 font-serif"><Landmark className="h-5 w-5 text-emerald-700" />By league</CardTitle></CardHeader><CardContent className="space-y-3">{demand.by_league?.length ? demand.by_league.map((row) => <div key={row.league} className="flex items-center justify-between border-b pb-3"><span className="font-medium">{row.league}</span><Badge variant="secondary">{row.saved_count} saves</Badge></div>) : <p className="text-sm text-muted-foreground">No future-support signals yet.</p>}</CardContent></Card>
            </div>
            {demand.programs?.length ? <Card><CardHeader><CardTitle className="font-serif">Program signals</CardTitle><CardDescription>Expansion demand only—never an admission or ranking signal.</CardDescription></CardHeader><CardContent className="divide-y">{demand.programs.map((row) => <div key={row.program_id} className="flex flex-col justify-between gap-2 py-4 sm:flex-row sm:items-center"><div><Link className="font-medium hover:underline" to={`/programs/${row.slug}`}>{row.program_name}</Link><p className="text-xs text-muted-foreground">{row.league} · {row.region}, {row.country}</p></div><Badge><BellRing className="mr-1 h-3 w-3" />{row.saved_count}</Badge></div>)}</CardContent></Card> : null}
        </div>
    )
}

export function AdminFunding() {
    const [searchParams, setSearchParams] = useSearchParams()
    const requestedTab = searchParams.get('tab')
    const [tab, setTab] = useState(['registry', 'claims', 'demand'].includes(requestedTab) ? requestedTab : 'registry')
    const [filters, setFilters] = useState({ q: '', admission_state: 'all', registry_status: 'all' })
    const [claimStatus, setClaimStatus] = useState('pending')
    const [leagues, setLeagues] = useState([])
    const [claims, setClaims] = useState([])
    const [demand, setDemand] = useState({ programs: [], by_region: [], by_league: [] })
    const [loading, setLoading] = useState(true)
    const [message, setMessage] = useState(null)
    const [dialogOpen, setDialogOpen] = useState(false)
    const [editingLeague, setEditingLeague] = useState(null)
    const [review, setReview] = useState(null)
    const [reviewReason, setReviewReason] = useState('')
    const [reviewing, setReviewing] = useState(false)

    const leagueParams = useMemo(() => Object.fromEntries(
        Object.entries(filters).filter(([, value]) => value && value !== 'all')
    ), [filters])

    const load = useCallback(async () => {
        await Promise.resolve()
        setLoading(true)
        try {
            const [leagueData, claimData, demandData] = await Promise.all([
                APIService.adminFundingLeagues(leagueParams),
                APIService.adminFundingClaims({ status: claimStatus }),
                APIService.adminFundingDemand(),
            ])
            setLeagues(leagueData?.leagues || [])
            setClaims(claimData?.claims || [])
            setDemand(demandData || { programs: [], by_region: [], by_league: [] })
        } catch (err) {
            setMessage({ type: 'error', text: err.message || 'Unable to load funding registry' })
        } finally {
            setLoading(false)
        }
    }, [claimStatus, leagueParams])

    useEffect(() => { load() }, [load])

    const changeTab = (value) => {
        setTab(value)
        setSearchParams(value === 'registry' ? {} : { tab: value }, { replace: true })
    }

    const saved = (text) => {
        setMessage({ type: 'success', text })
        load()
    }

    const removeLeague = async (league) => {
        const reason = window.prompt(`Audit reason for deleting ${league.name}:`)
        if (!reason) return
        try {
            await APIService.adminDeleteFundingLeague(league.id, reason)
            saved('League removed from the registry.')
        } catch (err) {
            setMessage({ type: 'error', text: err.message || 'Unable to delete league' })
        }
    }

    const submitReview = async () => {
        if (!reviewReason.trim()) return
        setReviewing(true)
        try {
            await APIService.adminReviewFundingClaim(review.claim.id, review.action, reviewReason.trim())
            setReview(null)
            setReviewReason('')
            const actionLabel = review.action === 'approve' ? 'approved' : review.action === 'revoke' ? 'revoked' : 'rejected'
            saved(`Claim ${actionLabel} with an audit record.`)
        } catch (err) {
            setMessage({ type: 'error', text: err.message || 'Unable to review claim' })
        } finally {
            setReviewing(false)
        }
    }

    const syncConnect = async (claim) => {
        const reason = window.prompt(`Audit reason for syncing ${claim.program?.name} with test-mode Connect:`)
        if (!reason?.trim()) return
        try {
            await APIService.adminSyncFundingConnect(claim.program.id, reason.trim())
            saved('Test-mode Connect readiness synced and verification recomputed.')
        } catch (err) {
            setMessage({ type: 'error', text: err.message || 'Unable to sync test-mode Connect' })
        }
    }

    const stats = {
        open: leagues.filter((league) => league.admission_state === 'open' && league.registry_status === 'approved').length,
        proposed: leagues.filter((league) => league.registry_status === 'proposed').length,
        pending: claims.filter((claim) => claim.status === 'pending').length,
    }

    return (
        <div className="space-y-6">
            <section className="relative overflow-hidden rounded-3xl bg-[#0b1f19] px-6 py-7 text-white shadow-xl sm:px-8">
                <div className="absolute inset-0 opacity-20" style={{ backgroundImage: 'linear-gradient(rgba(255,255,255,.12) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.12) 1px, transparent 1px)', backgroundSize: '36px 36px' }} />
                <div className="relative flex flex-col justify-between gap-6 lg:flex-row lg:items-end">
                    <div className="max-w-2xl"><div className="mb-4 flex h-11 w-11 items-center justify-center rounded-full border border-emerald-200/30 bg-emerald-200/10"><ShieldCheck className="h-5 w-5 text-emerald-200" /></div><p className="text-xs font-semibold uppercase tracking-[0.24em] text-emerald-200/70">Grassroots funding · F2</p><h1 className="mt-2 font-serif text-4xl font-semibold tracking-tight sm:text-5xl">Registry control room</h1><p className="mt-3 max-w-xl text-sm leading-relaxed text-emerald-50/70">League-gated admission, adult authority evidence, and organization verification. No donations are processed in this build.</p></div>
                    <div className="grid grid-cols-3 gap-3"><div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3"><p className="text-2xl font-semibold">{stats.open}</p><p className="text-xs text-emerald-50/60">Open leagues</p></div><div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3"><p className="text-2xl font-semibold">{stats.proposed}</p><p className="text-xs text-emerald-50/60">Waitlist</p></div><div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3"><p className="text-2xl font-semibold">{stats.pending}</p><p className="text-xs text-emerald-50/60">Claims</p></div></div>
                </div>
            </section>

            {message ? <Alert className={message.type === 'error' ? 'border-rose-300 bg-rose-50 text-rose-900' : 'border-emerald-300 bg-emerald-50 text-emerald-900'}>{message.type === 'error' ? <AlertTriangle className="h-4 w-4" /> : <CheckCircle2 className="h-4 w-4" />}<AlertDescription>{message.text}</AlertDescription></Alert> : null}

            <Tabs value={tab} onValueChange={changeTab}>
                <TabsList className="grid h-auto w-full grid-cols-3 rounded-2xl bg-secondary p-1 sm:w-[560px]">
                    <TabsTrigger value="registry" className="rounded-xl py-2.5"><Landmark className="mr-2 h-4 w-4" />League registry</TabsTrigger>
                    <TabsTrigger value="claims" className="rounded-xl py-2.5"><FileCheck2 className="mr-2 h-4 w-4" />Approval queue</TabsTrigger>
                    <TabsTrigger value="demand" className="rounded-xl py-2.5"><BellRing className="mr-2 h-4 w-4" />Demand</TabsTrigger>
                </TabsList>
                <TabsContent value="registry" className="mt-5"><RegistryTab leagues={leagues} loading={loading} filters={filters} setFilters={setFilters} onCreate={() => { setEditingLeague(null); setDialogOpen(true) }} onEdit={(league) => { setEditingLeague(league); setDialogOpen(true) }} onDelete={removeLeague} /></TabsContent>
                <TabsContent value="claims" className="mt-5"><ClaimsTab claims={claims} loading={loading} status={claimStatus} setStatus={setClaimStatus} onReview={(claim, action) => { setReview({ claim, action }); setReviewReason('') }} onSyncConnect={syncConnect} /></TabsContent>
                <TabsContent value="demand" className="mt-5"><DemandTab demand={demand} loading={loading} /></TabsContent>
            </Tabs>

            {dialogOpen ? <LeagueDialog open onOpenChange={setDialogOpen} league={editingLeague} onSaved={saved} /> : null}
            <Dialog open={Boolean(review)} onOpenChange={(open) => { if (!open) setReview(null) }}>
                <DialogContent>
                    <DialogHeader><DialogTitle className="font-serif text-2xl">{review?.action === 'approve' ? 'Approve organization' : review?.action === 'revoke' ? 'Revoke manager access' : 'Reject claim'}</DialogTitle><DialogDescription>{review?.claim?.program?.name} · the reason is retained in the immutable admin trail.</DialogDescription></DialogHeader>
                    <Field id="funding-review-reason" label="Review reason"><Textarea id="funding-review-reason" name="review_reason" autoComplete="off" autoFocus value={reviewReason} onChange={(e) => setReviewReason(e.target.value)} placeholder="Record the evidence decision and any follow-up…" /></Field>
                    <DialogFooter><Button variant="ghost" onClick={() => setReview(null)}>Cancel</Button><Button disabled={reviewing || !reviewReason.trim()} onClick={submitReview} className={review?.action === 'approve' ? 'bg-emerald-700 hover:bg-emerald-800' : 'bg-rose-700 hover:bg-rose-800'}>{reviewing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : review?.action === 'approve' ? <ShieldCheck className="mr-2 h-4 w-4" /> : <X className="mr-2 h-4 w-4" />}{review?.action === 'approve' ? 'Approve claim' : review?.action === 'revoke' ? 'Revoke manager' : 'Reject claim'}</Button></DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    )
}
