import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
    ArrowRight,
    Building2,
    CheckCircle2,
    ChevronRight,
    Clock3,
    FileCheck2,
    Landmark,
    Loader2,
    LockKeyhole,
    MailCheck,
    MapPinned,
    ShieldCheck,
} from 'lucide-react'

import { APIService } from '@/lib/api'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'

const EMPTY_FORM = {
    leagueMode: 'approved',
    funding_league_id: '',
    club_name: '',
    legal_name: '',
    team_api_id: 'none',
    country: '',
    region: '',
    city: '',
    currency: 'USD',
    crest_url: '',
    applicant_message: '',
    official_email: '',
    authorization_method: 'official_domain_email',
    authorization_reference: '',
    organization_form: 'association',
    registration_reference: '',
    official_contact_name: '',
    official_contact_reference: '',
    safeguarding_contact_email: '',
    safeguarding_policy_url: '',
    adult_authority_attested: false,
    safeguarding_policy_attested: false,
    eligible_organization_attested: false,
    payout_control_attested: false,
    proposed_name: '',
    proposed_country: '',
    proposed_region: '',
    proposed_level: 'youth_regional',
    proposed_age_bands: 'U12, U14',
    proposed_gender_program: 'both',
    proposed_season_calendar: 'calendar_year',
    proposed_data_tier: 'self_reported',
    proposed_league_api_id: '',
}

function Field({ id, label, hint, children }) {
    return (
        <div className="space-y-2">
            <Label htmlFor={id}>{label}</Label>
            {children}
            {hint ? <p className="text-xs leading-relaxed text-muted-foreground">{hint}</p> : null}
        </div>
    )
}

function Attestation({ checked, onCheckedChange, title, description }) {
    return (
        <label className="flex cursor-pointer items-start gap-3 rounded-xl border bg-background p-4 transition-colors hover:border-emerald-300">
            <Checkbox checked={checked} onCheckedChange={onCheckedChange} className="mt-0.5" />
            <span><span className="block text-sm font-medium">{title}</span><span className="mt-1 block text-xs leading-relaxed text-muted-foreground">{description}</span></span>
        </label>
    )
}

