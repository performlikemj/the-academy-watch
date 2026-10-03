import { formatDisplayDate } from '@/lib/display-date'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
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
import { CalmDetails, CalmHeader, StatusDot, calmPanelClass, calmPillButton, calmPrimaryButton, calmWarnButton } from '@/components/admin/ControlRoom'
import { FilterBar } from '@/components/filter/FilterBar'
import { useUrlFilters } from '@/hooks/useUrlFilters'
import { clubCheckLine, clubCheckSummary, leagueOpen } from '@/lib/club-checks'
import { countLabel } from '@/lib/url-filters'
import { DirectoryReview } from '@/components/admin/DirectoryReview' // p2-b1

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
    return formatDisplayDate(value, { fallback: '—' })
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

const CLAIM_STATUS = [['pending', 'Waiting'], ['approved', 'Approved'], ['rejected', 'Rejected'], ['revoked', 'Revoked'], ['all', 'All']]
const CLAIM_WORDS = { pending: ['gold', 'Waiting'], approved: ['good', 'Approved'], rejected: ['quiet', 'Rejected'], revoked: ['quiet', 'Revoked'] }
const CLAIM_ASK = { pending: 'Wants to be a verified club', approved: 'Approved club', rejected: 'Claim rejected', revoked: 'Manager access revoked' }
const CLAIM_FILTERS = [{ key: 'status', label: 'Status', neutral: true, defaultValue: 'pending', options: CLAIM_STATUS.map(([value, label]) => ({ value, label })) }]

function ClaimsTab({ claims, loading, status, onStatus, onOpen }) {
    return (
        <div className="flex flex-col gap-4">
            <FilterBar label="Claim filters" filters={CLAIM_FILTERS} values={{ status }} onChange={changes => onStatus(changes.status)} count={loading ? '' : countLabel(claims.length, 'club', 'clubs')} />
            {loading ? <LoadingState label="Loading clubs…" /> : claims.length === 0 ? (
                <p className="border-t border-chalk/[0.12] py-8 text-sm text-muted-dark">{status === 'pending' ? 'No clubs are waiting.' : 'No clubs in this view.'}</p>
            ) : (
                <ul className="m-0 list-none overflow-hidden rounded-2xl border border-chalk/[0.12] p-0">
                    {claims.map((claim, index) => {
                        const [tone, words] = CLAIM_WORDS[claim.status] || ['quiet', title(claim.status)]
                        return (
                            <li key={claim.id}>
                                <button type="button" onClick={() => onOpen(claim)} className={`flex w-full items-center gap-4 px-5 py-4 text-left transition-colors hover:bg-chalk/[0.04] focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-gold ${index < claims.length - 1 ? 'border-b border-chalk/[0.08]' : ''}`}>
                                    <StatusDot tone={tone} />
                                    <span className="min-w-0 flex-1">
                                        <span className="block text-[15px] font-medium text-chalk [overflow-wrap:anywhere]">{claim.program?.name}</span>
                                        <span className="mt-0.5 block text-[13px] text-muted-dark [overflow-wrap:anywhere]">{clubCheckLine(clubCheckSummary(claim.evidence))}</span>
                                    </span>
                                    <span className="flex-none text-[13px] text-muted-dark">{words}</span>
                                </button>
                            </li>
                        )
                    })}
                </ul>
            )}
        </div>
    )
}

function CheckLine({ item }) {
    const href = item.ok ? safeHttpsUrl(item.value) : null
    const optional = !item.required && !item.ok
    return (
        <div className={`[overflow-wrap:anywhere] ${!item.ok && item.required ? 'text-chalk' : ''}`}>
            {item.label} ·{' '}
            {href ? <a href={href} target="_blank" rel="noreferrer" className="underline underline-offset-2">{item.value}<ExternalLink className="ml-1 inline h-3 w-3" aria-hidden="true" /></a>
                : <span className={!item.ok && item.required ? 'text-[#E07A5F]' : ''}>{optional ? 'not supplied (optional)' : item.value}</span>}
        </div>
    )
}

