import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
    ArrowLeft,
    ArrowUpRight,
    Bell,
    Check,
    Landmark,
    Loader2,
    ShieldCheck,
} from 'lucide-react'

import { APIService } from '@/lib/api'
import { useAuth, useAuthUI } from '@/context/AuthContext'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { FactRow, QuietNote, SectionHeading, TeaserBlock } from '@/components/public/Floodlight'

const PROVENANCE_COPY = {
    'Provider-covered': 'Identity and roster linkage come from the platform’s football-data provider.',
    'Film Room-verified': 'Identity is supported by finalized footage and human-confirmed Film Room review.',
    'Self-reported': 'Program identity was supplied by the club and remains visibly labeled.',
}

// Floodlight club green when a club has not set its own colours.
const DEFAULT_PRIMARY = '#0F3D2E'
const DEFAULT_ACCENT = '#CFAE62'

function initials(name) {
    return String(name || 'Program').split(/\s+/).slice(0, 2).map((part) => part[0]).join('').toUpperCase()
}

function safeColor(value, fallback) {
    return /^#[0-9a-fA-F]{6}$/.test(String(value || '')) ? value : fallback
}

function formatDate(value) {
    if (!value) return null
    const date = new Date(value)
    return Number.isNaN(date.getTime())
        ? null
        : date.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
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
        return (
            <div className="flex min-h-[65vh] items-center justify-center gap-3 text-muted-foreground" role="status">
                <Loader2 className="h-5 w-5 animate-spin motion-reduce:animate-none" />
                <span className="eyebrow">Loading club</span>
            </div>
        )
    }

    if (!program) {
        return (
            <div className="floodlight-container flex min-h-[65vh] flex-col items-start justify-center py-20">
                <p className="eyebrow">Club page</p>
                <h1 className="display mt-4 text-[44px] sm:text-[64px]">This club page isn’t available.</h1>
                <p className="mt-4 max-w-lg text-muted-foreground">{error || 'This page is not published.'}</p>
                <Button asChild variant="outline" className="mt-8"><Link to="/"><ArrowLeft className="h-4 w-4" />Return home</Link></Button>
            </div>
        )
    }

    const location = [program.city, program.region, program.country].filter(Boolean).join(', ')
    const provenanceLabel = program.provenance?.label || 'Self-reported'
    const provided = program.program_provided
    const primary = safeColor(program.brand?.primary_color, DEFAULT_PRIMARY)
    const accent = safeColor(program.brand?.accent_color, DEFAULT_ACCENT)
    const banner = program.brand?.banner_url || null
    const heroMeta = [program.league?.name, location].filter(Boolean)
    const updates = program.updates || []

    return (
        <div className="min-h-screen bg-chalk text-ink">
            <section
                className="dark relative isolate overflow-hidden text-chalk"
                style={{ backgroundColor: primary }}
                aria-labelledby="club-name"
            >
                {banner ? (
                    <>
                        <img src={banner} alt="" className="absolute inset-0 -z-20 h-full w-full object-cover opacity-80" />
                        <div className="absolute inset-0 -z-10 bg-night/35" />
                        <div className="absolute inset-x-0 bottom-0 -z-10 h-3/5 bg-gradient-to-b from-night/0 to-night/95" />
                    </>
                ) : (
                    <div className="absolute inset-x-0 bottom-0 -z-10 h-2/3 bg-gradient-to-b from-night/0 to-night/45" />
                )}
                <div className={`floodlight-container flex flex-col justify-end pb-12 pt-10 sm:pb-16 ${banner ? 'min-h-[520px] lg:min-h-[600px]' : 'min-h-[380px] lg:min-h-[440px]'}`}>
                    <Link to="/programs/claim" className="eyebrow mb-auto inline-flex items-center gap-2 self-start text-chalk/70 hover:text-chalk">
                        <ArrowLeft className="h-3.5 w-3.5" />Club registry
                    </Link>
                    <div className="mt-12 flex flex-col gap-8 lg:flex-row lg:items-end">
                        <div
                            className="flex h-24 w-24 shrink-0 items-center justify-center overflow-hidden rounded-[20px] border border-chalk/25 sm:h-[132px] sm:w-[132px] sm:rounded-[26px]"
                            style={{ backgroundColor: primary, color: accent }}
                        >
                            {program.crest_url
                                ? <img src={program.crest_url} alt={`${program.name} crest`} width={132} height={132} className="h-full w-full object-contain p-3" />
                                : <span className="display text-[44px] sm:text-[60px]">{initials(program.name)}</span>}
                        </div>
                        <div className="min-w-0 flex-1">
                            <div className="eyebrow flex flex-wrap gap-x-5 gap-y-1">
                                {program.is_verified_program ? <span className="text-gold">Verified club</span> : null}
                                <span className="text-muted-dark">{provenanceLabel}</span>
                            </div>
                            <h1 id="club-name" className="display mt-3 break-words text-[48px] leading-[.92] [overflow-wrap:anywhere] sm:text-[72px] lg:text-[96px]">{program.name}</h1>
                            {heroMeta.length ? <p className="mt-4 text-base text-chalk/80">{heroMeta.join(' · ')}</p> : null}
                        </div>
                        <Button onClick={save} disabled={saving || saved} variant="on-dark" size="lg" className="h-12 self-start lg:self-end">
                            {saving ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" /> : saved ? <Check className="h-4 w-4" /> : <Bell className="h-4 w-4" />}
                            {saved ? 'Saved for future support' : 'Save this program'}
                        </Button>
                    </div>
                </div>
            </section>

            <div className="floodlight-container grid gap-16 py-14 sm:py-16 lg:grid-cols-[minmax(0,1fr)_380px]">
                <div className="min-w-0 space-y-16">
                    {error ? <Alert className="border-danger/40 text-danger"><AlertDescription>{error}</AlertDescription></Alert> : null}

                    <section aria-labelledby="club-about">
                        <SectionHeading id="club-about" title="About the club" meta={provided?.label || 'Program-provided'} />
                        {provided ? (
                            <div className="mt-6">
                                {provided.summary ? <p className="display max-w-3xl whitespace-pre-line break-words text-[24px] leading-[1.25] [overflow-wrap:anywhere] sm:text-[28px]">{provided.summary}</p> : null}
                                <div className="mt-8 border-t border-border">
                                    <FactRow label="Age groups">{provided.age_groups?.join(' · ') || 'Not supplied'}</FactRow>
                                    <FactRow label="Activities">{provided.activities?.join(' · ') || 'Not supplied'}</FactRow>
                                    {provided.funding_purpose ? <FactRow label="Program-wide use">{provided.funding_purpose}</FactRow> : null}
                                </div>
                            </div>
                        ) : (
                            <QuietNote title="The club hasn’t added its story yet." className="mt-2">
                                What you see above comes from the club registry. Nothing on this page is invented to fill the space.
                            </QuietNote>
                        )}
                    </section>

                    <section aria-labelledby="club-opportunities">
                        <SectionHeading id="club-opportunities" title="Opportunities" meta="Coming soon" />
                        <TeaserBlock
                            className="mt-6"
                            feature="opportunities"
                            eyebrow="Trials · open sessions · places to fill"
                            title="Straight from the club, soon."
                            lede="Clubs will be able to post trials and open sessions here, and you’ll apply in about a minute. Leave your email and we’ll tell you when it opens."
                        />
                    </section>

                    {updates.length ? (
                        <section aria-labelledby="club-updates">
                            <SectionHeading id="club-updates" title="Latest from the club" meta={`${updates.length} ${updates.length === 1 ? 'update' : 'updates'}`} />
                            <p className="mt-3 text-sm text-muted-foreground">Approved updates from the club team.</p>
                            <div className="mt-4">
                                {updates.map((update) => (
                                    <article key={update.id} className="border-b border-border py-7">
                                        <div className="flex flex-col justify-between gap-1 sm:flex-row sm:items-baseline sm:gap-6">
                                            <h3 className="display text-[28px] leading-tight">{update.title}</h3>
                                            {formatDate(update.published_at) ? <time dateTime={update.published_at} className="eyebrow shrink-0">{formatDate(update.published_at)}</time> : null}
                                        </div>
                                        <p className="mt-3 max-w-2xl whitespace-pre-wrap text-[15px] leading-relaxed text-ink/80">{update.body}</p>
                                        {update.impact ? <p className="mt-4 max-w-2xl border-l-2 border-gold pl-4 text-[15px] text-ink/80"><span className="eyebrow mr-2 text-gold-text">Impact</span>{update.impact}</p> : null}
                                    </article>
                                ))}
                            </div>
                        </section>
                    ) : null}

                    {program.roster_links?.team_page ? (
                        <section aria-labelledby="club-roster">
                            <SectionHeading id="club-roster" title="Covered roster" meta="Provider data" />
                            <Link to={program.roster_links.team_page} className="group flex items-center justify-between gap-6 border-b border-border px-1 py-6 transition-colors hover:bg-chalk-2">
                                <span>
                                    <span className="display block text-[26px] leading-tight">View team + academy roster</span>
                                    <span className="mt-1 block text-sm text-muted-foreground">This club maps to a team we already follow through our football-data provider.</span>
                                </span>
                                <ArrowUpRight className="h-5 w-5 shrink-0 transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
                            </Link>
                        </section>
                    ) : null}
                </div>

                <aside className="space-y-12">
                    <section aria-labelledby="club-support" className="space-y-4">
                        <h2 id="club-support" className="eyebrow">Support the club</h2>
                        {program.external_support ? (
                            <>
                                <p className="text-[15px] leading-relaxed text-ink/80">Support happens directly on the club&apos;s approved external page.</p>
                                <Button asChild variant="outline" size="lg">
                                    <a href={program.external_support.url} target="_blank" rel="noopener noreferrer">Support on {program.external_support.label}<ArrowUpRight className="h-4 w-4" /></a>
                                </Button>
                            </>
                        ) : (
                            <div className="rounded-[10px] bg-ink p-6 text-chalk">
                                <p className="display text-[26px] leading-tight">Support isn’t open yet</p>
                                <p className="mt-3 text-sm leading-relaxed text-muted-dark">Right now this page confirms who the club is. There’s no checkout and no money changes hands here.</p>
                            </div>
                        )}
                    </section>

                    <section aria-labelledby="club-badge" className="space-y-4">
                        <h2 id="club-badge" className="eyebrow">What the badge means</h2>
                        <div className="border-t border-border text-[15px] leading-relaxed text-ink/80">
                            <p className="flex gap-3 border-b border-border py-4"><ShieldCheck className="mt-1 h-4 w-4 shrink-0 text-good" /><span>MJ approved the organization and an active adult manager grant exists.</span></p>
                            <p className="flex gap-3 border-b border-border py-4"><Landmark className="mt-1 h-4 w-4 shrink-0 text-good" /><span>US programs also require test-mode Connect readiness; non-US programs remain informational.</span></p>
                        </div>
                        <p className="text-xs text-muted-foreground">It is not a charity, safeguarding, tax, or every-statement accreditation.</p>
                    </section>

                    <section aria-labelledby="club-provenance" className="space-y-3">
                        <h2 id="club-provenance" className="eyebrow">Where this comes from</h2>
                        <p className="display text-[26px] leading-tight">{provenanceLabel}</p>
                        <p className="text-[15px] leading-relaxed text-muted-foreground">{PROVENANCE_COPY[provenanceLabel] || PROVENANCE_COPY['Self-reported']}</p>
                    </section>
                </aside>
            </div>
        </div>
    )
}
