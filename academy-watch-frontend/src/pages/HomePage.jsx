import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button.jsx'
import {
  Trophy,
  Search,
  Star,
  Globe,
  Mail,
  TrendingUp,
  Settings,
  ArrowRight,
  Users,
  Newspaper,
  ChevronRight
} from 'lucide-react'
import { APIService } from '@/lib/api'
import { useAuth } from '@/context/AuthContext'
import { useGlobalSearchContext } from '@/context/GlobalSearchContext'
import { SponsorSidebar, SponsorStrip } from '@/components/SponsorSidebar'

export function HomePage() {
  const auth = useAuth()
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const adminUnlocked = !!auth?.token && auth?.isAdmin && auth?.hasApiKey
  const { open: openSearch } = useGlobalSearchContext()

  useEffect(() => {
    const loadStats = async () => {
      try {
        const data = await APIService.getStats()
        setStats(data)
      } catch (error) {
        console.error('Failed to load stats:', error)
      } finally {
        setLoading(false)
      }
    }

    loadStats()
  }, [])

  return (
    <div className="max-w-[1400px] mx-auto py-6 sm:px-6 lg:px-8">
      <div className="flex flex-col lg:flex-row gap-6">
        <div className="flex-1 min-w-0 px-4 py-6 sm:px-0">

          {/* Hero Section */}
          <div className="text-center mb-16">
            <h1 className="text-4xl sm:text-5xl md:text-6xl font-bold text-foreground tracking-tight mb-4 leading-tight">
              Track Every Academy{' '}
              <span className="text-primary">Prospect's Journey</span>
            </h1>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto mb-8">
              Weekly AI-generated newsletters, career journey maps, and stats for academy players on loan from Europe's top clubs.
            </p>

            <div className="flex flex-col items-center gap-4 max-w-xl mx-auto mb-6">
              <button
                type="button"
                onClick={openSearch}
                className="w-full relative flex items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3.5 text-left shadow-sm hover:border-primary/30 transition-all cursor-text"
              >
                <div className="flex items-center gap-3 text-muted-foreground/70">
                  <Search className="h-5 w-5" />
                  <span className="text-base">Search for your club...</span>
                </div>
                <kbd className="hidden sm:inline-flex items-center gap-1 rounded border border-border bg-secondary px-2 py-1 font-mono text-xs text-muted-foreground">
                  <span>⌘</span>K
                </kbd>
              </button>

              <div className="flex flex-wrap justify-center gap-3">
                <Link to="/dream-team">
                  <Button size="lg" variant="outline">
                    <Trophy className="h-5 w-5 mr-2" />
                    Build Your Dream XI
                  </Button>
                </Link>
                <Link to="/academy">
                  <Button size="lg" variant="outline">
                    <Star className="h-5 w-5 mr-2" />
                    Academy Tracker
                  </Button>
                </Link>
                {adminUnlocked && (
                  <Link to="/admin">
                    <Button size="lg">
                      <Settings className="h-5 w-5 mr-2" />
                      Admin
                    </Button>
                  </Link>
                )}
              </div>
            </div>
          </div>

          {/* Stats Bar */}
          {loading ? (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-16">
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="bg-card rounded-xl border border-border p-5 text-center">
                  <div className="h-8 w-16 bg-secondary rounded animate-pulse mx-auto mb-2" />
                  <div className="h-4 w-24 bg-secondary rounded animate-pulse mx-auto mb-1" />
                  <div className="h-3 w-28 bg-secondary rounded animate-pulse mx-auto" />
                </div>
              ))}
            </div>
          ) : stats ? (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-16">
              <div className="bg-card rounded-xl border border-border p-5 text-center">
                <p className="text-3xl font-bold text-foreground">{stats.teams_with_loans}</p>
                <p className="text-sm text-muted-foreground mt-1">Academies Tracked</p>
                <p className="text-xs text-muted-foreground/60">Across Europe's top leagues</p>
              </div>
              <div className="bg-card rounded-xl border border-border p-5 text-center">
                <p className="text-3xl font-bold text-foreground">{stats.total_active_loans}</p>
                <p className="text-sm text-muted-foreground mt-1">Players Monitored</p>
                <p className="text-xs text-muted-foreground/60">Academy prospects on loan</p>
              </div>
              <div className="bg-card rounded-xl border border-border p-5 text-center">
                <p className="text-3xl font-bold text-foreground">{stats.total_newsletters}</p>
                <p className="text-sm text-muted-foreground mt-1">Newsletters Sent</p>
                <p className="text-xs text-muted-foreground/60">AI-generated match reports</p>
              </div>
              <div className="bg-card rounded-xl border border-border p-5 text-center">
                <p className="text-3xl font-bold text-foreground">{stats.total_subscriptions}</p>
                <p className="text-sm text-muted-foreground mt-1">Active Subscribers</p>
                <p className="text-xs text-muted-foreground/60">Following their clubs</p>
              </div>
            </div>
          ) : null}

          {/* How It Works */}
          <div className="mb-20">
            <div className="text-center mb-10">
              <p className="text-sm text-primary font-medium tracking-wide uppercase mb-2">How It Works</p>
              <h2 className="text-3xl font-bold text-foreground">Three steps to never miss a prospect</h2>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="bg-card rounded-xl border border-border p-6 text-center">
                <div className="w-12 h-12 bg-primary/10 rounded-lg flex items-center justify-center mx-auto mb-4">
                  <Search className="h-6 w-6 text-primary" />
                </div>
                <div className="text-xs font-medium text-primary uppercase tracking-wide mb-2">Step 1</div>
                <h3 className="text-lg font-semibold text-foreground mb-2">Pick Your Club</h3>
                <p className="text-sm text-muted-foreground">
                  Search for any academy from our tracked leagues — Premier League, La Liga, Bundesliga, Serie A, and more.
                </p>
              </div>
              <div className="bg-card rounded-xl border border-border p-6 text-center">
                <div className="w-12 h-12 bg-primary/10 rounded-lg flex items-center justify-center mx-auto mb-4">
                  <Mail className="h-6 w-6 text-primary" />
                </div>
                <div className="text-xs font-medium text-primary uppercase tracking-wide mb-2">Step 2</div>
                <h3 className="text-lg font-semibold text-foreground mb-2">Get Weekly Newsletters</h3>
                <p className="text-sm text-muted-foreground">
                  Receive AI-generated reports covering your academy's loan players — goals, assists, minutes played, and career updates.
                </p>
              </div>
              <div className="bg-card rounded-xl border border-border p-6 text-center">
                <div className="w-12 h-12 bg-primary/10 rounded-lg flex items-center justify-center mx-auto mb-4">
                  <TrendingUp className="h-6 w-6 text-primary" />
                </div>
                <div className="text-xs font-medium text-primary uppercase tracking-wide mb-2">Step 3</div>
                <h3 className="text-lg font-semibold text-foreground mb-2">Follow Their Journey</h3>
                <p className="text-sm text-muted-foreground">
                  Track each player's career path with journey maps, cohort comparisons, and season-by-season stats.
                </p>
              </div>
            </div>
          </div>

          {/* Feature Cards */}
          <div className="mb-20">
            <div className="text-center mb-10">
              <p className="text-sm text-primary font-medium tracking-wide uppercase mb-2">Features</p>
              <h2 className="text-3xl font-bold text-foreground">Everything you need to follow the next generation</h2>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Newsletters - spans full width */}
              <Link to="/newsletters" className="md:col-span-2 group bg-card rounded-xl border border-border p-8 hover:border-primary/30 transition-all">
                <div className="flex items-start gap-4">
                  <div className="w-12 h-12 bg-primary/10 rounded-lg flex items-center justify-center shrink-0">
                    <Newspaper className="h-6 w-6 text-primary" />
                  </div>
                  <div className="flex-1">
                    <h3 className="text-xl font-semibold text-foreground group-hover:text-primary transition-colors mb-2">
                      AI-Generated Newsletters
                    </h3>
                    <p className="text-muted-foreground">
                      Weekly reports with goals, assists, minutes, and AI commentary for every academy player on loan. Delivered straight to your inbox.
                    </p>
                  </div>
                  <ArrowRight className="h-5 w-5 text-muted-foreground/40 group-hover:text-primary transition-colors mt-1 shrink-0" />
                </div>
              </Link>
              {/* Career Journey Maps */}
              <Link to="/teams" className="group bg-card rounded-xl border border-border p-6 hover:border-primary/30 transition-all">
                <div className="w-10 h-10 bg-primary/10 rounded-lg flex items-center justify-center mb-4">
                  <Globe className="h-5 w-5 text-primary" />
                </div>
                <h3 className="font-semibold text-foreground group-hover:text-primary transition-colors mb-2">Career Journey Maps</h3>
                <p className="text-sm text-muted-foreground">Visualise each player's path from academy to loan spells with interactive journey maps.</p>
              </Link>
              {/* Academy Cohort Tracker */}
              <Link to="/academy" className="group bg-card rounded-xl border border-border p-6 hover:border-primary/30 transition-all">
                <div className="w-10 h-10 bg-primary/10 rounded-lg flex items-center justify-center mb-4">
                  <Users className="h-5 w-5 text-primary" />
                </div>
                <h3 className="font-semibold text-foreground group-hover:text-primary transition-colors mb-2">Academy Cohort Tracker</h3>
                <p className="text-sm text-muted-foreground">Browse academy cohorts by year, compare development paths, and see which players are breaking through.</p>
              </Link>
              {/* Dream XI Builder */}
              <Link to="/dream-team" className="group bg-card rounded-xl border border-border p-6 hover:border-primary/30 transition-all">
                <div className="w-10 h-10 bg-primary/10 rounded-lg flex items-center justify-center mb-4">
                  <Trophy className="h-5 w-5 text-primary" />
                </div>
                <h3 className="font-semibold text-foreground group-hover:text-primary transition-colors mb-2">Dream XI Builder</h3>
                <p className="text-sm text-muted-foreground">Build your best XI from academy prospects across all tracked clubs.</p>
              </Link>
              {/* Journalist Profiles */}
              <Link to="/journalists" className="group bg-card rounded-xl border border-border p-6 hover:border-primary/30 transition-all">
                <div className="w-10 h-10 bg-primary/10 rounded-lg flex items-center justify-center mb-4">
                  <Star className="h-5 w-5 text-primary" />
                </div>
                <h3 className="font-semibold text-foreground group-hover:text-primary transition-colors mb-2">Writer Profiles</h3>
                <p className="text-sm text-muted-foreground">Follow dedicated writers who cover your club's academy and contribute expert commentary.</p>
              </Link>
            </div>
          </div>

          {/* Newsletter Preview */}
          <div className="mb-20">
            <div className="text-center mb-10">
              <p className="text-sm text-primary font-medium tracking-wide uppercase mb-2">What You'll Get</p>
              <h2 className="text-3xl font-bold text-foreground">A taste of the weekly report</h2>
            </div>
            <div className="bg-card rounded-xl border border-border overflow-hidden max-w-2xl mx-auto">
              <div className="bg-secondary/50 px-6 py-3 border-b border-border flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Mail className="h-4 w-4 text-muted-foreground" />
                  <span className="text-sm font-medium text-foreground">Arsenal Academy Watch</span>
                </div>
                <span className="text-xs text-muted-foreground">Weekly Report</span>
              </div>
              <div className="p-6 space-y-4">
                <div className="bg-secondary/30 rounded-lg p-4">
                  <p className="text-2xl font-bold text-foreground mb-1">3 Goals, 2 Assists</p>
                  <p className="text-xs text-muted-foreground uppercase tracking-wide">Across 12 loanees this week</p>
                </div>
                <div className="space-y-3">
                  <div className="flex items-start gap-3">
                    <ChevronRight className="h-4 w-4 text-primary mt-0.5 shrink-0" />
                    <p className="text-sm text-muted-foreground">
                      <span className="text-foreground font-medium">E. Nwaneri</span> — Brace for the U21s in a 3-1 win. 89% pass accuracy, 4 key passes.
                    </p>
                  </div>
                  <div className="flex items-start gap-3">
                    <ChevronRight className="h-4 w-4 text-primary mt-0.5 shrink-0" />
                    <p className="text-sm text-muted-foreground">
                      <span className="text-foreground font-medium">M. Lewis-Skelly</span> — Full 90 minutes in the Championship. 3 tackles won, clean sheet.
                    </p>
                  </div>
                  <div className="flex items-start gap-3">
                    <ChevronRight className="h-4 w-4 text-primary mt-0.5 shrink-0" />
                    <p className="text-sm text-muted-foreground">
                      <span className="text-foreground font-medium">C. Patino</span> — Assist and 89 minutes in a 2-0 victory.
                    </p>
                  </div>
                </div>
                <div className="pt-2 border-t border-border">
                  <Link to="/newsletters" className="text-sm text-primary hover:underline inline-flex items-center gap-1">
                    Browse real newsletters <ArrowRight className="h-3.5 w-3.5" />
                  </Link>
                </div>
              </div>
            </div>
          </div>

          {/* Subscribe CTA */}
          <div className="mb-12">
            <div className="bg-card rounded-xl border border-border p-8 md:p-12 text-center">
              <h2 className="text-3xl font-bold text-foreground mb-3">
                Never Miss an Academy Update
              </h2>
              <p className="text-lg text-muted-foreground mb-8 max-w-lg mx-auto">
                Pick your club and get weekly AI newsletters — free.
              </p>
              <Link to="/teams">
                <Button size="lg" className="text-base px-8">
                  <Mail className="h-5 w-5 mr-2" />
                  Find Your Club & Subscribe
                </Button>
              </Link>
            </div>
          </div>

        </div>

        {/* Sponsor Sidebar - visible on larger screens */}
        <SponsorSidebar className="hidden lg:block" />
      </div>

      {/* Mobile Sponsor Strip - visible on smaller screens */}
      <div className="lg:hidden px-4 pb-6">
        <SponsorStrip />
      </div>
    </div>
  )
}