function StepLabel({ number, title, active }) {
    return (
        <div className="flex items-center gap-3">
            <div className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold ${active ? 'bg-emerald-700 text-white' : 'bg-secondary text-muted-foreground'}`}>{number}</div>
            <span className={`text-sm font-medium ${active ? 'text-foreground' : 'text-muted-foreground'}`}>{title}</span>
        </div>
    )
}

export function ProgramClaimPage() {
    const [form, setForm] = useState(EMPTY_FORM)
    const [leagues, setLeagues] = useState([])
    const [teams, setTeams] = useState([])
    const [claims, setClaims] = useState([])
    const [teamQuery, setTeamQuery] = useState('')
    const [loading, setLoading] = useState(true)
    const [submitting, setSubmitting] = useState(false)
    const [error, setError] = useState('')
    const [submitted, setSubmitted] = useState(null)

    useEffect(() => {
        let cancelled = false
        Promise.all([
            APIService.getFundingLeagues(),
            APIService.getTeams(),
            APIService.getMyProgramClaims(),
        ]).then(([leagueData, teamData, claimData]) => {
            if (cancelled) return
            setLeagues(leagueData?.leagues || [])
            setTeams(Array.isArray(teamData) ? teamData : teamData?.teams || [])
            setClaims(claimData?.claims || [])
        }).catch((err) => {
            if (!cancelled) setError(err.message || 'Unable to load the admission form')
        }).finally(() => {
            if (!cancelled) setLoading(false)
        })
        return () => { cancelled = true }
    }, [])

    const update = (key, value) => setForm((current) => ({ ...current, [key]: value }))
    const visibleTeams = useMemo(() => {
        const query = teamQuery.trim().toLowerCase()
        const seen = new Set()
        const rows = []
        for (const team of teams) {
            const apiId = team?.team_id
            if (!apiId || !team?.slug || seen.has(apiId)) continue
            if (query && !`${team.name || ''} ${team.country || ''}`.toLowerCase().includes(query)) continue
            seen.add(apiId)
            rows.push(team)
            if (rows.length >= 60) break
        }
        return rows
    }, [teamQuery, teams])

    const chooseTeam = (value) => {
        update('team_api_id', value)
        if (value === 'none') return
        const team = teams.find((row) => String(row.team_id) === value)
        if (!team) return
        setForm((current) => ({
            ...current,
            team_api_id: value,
            club_name: team.name || current.club_name,
            country: team.country || current.country,
            crest_url: team.logo || team.logo_url || current.crest_url,
        }))
    }

    const submit = async (event) => {
        event.preventDefault()
        setSubmitting(true)
        setError('')
        const evidence = {
            adult_authority_attested: form.adult_authority_attested,
            official_email: form.official_email || null,
            authorization_method: form.authorization_method,
            authorization_reference: form.authorization_reference || null,
            organization_form: form.organization_form,
            registration_reference: form.registration_reference,
            official_contact_name: form.official_contact_name,
            official_contact_reference: form.official_contact_reference,
            safeguarding_contact_email: form.safeguarding_contact_email,
            safeguarding_policy_url: form.safeguarding_policy_url || null,
            safeguarding_policy_attested: form.safeguarding_policy_attested,
            eligible_organization_attested: form.eligible_organization_attested,
            payout_control_attested: form.payout_control_attested,
        }
        const payload = {
            club_name: form.club_name,
            legal_name: form.legal_name,
            team_api_id: form.team_api_id === 'none' ? null : Number(form.team_api_id),
            country: form.country,
            region: form.region,
            city: form.city || null,
            currency: form.currency.toUpperCase(),
            crest_url: form.crest_url || null,
            applicant_message: form.applicant_message || null,
            evidence,
        }
        if (form.leagueMode === 'approved') {
            payload.funding_league_id = Number(form.funding_league_id)
        } else {
            payload.proposed_league = {
                name: form.proposed_name,
                country: form.proposed_country,
                region: form.proposed_region,
                level: form.proposed_level,
                age_bands: form.proposed_age_bands.split(',').map((item) => item.trim()).filter(Boolean),
                gender_program: form.proposed_gender_program,
                season_calendar: form.proposed_season_calendar,
                data_tier: form.proposed_data_tier === 'api_football'
                    ? `api_football:${form.proposed_league_api_id}`
                    : form.proposed_data_tier,
            }
        }
        try {
            const response = await APIService.submitClubProgramClaim(payload)
            setSubmitted(response)
            setClaims((current) => [response.claim, ...current])
            const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
            window.scrollTo({ top: 0, behavior: reduceMotion ? 'auto' : 'smooth' })
        } catch (err) {
            setError(err.message || 'Unable to submit the club claim')
        } finally {
            setSubmitting(false)
        }
    }

    const registerAnother = () => {
        setForm({ ...EMPTY_FORM })
        setTeamQuery('')
        setError('')
        setSubmitted(null)
    }

    if (loading) {
        return <div className="flex min-h-[60vh] items-center justify-center gap-2 text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin motion-reduce:animate-none" />Loading program admission…</div>
    }

    if (submitted) {
        return (
            <div className="mx-auto max-w-3xl px-4 py-16">
                <Card className="overflow-hidden border-0 shadow-2xl">
                    <div className="bg-[#0b1f19] px-8 py-10 text-white"><div className="flex h-12 w-12 items-center justify-center rounded-full bg-emerald-300/15"><CheckCircle2 className="h-6 w-6 text-emerald-200" /></div><p className="mt-6 text-xs font-semibold uppercase tracking-[0.22em] text-emerald-200/70">Application received</p><h1 className="mt-2 font-serif text-4xl">{submitted.claim?.program?.name}</h1><p className="mt-3 max-w-xl text-emerald-50/70">Your club claim is pending an adult-authority and organization review. Approval—not this submission—creates a club-manager grant.</p></div>
                    <CardContent className="space-y-5 p-8">
                        <div className="flex items-start gap-3 rounded-xl border bg-secondary/50 p-4"><Clock3 className="mt-0.5 h-5 w-5 text-amber-700" /><div><p className="font-medium">{submitted.league_waitlisted ? 'League proposal added to MJ’s waitlist' : 'Club evidence entered the approval queue'}</p><p className="mt-1 text-sm text-muted-foreground">No Stripe onboarding or funding begins until the platform review is approved.</p></div></div>
                        <div className="flex flex-wrap gap-3"><Button onClick={registerAnother}>Register another program</Button><Button variant="outline" asChild><Link to="/">Return home</Link></Button></div>
                    </CardContent>
                </Card>
            </div>
        )
    }

    return (
        <div className="min-h-screen bg-[#f4f1e8] py-10 text-stone-950">
            <div className="mx-auto max-w-6xl px-4">
                <header className="relative overflow-hidden rounded-[2rem] bg-[#0b1f19] px-6 py-10 text-white shadow-2xl sm:px-10">
                    <div className="absolute right-[-6rem] top-[-8rem] h-72 w-72 rounded-full border-[48px] border-emerald-100/5" />
                    <div className="relative max-w-3xl"><Badge className="border-emerald-200/20 bg-emerald-200/10 text-emerald-100">Club representatives · F2 admission</Badge><h1 className="mt-5 font-serif text-4xl font-semibold tracking-tight sm:text-6xl">Put your program on the verified path.</h1><p className="mt-5 max-w-2xl text-base leading-relaxed text-emerald-50/70">Register a legal club or academy program—not an individual player. League eligibility, adult authority, and safeguarding evidence are reviewed before any badge is shown.</p></div>
                </header>

                <div className="mt-6 grid gap-6 lg:grid-cols-[260px_1fr]">
                    <aside className="space-y-5 lg:sticky lg:top-6 lg:self-start">
                        <Card className="border-stone-200 bg-white/80"><CardHeader><CardTitle className="font-serif text-xl">Admission route</CardTitle></CardHeader><CardContent className="space-y-4"><StepLabel number="1" title="League gate" active /><ChevronRight className="ml-2 h-4 w-4 text-stone-300" /><StepLabel number="2" title="Program identity" active /><ChevronRight className="ml-2 h-4 w-4 text-stone-300" /><StepLabel number="3" title="Authority evidence" active /><ChevronRight className="ml-2 h-4 w-4 text-stone-300" /><StepLabel number="4" title="MJ review" /></CardContent></Card>
                        <Card className="border-stone-200 bg-white/80"><CardContent className="space-y-3 p-5"><div className="flex items-center gap-2 font-medium"><LockKeyhole className="h-4 w-4 text-emerald-800" />Private by default</div><p className="text-xs leading-relaxed text-muted-foreground">Evidence metadata is reviewer-only. Never submit a minor’s ID or bank data; Stripe-hosted onboarding handles organization KYC later for approved US programs.</p></CardContent></Card>
                        {claims.length > 0 ? <Card className="border-stone-200 bg-white/80"><CardHeader><CardTitle className="text-base">Your claims</CardTitle></CardHeader><CardContent className="space-y-3">{claims.slice(0, 3).map((claim) => <div key={claim.id} className="border-l-2 border-amber-500 pl-3"><p className="text-sm font-medium">{claim.program?.name}</p><p className="text-xs capitalize text-muted-foreground">{claim.status}</p></div>)}</CardContent></Card> : null}
                    </aside>

                    <form onSubmit={submit} className="space-y-6">
                        {error ? <Alert className="border-rose-300 bg-rose-50 text-rose-900"><AlertDescription>{error}</AlertDescription></Alert> : null}
                        <Card className="border-stone-200 bg-white/90 shadow-lg">
                            <CardHeader><div className="flex items-center gap-3"><div className="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-100"><Landmark className="h-5 w-5 text-emerald-900" /></div><div><CardTitle className="font-serif text-2xl">1. League gate</CardTitle><CardDescription>Choose an MJ-approved open league or submit a proposal to the waitlist.</CardDescription></div></div></CardHeader>
                            <CardContent className="space-y-5">
                                <div className="grid grid-cols-2 rounded-xl bg-stone-100 p-1"><button type="button" onClick={() => update('leagueMode', 'approved')} className={`rounded-lg px-4 py-2.5 text-sm font-medium transition ${form.leagueMode === 'approved' ? 'bg-white shadow-sm' : 'text-muted-foreground'}`}>Approved league</button><button type="button" onClick={() => update('leagueMode', 'propose')} className={`rounded-lg px-4 py-2.5 text-sm font-medium transition ${form.leagueMode === 'propose' ? 'bg-white shadow-sm' : 'text-muted-foreground'}`}>Propose a league</button></div>
                                {form.leagueMode === 'approved' ? (
                                    <Field id="claim-funding-league" label="Open league">
                                        <Select name="funding_league_id" value={form.funding_league_id} onValueChange={(value) => update('funding_league_id', value)} required><SelectTrigger id="claim-funding-league"><SelectValue placeholder="Select an approved league" /></SelectTrigger><SelectContent>{leagues.map((league) => <SelectItem key={league.id} value={String(league.id)}>{league.name} · {league.region}, {league.country}</SelectItem>)}</SelectContent></Select>
                                        {leagues.length === 0 ? <p className="text-xs text-amber-800">No leagues are currently open. Propose one for MJ review.</p> : null}
                                    </Field>
                                ) : (
                                    <div className="grid gap-4 sm:grid-cols-2">
                                        <Field id="claim-proposed-league-name" label="League name"><Input id="claim-proposed-league-name" name="proposed_name" autoComplete="off" value={form.proposed_name} onChange={(e) => update('proposed_name', e.target.value)} required /></Field>
                                        <Field id="claim-proposed-country" label="Country"><Input id="claim-proposed-country" name="proposed_country" autoComplete="country-name" value={form.proposed_country} onChange={(e) => update('proposed_country', e.target.value)} required /></Field>
                                        <Field id="claim-proposed-region" label="Region"><Input id="claim-proposed-region" name="proposed_region" autoComplete="address-level1" value={form.proposed_region} onChange={(e) => update('proposed_region', e.target.value)} required /></Field>
                                        <Field id="claim-proposed-level" label="Level"><Select name="proposed_level" value={form.proposed_level} onValueChange={(value) => update('proposed_level', value)}><SelectTrigger id="claim-proposed-level"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="pro_academy">Pro academy</SelectItem><SelectItem value="youth_national">Youth · national</SelectItem><SelectItem value="youth_regional">Youth · regional</SelectItem><SelectItem value="recreational">Recreational</SelectItem></SelectContent></Select></Field>
                                        <Field id="claim-proposed-age-bands" label="Age bands"><Input id="claim-proposed-age-bands" name="proposed_age_bands" autoComplete="off" value={form.proposed_age_bands} onChange={(e) => update('proposed_age_bands', e.target.value)} required /></Field>
                                        <Field id="claim-proposed-gender-program" label="Gender program"><Select name="proposed_gender_program" value={form.proposed_gender_program} onValueChange={(value) => update('proposed_gender_program', value)}><SelectTrigger id="claim-proposed-gender-program"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="boys">Boys</SelectItem><SelectItem value="girls">Girls</SelectItem><SelectItem value="both">Both</SelectItem></SelectContent></Select></Field>
                                        <Field id="claim-proposed-season" label="Season"><Select name="proposed_season_calendar" value={form.proposed_season_calendar} onValueChange={(value) => update('proposed_season_calendar', value)}><SelectTrigger id="claim-proposed-season"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="aug_may">August–May</SelectItem><SelectItem value="calendar_year">Calendar year</SelectItem><SelectItem value="fall_spring">Fall–spring</SelectItem></SelectContent></Select></Field>
                                        <Field id="claim-proposed-data-tier" label="Data tier"><Select name="proposed_data_tier" value={form.proposed_data_tier} onValueChange={(value) => update('proposed_data_tier', value)}><SelectTrigger id="claim-proposed-data-tier"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="self_reported">Self-reported</SelectItem><SelectItem value="film_room">Film Room</SelectItem><SelectItem value="api_football">API-Football</SelectItem></SelectContent></Select></Field>
                                        {form.proposed_data_tier === 'api_football' ? <Field id="claim-proposed-league-api-id" label="API-Football league ID"><Input id="claim-proposed-league-api-id" name="proposed_league_api_id" type="number" min="1" value={form.proposed_league_api_id} onChange={(e) => update('proposed_league_api_id', e.target.value)} required /></Field> : null}
                                    </div>
                                )}
                            </CardContent>
                        </Card>

                        <Card className="border-stone-200 bg-white/90 shadow-lg">
                            <CardHeader><div className="flex items-center gap-3"><div className="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-100"><Building2 className="h-5 w-5 text-emerald-900" /></div><div><CardTitle className="font-serif text-2xl">2. Program identity</CardTitle><CardDescription>Link provider coverage where it exists; standalone grassroots clubs are welcome.</CardDescription></div></div></CardHeader>
                            <CardContent className="grid gap-4 sm:grid-cols-2">
                                <div className="space-y-4 sm:col-span-2">
                                    <Field id="claim-covered-team-filter" label="Find a covered team"><Input id="claim-covered-team-filter" name="covered_team_filter" autoComplete="off" value={teamQuery} onChange={(e) => setTeamQuery(e.target.value)} placeholder="Search by team or country…" /></Field>
                                    <Field id="claim-covered-team" label="Covered team (optional)" hint="Selecting a covered team uses its provider-controlled name and crest."><Select name="team_api_id" value={form.team_api_id} onValueChange={chooseTeam}><SelectTrigger id="claim-covered-team"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="none">Free-standing registered club</SelectItem>{visibleTeams.map((team) => <SelectItem key={team.team_id} value={String(team.team_id)}>{team.name} · {team.country}</SelectItem>)}</SelectContent></Select></Field>
                                </div>
                                <Field id="claim-club-name" label="Club / program name"><Input id="claim-club-name" name="club_name" autoComplete="organization" value={form.club_name} onChange={(e) => update('club_name', e.target.value)} required /></Field>
                                <Field id="claim-legal-name" label="Legal organization name"><Input id="claim-legal-name" name="legal_name" autoComplete="organization" value={form.legal_name} onChange={(e) => update('legal_name', e.target.value)} required /></Field>
                                <Field id="claim-country" label="Country"><Input id="claim-country" name="country" autoComplete="country-name" value={form.country} onChange={(e) => update('country', e.target.value)} required /></Field>
                                <Field id="claim-region" label="Region / state"><Input id="claim-region" name="region" autoComplete="address-level1" value={form.region} onChange={(e) => update('region', e.target.value)} required /></Field>
                                <Field id="claim-city" label="City"><Input id="claim-city" name="city" autoComplete="address-level2" value={form.city} onChange={(e) => update('city', e.target.value)} /></Field>
                                <Field id="claim-currency" label="Currency" hint="Money remains disabled in F2."><Input id="claim-currency" name="currency" autoComplete="off" maxLength={3} value={form.currency} onChange={(e) => update('currency', e.target.value.toUpperCase())} required /></Field>
                                <div className="sm:col-span-2"><Field id="claim-crest-url" label="Official crest URL (optional)"><Input id="claim-crest-url" name="crest_url" type="url" autoComplete="url" value={form.crest_url} onChange={(e) => update('crest_url', e.target.value)} placeholder="https://…" /></Field></div>
                            </CardContent>
                        </Card>

                        <Card className="border-stone-200 bg-white/90 shadow-lg">
                            <CardHeader><div className="flex items-center gap-3"><div className="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-100"><FileCheck2 className="h-5 w-5 text-emerald-900" /></div><div><CardTitle className="font-serif text-2xl">3. Authority + safeguarding</CardTitle><CardDescription>Private evidence metadata for MJ’s review. Weak or mismatched evidence escalates.</CardDescription></div></div></CardHeader>
                            <CardContent className="space-y-5">
                                <div className="grid gap-4 sm:grid-cols-2">
                                    <Field id="claim-authorization-method" label="Authorization route"><Select name="authorization_method" value={form.authorization_method} onValueChange={(value) => update('authorization_method', value)}><SelectTrigger id="claim-authorization-method"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="official_domain_email">Official-domain email</SelectItem><SelectItem value="signed_officer_authorization">Signed officer authorization</SelectItem></SelectContent></Select></Field>
                                    <Field id="claim-organization-form" label="Organization form"><Select name="organization_form" value={form.organization_form} onValueChange={(value) => update('organization_form', value)}><SelectTrigger id="claim-organization-form"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="nonprofit">Nonprofit</SelectItem><SelectItem value="company">Company</SelectItem><SelectItem value="association">Association</SelectItem><SelectItem value="school">School</SelectItem><SelectItem value="municipal">Municipal</SelectItem><SelectItem value="other_organization">Other organization</SelectItem></SelectContent></Select></Field>
                                    <Field id="claim-official-email" label="Official email"><Input id="claim-official-email" name="official_email" type="email" autoComplete="email" spellCheck={false} value={form.official_email} onChange={(e) => update('official_email', e.target.value)} required={form.authorization_method === 'official_domain_email'} /></Field>
                                    {form.authorization_method === 'signed_officer_authorization' ? <Field id="claim-authorization-reference" label="Signed authorization reference"><Input id="claim-authorization-reference" name="authorization_reference" autoComplete="off" value={form.authorization_reference} onChange={(e) => update('authorization_reference', e.target.value)} required /></Field> : null}
                                    <Field id="claim-registration-reference" label="League / legal registration reference"><Input id="claim-registration-reference" name="registration_reference" autoComplete="off" value={form.registration_reference} onChange={(e) => update('registration_reference', e.target.value)} required /></Field>
                                    <Field id="claim-official-contact-name" label="Official contact name"><Input id="claim-official-contact-name" name="official_contact_name" autoComplete="name" value={form.official_contact_name} onChange={(e) => update('official_contact_name', e.target.value)} required /></Field>
                                    <Field id="claim-official-contact-reference" label="Official contact cross-check"><Input id="claim-official-contact-reference" name="official_contact_reference" autoComplete="off" value={form.official_contact_reference} onChange={(e) => update('official_contact_reference', e.target.value)} required /></Field>
                                    <Field id="claim-safeguarding-email" label="Safeguarding contact email"><Input id="claim-safeguarding-email" name="safeguarding_contact_email" type="email" autoComplete="email" spellCheck={false} value={form.safeguarding_contact_email} onChange={(e) => update('safeguarding_contact_email', e.target.value)} required /></Field>
                                    <div className="sm:col-span-2"><Field id="claim-safeguarding-policy-url" label="Safeguarding policy URL (optional)"><Input id="claim-safeguarding-policy-url" name="safeguarding_policy_url" type="url" autoComplete="url" value={form.safeguarding_policy_url} onChange={(e) => update('safeguarding_policy_url', e.target.value)} placeholder="https://…" /></Field></div>
                                </div>
                                <div className="grid gap-3 sm:grid-cols-2">
                                    <Attestation checked={form.adult_authority_attested} onCheckedChange={(value) => update('adult_authority_attested', Boolean(value))} title="I am an authorized adult" description="I have authority to represent this organization and am not applying on behalf of a minor personally." />
                                    <Attestation checked={form.safeguarding_policy_attested} onCheckedChange={(value) => update('safeguarding_policy_attested', Boolean(value))} title="Safeguarding controls exist" description="The organization has a safeguarding contact and policy/process for youth participants." />
                                    <Attestation checked={form.eligible_organization_attested} onCheckedChange={(value) => update('eligible_organization_attested', Boolean(value))} title="Organization-only recipient" description="Any future recipient is the eligible legal organization—not a coach, parent, manager, or player." />
                                    <Attestation checked={form.payout_control_attested} onCheckedChange={(value) => update('payout_control_attested', Boolean(value))} title="Organization controls payouts" description="Any future payout account will be controlled by the legal organization." />
                                </div>
                                <Field id="claim-applicant-message" label="Applicant note (optional)"><Textarea id="claim-applicant-message" name="applicant_message" autoComplete="off" value={form.applicant_message} onChange={(e) => update('applicant_message', e.target.value)} placeholder="Add context that helps MJ cross-check the application…" /></Field>
                            </CardContent>
                        </Card>

                        <div className="flex flex-col justify-between gap-4 rounded-2xl bg-[#0b1f19] p-6 text-white sm:flex-row sm:items-center"><div><div className="flex items-center gap-2 font-medium"><ShieldCheck className="h-5 w-5 text-emerald-200" />Submit for human review</div><p className="mt-1 text-xs text-emerald-50/60">No badge, payout access, or club-manager grant is created automatically.</p></div><Button type="submit" disabled={submitting} className="bg-emerald-300 text-emerald-950 hover:bg-emerald-200">{submitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin motion-reduce:animate-none" /> : <MailCheck className="mr-2 h-4 w-4" />}Send application <ArrowRight className="ml-2 h-4 w-4" /></Button></div>
                    </form>
                </div>
            </div>
        </div>
    )
}