function ClaimDetail({ claim, waiting, onBack, onReview, onSyncConnect }) {
    const summary = clubCheckSummary(claim.evidence)
    const league = claim.program?.league
    const ready = leagueOpen(league)
    const pending = claim.status === 'pending'
    const place = [claim.program?.region, claim.program?.country].filter(Boolean).join(', ')
    const connect = claim.connect
    return (
        <div className="flex max-w-[820px] flex-col gap-7">
            <CalmHeader
                back={<button type="button" onClick={onBack} className="self-start text-sm text-muted-dark hover:text-chalk">← Clubs waiting · {waiting}</button>}
                title={claim.program?.name}
                line={[CLAIM_ASK[claim.status] || title(claim.status), league?.name, place].filter(Boolean).join(' · ')}
            />

            <section aria-label="Decision" className={`${calmPanelClass} flex flex-col gap-5`}>
                <div className="flex flex-wrap items-start justify-between gap-6">
                    <div className="flex min-w-0 flex-col gap-2">
                        <p className="m-0 text-xl font-semibold text-chalk">{summary.passed} of {summary.total} checks pass</p>
                        {summary.missing.map(item => (
                            <p key={item.label} className="m-0 flex items-center gap-2.5 text-[15px] text-chalk"><StatusDot tone="warn" /><span>Missing: <span className="font-medium">{item.short}</span> — {item.missing}</span></p>
                        ))}
                        {summary.complete && <p className="m-0 flex items-center gap-2.5 text-[15px] text-[#C9C5BA]"><StatusDot tone="good" />Nothing is missing</p>}
                    </div>
                    <div className="flex flex-wrap gap-2.5">
                        {pending && <button type="button" className={`${calmPillButton} h-11`} onClick={() => onReview(claim, 'reject')}>Reject</button>}
                        {pending && <button type="button" className={calmPrimaryButton} disabled={!summary.complete || !ready} onClick={() => onReview(claim, 'approve')}>Approve</button>}
                        {claim.status === 'approved' && <button type="button" className={`${calmWarnButton} h-11`} onClick={() => onReview(claim, 'revoke')}>Revoke access</button>}
                    </div>
                </div>
                {pending && (
                    <p className="m-0 text-[13px] text-muted-dark">
                        {!summary.complete ? 'A club can be approved only when every check passes. Reject the claim, or leave it waiting until the club supplies what is missing.'
                            : !ready ? `${league?.name || 'The league'} is not open yet. Approve and open it in the League registry before approving this club.`
                                : `Approving makes ${claim.applicant_email || 'the applicant'} the club's manager and records your reason.`}
                    </p>
                )}
            </section>

            <section aria-label="Checks" className="border-b border-chalk/[0.12]">
                {summary.groups.map(group => (
                    <CalmDetails key={group.key} summary={group.title} note={`${group.passed} of ${group.total} pass`} noteTone={group.failing ? 'warn' : undefined} open={group.failing}>
                        <div className="flex flex-col gap-1.5">
                            {group.checks.map(item => <CheckLine key={item.label} item={item} />)}
                            {group.key === 'identity' && <div className="[overflow-wrap:anywhere]">Legal name · {claim.program?.legal_name || 'not supplied'}</div>}
                            {group.key === 'authority' && <div className="[overflow-wrap:anywhere]">Applied by · {claim.applicant_email || 'former account'}</div>}
                            {group.key === 'money' && (
                                <div>
                                    Connect · {connect ? (connect.is_ready ? 'test account ready' : 'onboarding pending') : 'not required outside the US'}
                                    {connect?.onboarding_url ? <> · <a href={connect.onboarding_url} target="_blank" rel="noreferrer" className="underline underline-offset-2">Open test onboarding<ExternalLink className="ml-1 inline h-3 w-3" aria-hidden="true" /></a></> : null}
                                    {connect?.stripe_account_id && !connect?.is_ready ? <> · <button type="button" className="underline underline-offset-2" onClick={() => onSyncConnect(claim)}>Sync test readiness</button></> : null}
                                </div>
                            )}
                        </div>
                    </CalmDetails>
                ))}
                {claim.audit_trail?.length > 0 && (
                    <CalmDetails summary="History" note={String(claim.audit_trail.length)}>
                        <div className="flex flex-col gap-2">{claim.audit_trail.map((event, index) => <div key={`${event.action}-${index}`} className="[overflow-wrap:anywhere]"><span className="text-chalk">{title(event.action)}</span> · {event.reason} · {formatDate(event.created_at)}</div>)}</div>
                    </CalmDetails>
                )}
            </section>
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

function ContentReviewQueues() {
    const [profiles, setProfiles] = useState([])
    const [updates, setUpdates] = useState([])
    const [reasons, setReasons] = useState({})
    const [busy, setBusy] = useState(null)
    const [error, setError] = useState(null)

    useEffect(() => {
        let cancelled = false
        Promise.all([
            APIService.adminListProfileRevisions(),
            APIService.adminListProgramUpdates(),
        ]).then(([profileData, updateData]) => {
            if (cancelled) return
            setProfiles(profileData?.revisions || [])
            setUpdates(updateData?.updates || [])
        }).catch((err) => { if (!cancelled) setError(err.message || 'Content review queues could not be loaded.') })
        return () => { cancelled = true }
    }, [])

    const review = async (kind, item, decision) => {
        const key = `${kind}-${item.id}`
        const reason = reasons[key]?.trim()
        if (!reason) return
        setBusy(key)
        setError(null)
        try {
            if (kind === 'profile') {
                await APIService.adminReviewProfileRevision(item.program.id, item.id, { decision, reason })
                setProfiles((current) => current.filter((row) => row.id !== item.id))
            } else {
                await APIService.adminReviewProgramUpdate(item.program.id, item.id, { decision, reason })
                setUpdates((current) => current.filter((row) => row.id !== item.id))
            }
        } catch (err) {
            setError(err.body?.error || err.message || 'Review could not be saved.')
        } finally {
            setBusy(null)
        }
    }

    const queue = (kind, titleText, items) => (
        <Card>
            <CardHeader><CardTitle className="font-serif text-2xl">{titleText}</CardTitle><CardDescription>{items.length} pending</CardDescription></CardHeader>
            <CardContent className="space-y-4">
                {items.length ? items.map((item) => {
                    const key = `${kind}-${item.id}`
                    return (
                        <article key={item.id} className="space-y-3 rounded-xl border p-4">
                            <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="font-semibold">{item.program?.name || `Program #${item.program?.id}`}</h3><StatusBadge value={item.status} /></div>
                            {kind === 'profile' ? (
                                <div className="space-y-2 text-sm text-foreground/80"><p className="whitespace-pre-wrap">{item.summary || 'No summary supplied.'}</p>{item.funding_purpose ? <p><strong>Purpose:</strong> {item.funding_purpose}</p> : null}{item.age_groups?.length ? <p><strong>Age groups:</strong> {item.age_groups.join(', ')}</p> : null}{item.activities?.length ? <p><strong>Activities:</strong> {item.activities.join(', ')}</p> : null}{item.official_url ? <p><strong>Official URL:</strong> {item.official_url}</p> : null}{item.safeguarding_url ? <p><strong>Safeguarding URL:</strong> {item.safeguarding_url}</p> : null}{item.media_urls?.length ? <p><strong>Media URLs:</strong> {item.media_urls.join(', ')}</p> : null}{item.external_support ? <p><strong>Support:</strong> {item.external_support.provider} · {item.external_support.url}</p> : null}{/* p2-b1 */}{item.directory ? <DirectoryReview directory={item.directory} /> : null}</div>
                            ) : (
                                <div className="space-y-2 text-sm text-foreground/80"><h4 className="font-semibold text-foreground">{item.title}</h4><p className="whitespace-pre-wrap">{item.body}</p>{item.impact ? <p><strong>Impact:</strong> {item.impact}</p> : null}</div>
                            )}
                            <Label htmlFor={`${key}-reason`}>Review reason</Label>
                            <Textarea id={`${key}-reason`} value={reasons[key] || ''} onChange={(event) => setReasons((current) => ({ ...current, [key]: event.target.value }))} placeholder="Required audit reason…" maxLength={2000} />
                            <div className="flex gap-2"><Button size="sm" disabled={busy === key || !reasons[key]?.trim()} onClick={() => review(kind, item, 'approve')} className="bg-emerald-700 hover:bg-emerald-800"><Check className="mr-1 h-4 w-4" />Approve</Button><Button size="sm" variant="outline" disabled={busy === key || !reasons[key]?.trim()} onClick={() => review(kind, item, 'reject')} className="border-rose-300 text-rose-700"><X className="mr-1 h-4 w-4" />Reject</Button></div>
                        </article>
                    )
                }) : <p className="text-sm text-muted-foreground">Nothing is waiting for review.</p>}
            </CardContent>
        </Card>
    )

    return <section className="space-y-4" aria-labelledby="content-review-heading"><div><h2 id="content-review-heading" className="m-0 text-base font-semibold text-chalk">Club content to approve</h2><p className="mt-1 text-sm text-muted-dark">Approve only content supplied by the club's verified manager.</p></div>{error ? <Alert className="border-rose-300 bg-rose-50"><AlertTriangle className="h-4 w-4" /><AlertDescription>{error}</AlertDescription></Alert> : null}<div className="grid gap-5 xl:grid-cols-2">{queue('profile', 'Profile revisions', profiles)}{queue('update', 'Program updates', updates)}</div></section>
}

const PAGE_DEFAULTS = { tab: 'registry', status: 'pending', claim: '' }
const TABS = ['registry', 'claims', 'content', 'demand']

export function AdminFunding() {
    const [page, setPage] = useUrlFilters(PAGE_DEFAULTS)
    const tab = TABS.includes(page.tab) ? page.tab : 'registry'
    const claimStatus = CLAIM_STATUS.some(([value]) => value === page.status) ? page.status : 'pending'
    const [filters, setFilters] = useState({ q: '', admission_state: 'all', registry_status: 'all' })
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
            // The decided claim leaves this list; go back to it rather than show a stale answer.
            setPage({ claim: '' }, { replace: true })
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

    const openClaim = tab === 'claims' && page.claim ? claims.find((claim) => String(claim.id) === page.claim) : null
    const waiting = claims.filter((claim) => claim.status === 'pending').length
    const startReview = (claim, action) => { setReview({ claim, action }); setReviewReason('') }

    return (
        <div className="flex flex-col gap-6">
            {openClaim ? null : <CalmHeader title="Club verification" line="Which leagues are open, and which clubs are waiting to be verified." />}

            {message ? <p role={message.type === 'error' ? 'alert' : 'status'} className="m-0 flex items-center gap-2.5 text-sm text-chalk"><StatusDot tone={message.type === 'error' ? 'warn' : 'good'} />{message.text}</p> : null}

            {openClaim ? (
                <ClaimDetail claim={openClaim} waiting={waiting} onBack={() => setPage({ claim: '' })} onReview={startReview} onSyncConnect={syncConnect} />
            ) : tab === 'claims' && page.claim && !loading ? (
                <div className="flex flex-col gap-3"><p className="m-0 text-sm text-muted-dark">That club is not in this list any more — it may already have been decided.</p><button type="button" className={`${calmPillButton} self-start`} onClick={() => setPage({ claim: '' })}>Back to the clubs waiting</button></div>
            ) : (
                <Tabs value={tab} onValueChange={(value) => setPage({ tab: value, claim: '', status: 'pending' })}>
                    <TabsList className="flex h-auto w-full flex-wrap justify-start sm:w-auto sm:self-start">
                        <TabsTrigger value="registry" className="py-2.5">League registry</TabsTrigger>
                        <TabsTrigger value="claims" className="py-2.5">Clubs waiting{!loading && claimStatus === 'pending' && waiting ? ` · ${waiting}` : ''}</TabsTrigger>
                        <TabsTrigger value="content" className="py-2.5">Content review</TabsTrigger>
                        <TabsTrigger value="demand" className="py-2.5">Demand</TabsTrigger>
                    </TabsList>
                    <TabsContent value="registry" className="mt-5"><RegistryTab leagues={leagues} loading={loading} filters={filters} setFilters={setFilters} onCreate={() => { setEditingLeague(null); setDialogOpen(true) }} onEdit={(league) => { setEditingLeague(league); setDialogOpen(true) }} onDelete={removeLeague} /></TabsContent>
                    <TabsContent value="claims" className="mt-5"><ClaimsTab claims={claims} loading={loading} status={claimStatus} onStatus={(status) => setPage({ status })} onOpen={(claim) => setPage({ claim: String(claim.id) })} /></TabsContent>
                    <TabsContent value="content" className="mt-5"><ContentReviewQueues /></TabsContent>
                    <TabsContent value="demand" className="mt-5"><DemandTab demand={demand} loading={loading} /></TabsContent>
                </Tabs>
            )}

            {dialogOpen ? <LeagueDialog open onOpenChange={setDialogOpen} league={editingLeague} onSaved={saved} /> : null}
            <Dialog open={Boolean(review)} onOpenChange={(open) => { if (!open) setReview(null) }}>
                <DialogContent>
                    <DialogHeader><DialogTitle className="text-xl font-semibold">{review?.action === 'approve' ? 'Approve organization' : review?.action === 'revoke' ? 'Revoke manager access' : 'Reject claim'}</DialogTitle><DialogDescription>{review?.claim?.program?.name} · the reason is retained in the immutable admin trail.</DialogDescription></DialogHeader>
                    <Field id="funding-review-reason" label="Review reason"><Textarea id="funding-review-reason" name="review_reason" autoComplete="off" autoFocus value={reviewReason} onChange={(e) => setReviewReason(e.target.value)} placeholder="Record the evidence decision and any follow-up…" /></Field>
                    <DialogFooter><Button variant="ghost" onClick={() => setReview(null)}>Cancel</Button><Button disabled={reviewing || !reviewReason.trim()} onClick={submitReview}>{reviewing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}{review?.action === 'approve' ? 'Approve claim' : review?.action === 'revoke' ? 'Revoke manager' : 'Reject claim'}</Button></DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    )
}
