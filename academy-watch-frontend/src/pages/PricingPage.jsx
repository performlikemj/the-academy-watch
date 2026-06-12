import { useNavigate, Link } from 'react-router-dom'
import { useAuth, useAuthUI } from '@/context/AuthContext'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Check, Star, Clapperboard, Telescope } from 'lucide-react'

const TIERS = [
  {
    key: 'stand',
    name: 'The Stand',
    icon: Telescope,
    priceLine: 'Free forever',
    priceNote: null,
    chip: null,
    description: 'Follow the next generation the way supporters always have — out loud, in numbers.',
    features: [
      'Scout Desk discovery & leaderboards',
      'Player journeys & academy stats',
      '4-player comparison',
      'Weekly newsletters',
    ],
  },
  {
    key: 'pro',
    name: 'Scout Pro',
    icon: Star,
    priceLine: 'Free during beta',
    priceNote: 'pricing announced at launch',
    chip: 'FREE DURING BETA',
    description: 'The working scout’s desk: a watchlist that follows your players so you don’t have to.',
    features: [
      'Everything in The Stand',
      'Personal watchlist with notes',
      'Weekly scout digest by email',
      'CSV export of any view',
      'Early access to new tools',
    ],
  },
  {
    key: 'film',
    name: 'Film Room',
    icon: Clapperboard,
    priceLine: 'Pay per match',
    priceNote: null,
    chip: 'IN DEVELOPMENT',
    description: 'Physical data from your own footage, for the leagues nobody else covers.',
    features: [
      'Upload your own match footage',
      'Per-player physical reports (minutes visible, distance, speed bands, sprints, heatmaps)',
      'Own-team reports, consent-clean',
      'Built for leagues with no data coverage',
    ],
  },
]

function FeatureList({ features }) {
  return (
    <ul className="space-y-3">
      {features.map((feature) => (
        <li key={feature} className="flex items-start gap-2.5 text-sm text-foreground/85">
          <Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
          <span>{feature}</span>
        </li>
      ))}
    </ul>
  )
}

export function PricingPage() {
  const auth = useAuth()
  const { openLoginModal } = useAuthUI()
  const navigate = useNavigate()

  const renderCta = (tierKey) => {
    if (tierKey === 'stand') {
      return (
        <Button variant="outline" className="w-full" asChild>
          <Link to="/scout" className="no-underline hover:no-underline">Start scouting</Link>
        </Button>
      )
    }
    if (tierKey === 'pro') {
      return auth?.token ? (
        <Button className="w-full shadow-sm" onClick={() => navigate('/scout/watchlist')}>
          Open your watchlist
        </Button>
      ) : (
        <Button className="w-full shadow-sm" onClick={openLoginModal}>
          Sign in — it&apos;s free
        </Button>
      )
    }
    return (
      <Button variant="outline" className="w-full opacity-60" disabled aria-disabled="true">
        Coming soon
      </Button>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-secondary to-background">
      <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6 lg:px-8 lg:py-16">
        {/* Editorial header */}
        <header className="mx-auto mb-12 max-w-2xl text-center lg:mb-16">
          <p className="mb-3 text-xs font-semibold uppercase tracking-[0.2em] text-primary">Plans</p>
          <h1 className="text-3xl font-bold tracking-tight text-foreground sm:text-5xl">
            Scouting that pays for itself
          </h1>
          <p className="mt-4 text-base text-muted-foreground sm:text-lg">
            Free discovery for everyone. Pro workflow for working scouts.
            Film Room for clubs that need data nobody else has.
          </p>
        </header>

        {/* Tier cards */}
        <div className="relative">
          {/* Soft radial glow behind the elevated middle card */}
          <div
            aria-hidden="true"
            className="pointer-events-none absolute left-1/2 top-1/2 hidden h-[120%] w-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-primary/5 via-primary/[0.02] to-transparent md:block"
          />
          <div className="relative grid grid-cols-1 gap-6 md:grid-cols-3 md:items-stretch">
            {TIERS.map((tier) => {
              const elevated = tier.key === 'pro'
              const Icon = tier.icon
              return (
                <Card
                  key={tier.key}
                  className={`flex flex-col overflow-hidden transition-shadow ${
                    elevated
                      ? 'border-primary shadow-lg md:-translate-y-1 md:hover:shadow-xl'
                      : 'border-border/80 hover:shadow-md'
                  }`}
                >
                  <CardContent className="flex flex-1 flex-col p-6 sm:p-8">
                    <div className="mb-6">
                      <div className="mb-4 flex items-center justify-between gap-2">
                        <span className={`inline-flex h-10 w-10 items-center justify-center rounded-full ${elevated ? 'bg-primary text-primary-foreground' : 'bg-primary/10 text-primary'}`}>
                          <Icon className="h-5 w-5" aria-hidden="true" />
                        </span>
                        {tier.chip && (
                          <span
                            className={`rounded-full px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.12em] ${
                              elevated
                                ? 'bg-primary text-primary-foreground shadow-sm'
                                : 'border border-border bg-secondary text-muted-foreground'
                            }`}
                          >
                            {tier.chip}
                          </span>
                        )}
                      </div>
                      <h2 className="text-xl font-bold tracking-tight text-foreground">{tier.name}</h2>
                      <p className="mt-1.5 text-sm text-muted-foreground">{tier.description}</p>
                    </div>

                    <div className="mb-6 border-y border-border/60 py-4">
                      <p className="text-2xl font-bold tracking-tight text-foreground tabular-nums">{tier.priceLine}</p>
                      {tier.priceNote && (
                        <p className="mt-0.5 text-xs text-muted-foreground">{tier.priceNote}</p>
                      )}
                    </div>

                    <div className="flex-1">
                      <FeatureList features={tier.features} />
                    </div>

                    <div className="mt-8">
                      {renderCta(tier.key)}
                    </div>
                  </CardContent>
                </Card>
              )
            })}
          </div>
        </div>

        {/* FAQ strip */}
        <section aria-label="Questions" className="mx-auto mt-16 max-w-4xl border-t border-border/60 pt-10">
          <div className="grid grid-cols-1 gap-8 md:grid-cols-2">
            <div>
              <h3 className="text-sm font-semibold text-foreground">Why is Pro free right now?</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                We&apos;re in beta and building Scout Pro with the people who use it.
                Everything in the Pro tier is free while we refine it — when pricing
                launches, beta users will hear about it first, with plenty of notice.
              </p>
            </div>
            <div>
              <h3 className="text-sm font-semibold text-foreground">What is Film Room?</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                Film Room turns your own match footage into physical reports using
                computer vision — minutes visible, distances, speed bands, sprints and
                heatmaps for every player on your team. It&apos;s in active development
                and will be priced per processed match, so you only pay for what you use.
              </p>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}
