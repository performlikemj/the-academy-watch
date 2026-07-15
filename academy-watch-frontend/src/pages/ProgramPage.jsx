import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
    ArrowLeft,
    Bell,
    Check,
    ExternalLink,
    FileText,
    Landmark,
    Loader2,
    MapPin,
    ShieldCheck,
    Sparkles,
    Users,
} from 'lucide-react'

import { APIService } from '@/lib/api'
import { useAuth, useAuthUI } from '@/context/AuthContext'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

const PROVENANCE_COPY = {
    'Provider-covered': 'Identity and roster linkage come from the platform’s football-data provider.',
    'Film Room-verified': 'Identity is supported by finalized footage and human-confirmed Film Room review.',
    'Self-reported': 'Program identity was supplied by the club and remains visibly labeled.',
}

function initials(name) {
    return String(name || 'Program').split(/\s+/).slice(0, 2).map((part) => part[0]).join('').toUpperCase()
}

export function ProgramPage() {
    const { slug } = useParams()

    return <ProgramPageContent key={slug} slug={slug} />
}

function ProgramPageContent({ slug }) {
    const auth = useAuth()
    const { openLoginModal } = useAuthUI()
    const [program, setProgram] = useState(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState('')
    const [saving, setSaving] = useState(false)
    const [saved, setSaved] = useState(false)

    useEffect(() => {
        let cancelled = false
        APIService.getProgram(slug)
            .then((data) => { if (!cancelled) setProgram(data?.program || null) })
            .catch((err) => { if (!cancelled) setError(err.message || 'Program not found') })
            .finally(() => { if (!cancelled) setLoading(false) })
        return () => { cancelled = true }
    }, [slug])

    const save = async () => {
        if (!auth.token) {
            openLoginModal()
            return
        }
        setSaving(true)
        setError('')
        try {
            await APIService.saveProgram(slug, true)
            setSaved(true)
        } catch (err) {
            setError(err.message || 'Unable to save this program')
        } finally {
            setSaving(false)
        }
    }

    if (loading) {
        return <div className="flex min-h-[65vh] items-center justify-center gap-2 text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin motion-reduce:animate-none" />Loading program…</div>
    }

    if (!program) {
        return (
            <div className="mx-auto max-w-xl px-4 py-20 text-center">
                <Landmark className="mx-auto h-9 w-9 text-muted-foreground" />
                <h1 className="mt-4 font-serif text-3xl">Program unavailable</h1>
                <p className="mt-2 text-muted-foreground">{error || 'This page is not published.'}</p>
                <Button asChild variant="outline" className="mt-6"><Link to="/"><ArrowLeft className="mr-2 h-4 w-4" />Return home</Link></Button>
            </div>
        )
    }

    const location = [program.city, program.region, program.country].filter(Boolean).join(', ')
    const provenanceLabel = program.provenance?.label || 'Self-reported'
    const provided = program.program_provided

    return (
        <div className="min-h-screen bg-[#efece2] text-stone-950">
            <section className="relative overflow-hidden bg-[#081c17] text-white">
                <div className="absolute inset-0 opacity-[0.12]" style={{ backgroundImage: 'linear-gradient(rgba(255,255,255,.22) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.22) 1px, transparent 1px)', backgroundSize: '52px 52px' }} />
                <div className="absolute left-1/2 top-1/2 h-80 w-48 -translate-x-1/2 -translate-y-1/2 rounded-[50%] border border-white/20" />
                <div className="relative mx-auto max-w-6xl px-4 py-14 sm:py-20">
                    <Link to="/programs/claim" className="mb-10 inline-flex items-center text-xs font-semibold uppercase tracking-[0.18em] text-emerald-200/70 hover:text-emerald-100"><ArrowLeft className="mr-2 h-3.5 w-3.5" />Program registry</Link>
                    <div className="grid items-end gap-8 lg:grid-cols-[1fr_auto]">
                        <div className="flex min-w-0 flex-col gap-6 sm:flex-row sm:items-center">
                            <div className="flex h-28 w-28 shrink-0 items-center justify-center overflow-hidden rounded-[1.75rem] border border-white/20 bg-white/10 shadow-2xl">
                                {program.crest_url ? <img src={program.crest_url} alt={`${program.name} crest`} width={112} height={112} className="h-full w-full object-contain p-3" /> : <span className="font-serif text-3xl text-emerald-100">{initials(program.name)}</span>}
                            </div>
                            <div className="min-w-0">
                                <div className="mb-3 flex flex-wrap items-center gap-2">
                                    {program.is_verified_program ? <Badge className="border-emerald-200/30 bg-emerald-200 text-emerald-950"><ShieldCheck className="mr-1 h-3.5 w-3.5" />Verified program</Badge> : null}
                                    <Badge className="border-white/20 bg-white/10 text-white">{provenanceLabel}</Badge>
                                </div>
                                <h1 className="break-words font-serif text-4xl font-semibold tracking-tight [overflow-wrap:anywhere] sm:text-6xl">{program.name}</h1>
                                <div className="mt-4 flex min-w-0 flex-wrap gap-x-5 gap-y-2 text-sm text-emerald-50/70"><span className="inline-flex min-w-0 break-words [overflow-wrap:anywhere]"><Landmark className="mr-2 h-4 w-4 shrink-0" />{program.league?.name}</span><span className="inline-flex min-w-0 break-words [overflow-wrap:anywhere]"><MapPin className="mr-2 h-4 w-4 shrink-0" />{location}</span></div>
                            </div>
                        </div>
                        <Button onClick={save} disabled={saving || saved} className="h-12 rounded-full bg-emerald-200 px-6 text-emerald-950 hover:bg-emerald-100">
                            {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin motion-reduce:animate-none" /> : saved ? <Check className="mr-2 h-4 w-4" /> : <Bell className="mr-2 h-4 w-4" />}
                            {saved ? 'Saved for future support' : 'Save this program'}
                        </Button>
                    </div>
                </div>
            </section>

            <main className="mx-auto grid max-w-6xl gap-6 px-4 py-10 lg:grid-cols-[1fr_340px]">
                <div className="space-y-6">
                    {error ? <Alert className="border-rose-300 bg-rose-50"><AlertDescription>{error}</AlertDescription></Alert> : null}
                    <Card className="border-stone-200 bg-white/80 shadow-sm">
                        <CardHeader><div className="flex items-center gap-3"><div className="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-100"><FileText className="h-5 w-5 text-emerald-900" /></div><div><CardTitle className="font-serif text-2xl">Program overview</CardTitle><CardDescription>{provided?.label || 'Program-provided content'}</CardDescription></div></div></CardHeader>
                        <CardContent className="space-y-5">
                            {provided ? (
                                <>
                                    {provided.summary ? <p className="max-w-3xl break-words text-base leading-7 text-stone-700 [overflow-wrap:anywhere]">{provided.summary}</p> : null}
                                    <div className="grid gap-4 sm:grid-cols-2">
                                        <div className="min-w-0 rounded-xl bg-stone-100 p-4"><p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Age groups</p><p className="mt-2 break-words font-medium [overflow-wrap:anywhere]">{provided.age_groups?.join(' · ') || 'Not supplied'}</p></div>
                                        <div className="min-w-0 rounded-xl bg-stone-100 p-4"><p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Activities</p><p className="mt-2 break-words font-medium [overflow-wrap:anywhere]">{provided.activities?.join(' · ') || 'Not supplied'}</p></div>
                                    </div>
                                    {provided.funding_purpose ? <div className="min-w-0 border-l-4 border-amber-400 pl-4"><p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Program-wide use</p><p className="mt-1 break-words text-stone-700 [overflow-wrap:anywhere]">{provided.funding_purpose}</p></div> : null}
                                </>
                            ) : (
                                <div className="rounded-xl border border-dashed border-stone-300 bg-stone-50 px-5 py-8"><p className="font-medium">No program-provided overview has been approved yet.</p><p className="mt-1 text-sm text-stone-500">The registry facts above remain available without invented placeholder content.</p></div>
                            )}
                        </CardContent>
                    </Card>

                    {program.roster_links?.team_page ? (
                        <Card className="border-stone-200 bg-white/80 shadow-sm"><CardHeader><CardTitle className="flex items-center gap-2 font-serif text-2xl"><Users className="h-5 w-5 text-emerald-800" />Covered roster</CardTitle><CardDescription>This program maps to an existing provider-covered Team.</CardDescription></CardHeader><CardContent><Button variant="outline" asChild><Link to={program.roster_links.team_page}>View team + academy roster <ExternalLink className="ml-2 h-4 w-4" /></Link></Button></CardContent></Card>
                    ) : null}
                </div>

                <aside className="space-y-5">
                    <Card className="border-0 bg-[#f5c95d] text-stone-950 shadow-lg"><CardHeader><div className="flex h-10 w-10 items-center justify-center rounded-full bg-stone-950/10"><Sparkles className="h-5 w-5" /></div><CardTitle className="font-serif text-2xl">Support is not live yet</CardTitle><CardDescription className="text-stone-700">F2 establishes identity and verification only. There is no checkout or live money processing on this page.</CardDescription></CardHeader></Card>
                    <Card className="border-stone-200 bg-white/80"><CardHeader><CardTitle className="font-serif text-xl">What the badge means</CardTitle></CardHeader><CardContent className="space-y-3 text-sm text-stone-600"><p className="flex gap-2"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-800" /><span>MJ approved the organization and an active adult manager grant exists.</span></p><p className="flex gap-2"><Landmark className="mt-0.5 h-4 w-4 shrink-0 text-emerald-800" /><span>US programs also require test-mode Connect readiness; non-US programs remain informational.</span></p><p className="text-xs text-stone-500">It is not a charity, safeguarding, tax, or every-statement accreditation.</p></CardContent></Card>
                    <Card className="border-stone-200 bg-white/80"><CardHeader><CardTitle className="text-base">Data provenance</CardTitle></CardHeader><CardContent><Badge variant="outline">{provenanceLabel}</Badge><p className="mt-3 text-sm leading-relaxed text-stone-600">{PROVENANCE_COPY[provenanceLabel] || PROVENANCE_COPY['Self-reported']}</p></CardContent></Card>
                </aside>
            </main>
        </div>
    )
}
