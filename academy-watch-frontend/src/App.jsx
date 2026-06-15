import { useState, useEffect, useMemo, useCallback, useRef, Fragment } from 'react'
import { BrowserRouter as Router, Routes, Route, Link, Navigate, useLocation, useParams, useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button.jsx'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card.jsx'
import { Badge } from '@/components/ui/badge.jsx'
import { Input } from '@/components/ui/input.jsx'
import { Label } from '@/components/ui/label.jsx'
import { Textarea } from '@/components/ui/textarea.jsx'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select.jsx'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs.jsx'
import TeamMultiSelect from '@/components/ui/TeamMultiSelect.jsx'
import TeamSelect from '@/components/ui/TeamSelect.jsx'
import { JournalistList } from '@/components/JournalistList.jsx'
import { BuyMeCoffeeButton } from '@/components/BuyMeCoffeeButton.jsx'
import SyncBanner from '@/components/SyncBanner.jsx'
import { CommentaryManager } from '@/components/CommentaryManager.jsx'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion.jsx'
import { Alert, AlertDescription } from '@/components/ui/alert.jsx'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog.jsx'
import { Drawer, DrawerTrigger, DrawerContent, DrawerHeader, DrawerFooter, DrawerTitle, DrawerDescription, DrawerClose } from '@/components/ui/drawer.jsx'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover.jsx'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar.jsx'
import { useIsMobile } from '@/hooks/use-mobile.js'
import { useGlobalSearch } from '@/hooks/useGlobalSearch.js'
import { GlobalSearchDialog } from '@/components/GlobalSearchDialog.jsx'
import {
  Users,
  Mail,
  Calendar,
  Trophy,
  TrendingUp,
  Globe,
  Star,
  ArrowLeft,
  ArrowRight,
  CheckCircle,
  AlertCircle,
  Home,
  UserPlus,
  FileText,
  Settings,
  BarChart3,
  Loader2,
  ShieldCheck,
  ShieldAlert,
  KeyRound,
  LogIn,
  LogOut,
  MessageCircle,
  UserCog,
  X,
  Copy,
  ChevronDown,
  ChevronRight,
  Search,
  CreditCard,
  XCircle,
  RotateCcw,
  Clock
} from 'lucide-react'
import { estimateReadingTime, extractNewsletterExcerpt } from '@/lib/formatText'
import { parseNewsletterId } from '@/lib/newsletter-admin.js'
import { AdminLayout } from '@/components/layouts/AdminLayout'
import { SponsorSidebar, SponsorStrip } from '@/components/SponsorSidebar'
import { AdminDashboard } from '@/pages/admin/AdminDashboard'
import { AdminInbox } from '@/pages/admin/AdminInbox'
import { AdminOperations } from '@/pages/admin/AdminOperations'
import { AdminSeeding } from '@/pages/admin/AdminSeeding'
import { AdminNewsletters } from '@/pages/admin/AdminNewsletters'
import { AdminNewsletterDetail } from '@/pages/admin/AdminNewsletterDetail'
import { AdminPlayers } from '@/pages/admin/AdminPlayers'
import { AdminSettings } from '@/pages/admin/AdminSettings'
import { AdminUsers } from '@/pages/admin/AdminUsers'
import { AdminTeams } from '@/pages/admin/AdminTeams'
import { AdminSponsors } from '@/pages/admin/AdminSponsors'
import { AdminAcademy } from '@/pages/admin/AdminAcademy'
import { AdminCohorts } from '@/pages/admin/AdminCohorts'
import { AdminVideo } from '@/pages/admin/AdminVideo'
import { AdminVideoMatch } from '@/pages/admin/AdminVideoMatch'
import { AdminTools } from '@/pages/admin/AdminTools'
import { AdminSandbox } from '@/pages/admin/AdminSandbox'
import { AdminFormation } from '@/pages/admin/AdminFormation'
import { HomePage } from '@/pages/HomePage'
import { PublicFormationBuilder } from '@/pages/PublicFormationBuilder'
import { CohortBrowser } from '@/pages/CohortBrowser'
import { ScoutPage } from '@/pages/ScoutPage'
import { WatchlistPage } from '@/pages/WatchlistPage'
import { PricingPage } from '@/pages/PricingPage'
import { CohortDetail } from '@/pages/CohortDetail'
import { CohortAnalytics } from '@/pages/CohortAnalytics'
import { GolPanel } from '@/components/gol/GolPanel'
import { ClaimAccount } from '@/pages/ClaimAccount'
import { SubmitTake } from '@/pages/SubmitTake'
import { FlagData } from '@/pages/FlagData'
import { WriterLogin } from '@/pages/writer/WriterLogin'
import { WriterDashboard } from '@/pages/writer/WriterDashboard'
import { WriteupEditor } from '@/pages/writer/WriteupEditor'
import { ContributorManager } from '@/pages/writer/ContributorManager'
import { CuratorDashboard } from '@/pages/curator/CuratorDashboard'
import { WriteupPage } from '@/pages/WriteupPage'
import { PlayerPage } from '@/pages/PlayerPage'
import { TeamDetailPage } from '@/pages/TeamDetailPage'
import { JournalistProfile } from '@/pages/JournalistProfile'
import { JournalistNewsletterView } from '@/components/JournalistNewsletterView'
import {
  NewsletterWriterOverlay,
  NewsletterWriterProvider,
  WriterHeaderSection,
  InlinePlayerWriteups,
} from '@/components/NewsletterWriterOverlay'
import { NewsletterView } from '@/components/newsletter/NewsletterView'

import { APIService } from '@/lib/api'
import { UniversalDatePicker } from '@/components/ui/UniversalDatePicker'
import { AuthContext, AuthUIContext, useAuth, useAuthUI, buildAuthSnapshot } from '@/context/AuthContext'
import { GlobalSearchContext, useGlobalSearchContext } from '@/context/GlobalSearchContext'
import { AuthModal } from '@/components/auth/AuthModal'
import './App.css'
import { useQueryParam } from '@/hooks/useQueryParam'



const RELATIVE_TIME_DIVISIONS = [
  { amount: 60, unit: 'second' },
  { amount: 60, unit: 'minute' },
  { amount: 24, unit: 'hour' },
  { amount: 7, unit: 'day' },
  { amount: 4.34524, unit: 'week' },
  { amount: 12, unit: 'month' },
  { amount: Infinity, unit: 'year' },
]

const relativeTimeFormatter = typeof Intl !== 'undefined' && typeof Intl.RelativeTimeFormat === 'function'
  ? new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })
  : null

function formatRelativeTime(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  if (!relativeTimeFormatter) {
    return date.toLocaleString()
  }
  let duration = (date.getTime() - Date.now()) / 1000
  for (const division of RELATIVE_TIME_DIVISIONS) {
    if (Math.abs(duration) < division.amount || division.amount === Infinity) {
      return relativeTimeFormatter.format(Math.round(duration), division.unit)
    }
    duration /= division.amount
  }
  return date.toLocaleString()
}

// League colors for visual identity
const LEAGUE_COLORS = {
  'Premier League': '#37003c',
  'La Liga': '#ff6b35',
  'Serie A': '#0066cc',
  'Bundesliga': '#d20515',
  'Ligue 1': '#dae025',
  'Champions League': '#081c3b'
}

const NEWSLETTER_PAGE_SIZE = 5

const filterLatestSeasonTeams = (rows = []) => {
  if (!Array.isArray(rows) || rows.length === 0) {
    return { season: null, teams: [] }
  }

  const seasons = rows
    .map((team) => parseInt(team?.season, 10))
    .filter((value) => !Number.isNaN(value))

  const latestSeason = seasons.length ? Math.max(...seasons) : null
  const seasonFiltered = latestSeason !== null
    ? rows.filter((team) => parseInt(team?.season, 10) === latestSeason)
    : rows

  const deduped = new Map()
  for (const team of seasonFiltered) {
    if (!team) continue
    const key = team.team_id != null ? String(team.team_id) : team.id != null ? `db:${team.id}` : null
    if (!key) continue
    const existing = deduped.get(key)
    if (!existing) {
      deduped.set(key, team)
      continue
    }
    const existingUpdated = existing.updated_at ? Date.parse(existing.updated_at) : 0
    const candidateUpdated = team.updated_at ? Date.parse(team.updated_at) : 0
    if (candidateUpdated >= existingUpdated) {
      deduped.set(key, team)
    }
  }

  const teams = Array.from(deduped.values()).sort((a, b) => {
    return (a?.name || '').localeCompare(b?.name || '')
  })

  return { season: latestSeason, teams }
}

// Historical Newsletters page component
function HistoricalNewslettersPage() {
  const [teams, setTeams] = useState([])
  const [currentSeason, setCurrentSeason] = useState(null)
  const [selectedTeams, setSelectedTeams] = useState([])
  const [selectedDate, setSelectedDate] = useState('')
  const [newsletters, setNewsletters] = useState([])
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [message, setMessage] = useState(null)

  // Auth state — needed for the admin-gated empty state below. Without this
  // the JSX referenced these as free variables and exploded at runtime.
  const auth = useAuth()
  const { openLoginModal, logout: triggerLogout } = useAuthUI()
  const hasStoredKey = Boolean(auth?.hasApiKey)
  const hasAdminToken = Boolean(auth?.isAdmin)
  const authToken = Boolean(auth?.token)

  useEffect(() => {
    const loadTeams = async () => {
      try {
        const data = await APIService.getTeams({ european_only: 'true' })
        const { season, teams: filtered } = filterLatestSeasonTeams(data)
        setTeams(filtered)
        setCurrentSeason(season)
      } catch {
        setMessage({ type: 'error', text: 'Failed to load teams' })
      } finally {
        setLoading(false)
      }
    }

    loadTeams()
  }, [])

  const handleTeamToggle = (teamId) => {
    setSelectedTeams(prev =>
      prev.includes(teamId)
        ? prev.filter(id => id !== teamId)
        : [...prev, teamId]
    )
  }

  const generateNewsletters = async () => {
    if (!selectedDate || selectedTeams.length === 0) {
      setMessage({ type: 'error', text: 'Please select a date and at least one team' })
      return
    }

    setGenerating(true)
    setNewsletters([])

    try {
      const generatedNewsletters = []

      // Generate newsletter for each selected team
      for (const teamId of selectedTeams) {

        try {
          const newsletter = await APIService.generateNewsletter({
            team_id: teamId,
            target_date: selectedDate,
            type: 'weekly'
          })

          generatedNewsletters.push({
            ...newsletter.newsletter,
            teamName: teams.find(t => t.id === teamId)?.name || 'Unknown Team'
          })
        } catch (error) {
          console.error(`❌ Failed to generate newsletter for team ${teamId}:`, error)
        }
      }

      setNewsletters(generatedNewsletters)
      setMessage({
        type: 'success',
        text: `Generated ${generatedNewsletters.length} newsletters for ${selectedDate}`
      })

    } catch (error) {
      console.error('❌ Failed to generate newsletters:', error)
      setMessage({ type: 'error', text: 'Failed to generate newsletters' })
    } finally {
      setGenerating(false)
    }
  }

  // Group teams by league
  const teamsByLeague = teams.reduce((acc, team) => {
    const league = team.league_name || 'Other'
    if (!acc[league]) acc[league] = []
    acc[league].push(team)
    return acc
  }, {})



  return (
    <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
      <div className="px-4 py-6 sm:px-0">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-foreground mb-4">
            Historical Newsletters
          </h1>
          <p className="text-lg text-muted-foreground">
            Generate newsletters for any date. Select teams and a date to see academy player activities for that week.
          </p>
          {currentSeason !== null && (
            <p className="text-sm text-muted-foreground">Latest season detected: {currentSeason}–{String(currentSeason + 1).slice(-2)}</p>
          )}
        </div>

        {message && (
          <div className={`mb-6 p-4 rounded-md ${message.type === 'error'
            ? 'bg-rose-50 border border-rose-200 text-rose-700'
            : 'bg-emerald-50 border border-emerald-200 text-emerald-700'
            }`}>
            {message.text}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Selection Panel */}
          <div className="space-y-6">
            {/* Date Selection */}
            <Card>
              <CardHeader>
                <CardTitle>Select Date</CardTitle>
                <CardDescription>
                  Choose any date to generate newsletters for that week
                </CardDescription>
              </CardHeader>
              <CardContent>
                <input
                  type="date"
                  value={selectedDate}
                  onChange={(e) => setSelectedDate(e.target.value)}
                  className="w-full px-3 py-2 border border-border rounded-md focus:outline-none focus:ring-2 focus:ring-ring"
                />
                <p className="text-sm text-muted-foreground mt-2">
                  Select any date to generate newsletters for that week
                </p>
              </CardContent>
            </Card>

            {/* Team Selection */}
            <Card>
              <CardHeader>
                <CardTitle>Select Teams</CardTitle>
                <CardDescription>Use the searchable selector. ({selectedTeams.length} selected)</CardDescription>
              </CardHeader>
              <CardContent>
                {loading ? (
                  <div className="text-center py-8">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto"></div>
                  </div>
                ) : (
                  <div className="space-y-4">
                    <TeamMultiSelect teams={teams} value={selectedTeams} onChange={setSelectedTeams} placeholder="Search and select teams…" />
                    <Accordion type="multiple" className="rounded-md border">
                      {Object.entries(teamsByLeague).map(([league, leagueTeams]) => (
                        <AccordionItem key={league} value={league} className="border-b last:border-b-0">
                          <AccordionTrigger className="px-4">
                            <div className="flex items-center">
                              <div className="w-3 h-3 rounded mr-2" style={{ backgroundColor: LEAGUE_COLORS[league] || '#666' }} />
                              <span className="text-sm font-semibold">{league}</span>
                              <Badge variant="secondary" className="ml-2">{leagueTeams.length}</Badge>
                            </div>
                          </AccordionTrigger>
                          <AccordionContent>
                            <div className="grid grid-cols-1 gap-2 px-4 pb-2">
                              {leagueTeams.map((team) => (
                                <label key={team.id} className="flex items-center space-x-2 cursor-pointer hover:bg-secondary p-2 rounded">
                                  <input type="checkbox" checked={selectedTeams.includes(team.id)} onChange={() => handleTeamToggle(team.id)} className="rounded border-border text-primary focus:ring-ring" />
                                  <span className="text-sm">{team.name}</span>
                                </label>
                              ))}
                            </div>
                          </AccordionContent>
                        </AccordionItem>
                      ))}
                    </Accordion>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Generate Button */}
            <Button
              onClick={generateNewsletters}
              disabled={generating || !selectedDate || selectedTeams.length === 0}
              size="lg"
              className="w-full bg-primary hover:bg-primary/90"
            >
              {generating ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                  Generating...
                </>
              ) : (
                <>
                  <Mail className="h-5 w-5 mr-2" />
                  Generate {selectedTeams.length} Newsletter{selectedTeams.length !== 1 ? 's' : ''}
                </>
              )}
            </Button>
          </div>

          {/* Generated Newsletters */}
          <div>
            <Card>
              <CardHeader>
                <CardTitle>Generated Newsletters</CardTitle>
                <CardDescription>
                  {newsletters.length > 0
                    ? `${newsletters.length} newsletters for ${selectedDate}`
                    : 'Select teams and date to generate newsletters'
                  }
                </CardDescription>
              </CardHeader>
              <CardContent>
                {newsletters.length > 0 ? (
                  <div className="space-y-4 max-h-96 overflow-y-auto">
                    {newsletters.map((newsletter, index) => (
                      <div key={index} className="border rounded-lg p-4">
                        <h3 className="font-semibold text-lg mb-2">
                          {newsletter.teamName}
                        </h3>
                        <h4 className="font-medium text-foreground mb-2">
                          {newsletter.title}
                        </h4>
                        <div className="text-sm text-muted-foreground whitespace-pre-wrap">
                          {typeof newsletter.content === 'string'
                            ? JSON.parse(newsletter.content).summary || newsletter.content
                            : newsletter.content?.summary || 'No content available'
                          }
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-12 text-muted-foreground">
                    <Mail className="h-12 w-12 mx-auto mb-4 opacity-50" />
                    <p>No newsletters generated yet</p>
                    <p className="text-sm">Select teams and a date above</p>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
        ) : (
        <div className="rounded-lg border border-dashed bg-muted/40 p-6 text-sm text-muted-foreground space-y-3">
          {authToken && !hasAdminToken ? (
            <>
              <p>This account is signed in but is not authorized for admin tools.</p>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="outline" onClick={() => triggerLogout({ clearAdminKey: true })}>
                  Log out
                </Button>
              </div>
            </>
          ) : (
            <>
              <p>Admin tools are locked. Sign in with an approved admin email and store the API key above.</p>
              <div className="flex flex-wrap gap-2">
                {!hasAdminToken && (
                  <Button size="sm" onClick={openLoginModal}>
                    <LogIn className="mr-1 h-4 w-4" /> Sign in as admin
                  </Button>
                )}
                {hasAdminToken && !hasStoredKey && (
                  <Button size="sm" variant="outline" asChild>
                    <Link to="/admin">
                      <KeyRound className="mr-1 h-4 w-4" /> Add API key
                    </Link>
                  </Button>
                )}
              </div>
            </>
          )}
        </div>
        )

      </div>
    </div>
  )
}

function RequireAuth({ children }) {
  const { token } = useAuth()
  if (!token) {
    return <Navigate to="/" replace />
  }
  return children
}

// Navigation component
const BRAND_LOGO_SRC = '/assets/loan_army_assets/apple-touch-icon.png'

function SoccerBallToggleIcon({ spinning }) {
  return (
    <svg
      viewBox="0 0 64 64"
      className="h-10 w-10 text-foreground"
      style={{ transform: spinning ? 'rotate(360deg)' : 'rotate(0deg)', transition: 'transform 0.6s ease' }}
      aria-hidden="true"
    >
      <circle cx="32" cy="32" r="28" fill="#f5f5f5" stroke="currentColor" strokeWidth="4" />
      <polygon points="32,22 38,26 36,34 28,34 26,26" fill="currentColor" />
      <path d="M32 16L23 22L16 30L19 40L28 46H36L45 40L48 30L41 22Z" fill="none" stroke="currentColor" strokeWidth="3" strokeLinejoin="round" />
      <path d="M23 22L18 14" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
      <path d="M41 22L46 14" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
      <path d="M19 40L11 43" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
      <path d="M45 40L53 43" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
      <path d="M28 46L25 56" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
      <path d="M36 46L39 56" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  )
}

function Navigation() {
  const location = useLocation()
  const isMobile = useIsMobile()
  const { token, isAdmin, hasApiKey, isJournalist, isCurator } = useAuth()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const { open: openSearch } = useGlobalSearchContext()

  const adminUnlocked = !!token && isAdmin && hasApiKey

  const navItems = useMemo(() => {
    const items = [
      { path: '/', label: 'Home', icon: Home },
      { path: '/scout', label: 'Scout', icon: Globe },
      { path: '/teams', label: 'Teams', icon: Users },
      { path: '/dream-team', label: 'Dream XI', icon: Trophy },
      { path: '/newsletters', label: 'Newsletters', icon: FileText },
      { path: '/journalists', label: 'Journalists', icon: UserPlus },
      { path: '/pricing', label: 'Pricing', icon: CreditCard },
    ]
    if (isJournalist) {
      items.push({ path: '/writer/dashboard', label: 'Writer Dashboard', icon: FileText })
    }
    if (isCurator) {
      items.push({ path: '/curator/dashboard', label: 'Curator', icon: FileText })
    }
    if (token) {
      items.push({ path: '/settings', label: 'Settings', icon: UserCog })
    }
    if (adminUnlocked) {
      items.push({ path: '/admin', label: 'Admin', icon: Settings })
    }
    return items
  }, [adminUnlocked, isJournalist, isCurator, token])

  const linkClasses = (isActive) => (
    `inline-flex items-center gap-2 rounded-full px-3 py-2 text-sm font-medium transition-colors sm:px-3 whitespace-nowrap no-underline hover:no-underline ` +
    (isActive
      ? 'text-primary bg-primary/5 shadow-inner'
      : 'text-foreground/80 hover:text-foreground hover:bg-secondary'
    )
  )

  const renderNavLinks = (variant) => navItems.map((item) => {
    const { path, label, icon } = item
    const Icon = icon
    const isActive = location.pathname === path
    const content = (
      <span className="flex items-center gap-2">
        <Icon className="h-4 w-4" />
        {label}
      </span>
    )
    if (variant === 'mobile') {
      return (
        <DrawerClose asChild key={path}>
          <Link
            to={path}
            className={linkClasses(isActive) + ' justify-start'}
            onClick={() => setDrawerOpen(false)}
          >
            {content}
          </Link>
        </DrawerClose>
      )
    }
    return (
      <Link key={path} to={path} className={linkClasses(isActive)}>
        {content}
      </Link>
    )
  })

  return (
    <nav className="border-b bg-background/90 backdrop-blur supports-[backdrop-filter]:bg-background/70">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8 gap-4">
        <Link to="/" className="flex items-center gap-2 text-foreground no-underline hover:no-underline sm:gap-3 shrink-0">
          <span className="inline-flex h-10 w-10 items-center justify-center rounded bg-slate-900 shadow">
            <img src={BRAND_LOGO_SRC} alt="The Academy Watch logo" className="h-7 w-7" />
          </span>
          <div className="flex flex-col leading-tight">
            <span className="text-lg font-semibold">The Academy Watch</span>
            <span className="hidden text-xs text-muted-foreground sm:block">Academy player tracker</span>
          </div>
        </Link>

        {isMobile ? (
          <Drawer open={drawerOpen} onOpenChange={setDrawerOpen} autoFocus>
            <DrawerTrigger asChild>
              <button
                type="button"
                className="inline-flex items-center justify-center rounded-full border border-border bg-secondary p-2 shadow-sm transition hover:bg-muted"
                aria-label="Toggle navigation menu"
                aria-expanded={drawerOpen}
              >
                <SoccerBallToggleIcon spinning={drawerOpen} />
              </button>
            </DrawerTrigger>
            <DrawerContent className="pb-6">
              <DrawerHeader>
                <DrawerTitle className="text-base font-semibold">The Academy Watch</DrawerTitle>
                <DrawerDescription>Quick access to every page.</DrawerDescription>
              </DrawerHeader>
              <div className="flex flex-col gap-2 px-4">
                <DrawerClose asChild>
                  <button
                    type="button"
                    onClick={() => { setDrawerOpen(false); openSearch(); }}
                    className="inline-flex items-center gap-2 rounded-full px-3 py-2 text-sm font-medium text-foreground/80 hover:text-foreground hover:bg-secondary transition-colors justify-start"
                  >
                    <Search className="h-4 w-4" />
                    Search
                  </button>
                </DrawerClose>
                {renderNavLinks('mobile')}
              </div>
              <DrawerFooter>
                <AuthControls isMobile onNavigate={() => setDrawerOpen(false)} />
              </DrawerFooter>
            </DrawerContent>
          </Drawer>
        ) : (
          <div className="flex min-w-0 flex-1 items-center gap-4 overflow-hidden">
            <div className="flex min-w-0 flex-1 items-center gap-2 sm:gap-3 md:gap-4 overflow-x-auto pr-2">
              {renderNavLinks('desktop')}
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <button
                type="button"
                onClick={openSearch}
                className="inline-flex items-center gap-2 rounded-md border border-border bg-card px-3 py-1.5 text-sm text-muted-foreground shadow-sm hover:bg-secondary hover:text-foreground/80 transition-colors"
                aria-label="Search"
              >
                <Search className="h-4 w-4" />
                <span className="hidden sm:inline">Search</span>
                <kbd className="hidden sm:inline-flex items-center gap-1 rounded border border-border bg-secondary px-1.5 font-mono text-xs text-muted-foreground">
                  <span className="text-xs">⌘</span>K
                </kbd>
              </button>
              <AuthControls />
            </div>
          </div>
        )}
      </div>
    </nav>
  )
}

function AuthControls({ isMobile = false, onNavigate }) {
  const { token, displayName, isAdmin, hasApiKey } = useAuth()
  const { openLoginModal, logout } = useAuthUI()

  const [apiKeyPopoverOpen, setApiKeyPopoverOpen] = useState(false)
  const [apiKeyInput, setApiKeyInput] = useState('')
  const [apiKeyError, setApiKeyError] = useState(null)
  const [savingApiKey, setSavingApiKey] = useState(false)

  const adminUnlocked = isAdmin && hasApiKey

  useEffect(() => {
    if (!apiKeyPopoverOpen) {
      setApiKeyInput('')
      setApiKeyError(null)
      setSavingApiKey(false)
    }
  }, [apiKeyPopoverOpen])

  const handleAdminKeySubmit = (event) => {
    event.preventDefault()
    const trimmed = apiKeyInput.trim()
    if (!trimmed) {
      setApiKeyError('Enter the admin API key to continue.')
      return
    }
    setApiKeyError(null)
    setSavingApiKey(true)
    try {
      APIService.setAdminKey(trimmed)
      setApiKeyPopoverOpen(false)
    } catch (error) {
      console.error('Failed to persist admin API key', error)
      setApiKeyError('Could not store the API key. Try again.')
    } finally {
      setSavingApiKey(false)
    }
  }

  if (!token) {
    return (
      <Button
        size={isMobile ? 'lg' : 'sm'}
        className={isMobile ? 'w-full' : ''}
        onClick={() => {
          openLoginModal()
          onNavigate?.()
        }}
      >
        <LogIn className="mr-2 h-4 w-4" /> Sign In
      </Button>
    )
  }

  return (
    <div className={isMobile ? 'flex flex-col gap-3' : 'flex items-center gap-4 min-w-0 max-w-xs'}>
      {isAdmin && !adminUnlocked && (
        <span className="sr-only">Admin access requires API key</span>
      )}
      <div className="flex items-center gap-2 text-sm">
        <span
          className="max-w-[140px] truncate font-semibold text-foreground sm:max-w-[200px]"
          title={displayName || 'Signed in'}
        >
          {displayName || 'Signed in'}
        </span>
        {isAdmin ? (
          adminUnlocked ? (
            <Badge variant="default" className="bg-emerald-100 text-emerald-700 border-emerald-200">
              Admin ready
            </Badge>
          ) : isMobile ? (
            <Dialog open={apiKeyPopoverOpen} onOpenChange={setApiKeyPopoverOpen}>
              <DialogTrigger asChild>
                <Badge
                  asChild
                  variant="outline"
                  className="border-amber-300 text-amber-700 cursor-pointer hover:bg-amber-50"
                >
                  <button
                    type="button"
                    className="inline-flex items-center gap-1"
                    aria-haspopup="dialog"
                    aria-expanded={apiKeyPopoverOpen}
                  >
                    <KeyRound className="h-3.5 w-3.5" />
                    API key needed
                  </button>
                </Badge>
              </DialogTrigger>
              <DialogContent className="max-w-[calc(100vw-2rem)] sm:max-w-md">
                <DialogHeader>
                  <DialogTitle className="text-lg">Add admin API key</DialogTitle>
                  <DialogDescription className="text-sm text-muted-foreground">
                    Paste the API key from admin settings to unlock admin tools on this device.
                  </DialogDescription>
                </DialogHeader>
                <form className="space-y-4" onSubmit={handleAdminKeySubmit}>
                  <div className="space-y-2">
                    <Label htmlFor="nav-admin-api-key-mobile" className="text-sm font-medium">
                      API key
                    </Label>
                    <Input
                      id="nav-admin-api-key-mobile"
                      className="h-12 text-base font-mono"
                      autoComplete="off"
                      autoCapitalize="none"
                      autoCorrect="off"
                      spellCheck="false"
                      value={apiKeyInput}
                      onChange={(event) => setApiKeyInput(event.target.value)}
                      placeholder="sk_live_..."
                    />
                  </div>
                  {apiKeyError && (
                    <p className="text-sm text-rose-600">{apiKeyError}</p>
                  )}
                  <Button type="submit" className="h-12 w-full text-base" disabled={savingApiKey}>
                    {savingApiKey && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                    Save key
                  </Button>
                </form>
              </DialogContent>
            </Dialog>
          ) : (
            <Popover open={apiKeyPopoverOpen} onOpenChange={setApiKeyPopoverOpen}>
              <PopoverTrigger asChild>
                <Badge
                  asChild
                  variant="outline"
                  className="border-amber-300 text-amber-700 cursor-pointer hover:bg-amber-50"
                >
                  <button
                    type="button"
                    className="inline-flex items-center gap-1"
                    aria-haspopup="dialog"
                    aria-expanded={apiKeyPopoverOpen}
                  >
                    <KeyRound className="h-3.5 w-3.5" />
                    API key needed
                  </button>
                </Badge>
              </PopoverTrigger>
              <PopoverContent align="end" className="w-80 space-y-3">
                <div className="space-y-1">
                  <p className="text-sm font-semibold text-foreground">Add admin API key</p>
                  <p className="text-sm text-muted-foreground">
                    Paste the API key from admin settings to unlock admin tools on this device.
                  </p>
                </div>
                <form className="space-y-3" onSubmit={handleAdminKeySubmit}>
                  <div className="space-y-2">
                    <Label htmlFor="nav-admin-api-key-desktop" className="text-sm font-medium">
                      API key
                    </Label>
                    <Input
                      id="nav-admin-api-key-desktop"
                      className="h-10 font-mono"
                      autoComplete="off"
                      autoCapitalize="none"
                      autoCorrect="off"
                      spellCheck="false"
                      value={apiKeyInput}
                      onChange={(event) => setApiKeyInput(event.target.value)}
                      placeholder="sk_live_..."
                    />
                  </div>
                  {apiKeyError && (
                    <p className="text-sm text-rose-600">{apiKeyError}</p>
                  )}
                  <Button type="submit" className="h-10 w-full" disabled={savingApiKey}>
                    {savingApiKey && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                    Save key
                  </Button>
                </form>
              </PopoverContent>
            </Popover>
          )
        ) : (
          <Badge variant="secondary">Go On Member</Badge>
        )}
      </div>
      <div className={isMobile ? 'flex flex-col gap-2' : 'flex items-center gap-2'}>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => {
            logout()
            onNavigate?.()
          }}
        >
          <LogOut className="mr-1 h-4 w-4" /> Log Out
        </Button>
      </div>
    </div>
  )
}



// Home page component
// Subscribe page component
function SubscribePage() {
  const [teams, setTeams] = useState([])
  const [selectedTeams, setSelectedTeams] = useState([])
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [message, setMessage] = useState(null)

  useEffect(() => {
    const loadTeams = async () => {
      try {
        // First check database status for debugging
        try {
          await APIService.debugDatabase()
        } catch (dbError) {
          console.warn('⚠️ Could not get database status:', dbError)
        }

        const data = await APIService.getTeams({ european_only: 'true' })
        const { teams: filtered } = filterLatestSeasonTeams(Array.isArray(data) ? data : [])
        setTeams(filtered)
      } catch (error) {
        console.error('❌ Failed to load teams:', error)
        setMessage({ type: 'error', text: 'Failed to load teams. Check console for details.' })
      } finally {
        setLoading(false)
      }
    }

    loadTeams()
  }, [])

  const handleTeamToggle = (teamId) => {
    setSelectedTeams(prev =>
      prev.includes(teamId)
        ? prev.filter(id => id !== teamId)
        : [...prev, teamId]
    )
  }

  const handleSubmit = async (e) => {
    e.preventDefault()

    if (!email || selectedTeams.length === 0) {
      setMessage({ type: 'error', text: 'Please enter email and select at least one team' })
      return
    }

    setSubmitting(true)
    try {
      const response = await APIService.createSubscriptions({
        email,
        team_ids: selectedTeams
      })

      if (response?.verification_required) {
        const teamCount = response.team_count ?? selectedTeams.length
        const expiresLabel = response?.expires_at ? new Date(response.expires_at).toLocaleString() : null
        const detail = expiresLabel ? ` The confirmation link expires on ${expiresLabel}.` : ''
        let text = `Almost done! We sent a confirmation email to ${email} for ${teamCount} team${teamCount === 1 ? '' : 's'}.${detail}`

        // Add waitlist notification if applicable
        const teamsWithoutNewsletters = response?.teams_without_newsletters || []
        if (teamsWithoutNewsletters.length > 0) {
          const teamNames = teamsWithoutNewsletters.map(t => t.team_name).join(', ')
          text += ` Note: ${teamNames} ${teamsWithoutNewsletters.length === 1 ? "doesn't have" : "don't have"} active newsletters yet. We'll notify you once we start generating them!`
        }

        setMessage({
          type: 'success',
          text: text,
        })
      } else {
        const created = response?.created_count ?? 0
        const updated = response?.updated_count ?? 0
        const skippedCount = Array.isArray(response?.skipped) ? response.skipped.length : 0
        const parts = []
        if (created) parts.push(`${created} new`)
        if (updated) parts.push(`${updated} updated`)
        let text = parts.length ? `Subscriptions saved: ${parts.join(', ')}.` : 'Subscriptions updated.'
        if (skippedCount) {
          text += ` ${skippedCount} already active.`
        }

        // Add waitlist notification if applicable
        const teamsWithoutNewsletters = response?.teams_without_newsletters || []
        if (teamsWithoutNewsletters.length > 0) {
          const teamNames = teamsWithoutNewsletters.map(t => t.team_name).join(', ')
          text += ` Note: ${teamNames} ${teamsWithoutNewsletters.length === 1 ? "doesn't have" : "don't have"} active newsletters yet. We'll notify you once we start generating them!`
        }

        setMessage({ type: 'success', text })
      }
      setSelectedTeams([])
    } catch (error) {
      console.error('Failed to create subscriptions', error)
      const detail = error?.body?.error || error.message || 'Failed to create subscriptions'
      setMessage({ type: 'error', text: detail })
    } finally {
      setSubmitting(false)
    }
  }

  // Group teams by league
  const teamsByLeague = teams.reduce((acc, team) => {
    const league = team.league_name || 'Other'
    if (!acc[league]) acc[league] = []
    acc[league].push(team)
    return acc
  }, {})

  return (
    <div className="max-w-4xl mx-auto py-6 sm:px-6 lg:px-8">
      <div className="px-4 py-6 sm:px-0">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-foreground mb-4">
            Subscribe to Team Updates
          </h1>
          <p className="text-lg text-muted-foreground">
            Get AI-powered newsletters about your favorite teams' academy players
          </p>
        </div>

        {message && (
          <Alert className={`mb-6 ${message.type === 'error' ? 'border-rose-500' : 'border-emerald-500'}`}>
            {message.type === 'error' ? (
              <AlertCircle className="h-4 w-4" />
            ) : (
              <CheckCircle className="h-4 w-4" />
            )}
            <AlertDescription>{message.text}</AlertDescription>
          </Alert>
        )}

        <form onSubmit={handleSubmit} className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Subscription Details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label htmlFor="email">Email Address</Label>
                <Input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="your.email@example.com"
                  required
                />
                <p className="mt-1 text-xs text-muted-foreground">
                  We’ll email you a confirmation link to comply with anti-spam rules.
                </p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Select Teams</CardTitle>
              <CardDescription>Choose teams using the searchable selector. ({selectedTeams.length} selected)</CardDescription>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="text-center py-8">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto"></div>
                </div>
              ) : (
                <div className="space-y-4">
                  <TeamMultiSelect teams={teams} value={selectedTeams} onChange={setSelectedTeams} placeholder="Search and select teams…" />
                  <Accordion type="multiple" className="rounded-md border">
                    {Object.entries(teamsByLeague).map(([league, leagueTeams]) => (
                      <AccordionItem key={league} value={league} className="border-b last:border-b-0">
                        <AccordionTrigger className="px-4">
                          <div className="flex items-center">
                            <div className="w-4 h-4 rounded mr-2" style={{ backgroundColor: LEAGUE_COLORS[league] || '#666' }} />
                            <span className="font-medium">{league}</span>
                            <Badge variant="secondary" className="ml-2">{leagueTeams.length}</Badge>
                          </div>
                        </AccordionTrigger>
                        <AccordionContent>
                          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 px-4 pb-2">
                            {leagueTeams.map((team) => (
                              <div key={team.id} className={`p-3 border rounded-lg cursor-pointer transition-colors ${selectedTeams.includes(team.id) ? 'border-primary bg-primary/5' : 'border-border hover:border-border'}`} onClick={() => handleTeamToggle(team.id)}>
                                <div className="flex items-center justify-between">
                                  <div>
                                    <div className="font-medium">{team.name}</div>
                                    <div className="text-sm text-muted-foreground">{team.current_loaned_out_count} players tracked</div>
                                  </div>
                                  {selectedTeams.includes(team.id) && (<CheckCircle className="h-5 w-5 text-primary" />)}
                                </div>
                              </div>
                            ))}
                          </div>
                        </AccordionContent>
                      </AccordionItem>
                    ))}
                  </Accordion>
                </div>
              )}
            </CardContent>
          </Card>

          <div className="flex justify-center">
            <Button
              type="submit"
              size="lg"
              disabled={submitting || selectedTeams.length === 0}
              className="bg-primary hover:bg-primary/90"
            >
              {submitting ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                  Subscribing...
                </>
              ) : (
                <>
                  <Mail className="h-5 w-5 mr-2" />
                  Subscribe to {selectedTeams.length} Teams
                </>
              )}
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}

// Teams page component
const COMPETITION_TABS = [
  { key: 'all', label: 'All', color: '#6b7280' },
  { key: 'Premier League', apiId: 39, label: 'Premier League', color: LEAGUE_COLORS['Premier League'] },
  { key: 'La Liga', apiId: 140, label: 'La Liga', color: LEAGUE_COLORS['La Liga'] },
  { key: 'Serie A', apiId: 135, label: 'Serie A', color: LEAGUE_COLORS['Serie A'] },
  { key: 'Bundesliga', apiId: 78, label: 'Bundesliga', color: LEAGUE_COLORS['Bundesliga'] },
  { key: 'Ligue 1', apiId: 61, label: 'Ligue 1', color: LEAGUE_COLORS['Ligue 1'] },
  { key: 'champions-league', label: 'Champions League', color: LEAGUE_COLORS['Champions League'] },
]

const CL_CURRENT_SEASON = new Date().getFullYear() - (new Date().getMonth() < 7 ? 1 : 0)
const CL_SEASONS = Array.from({ length: 4 }, (_, i) => CL_CURRENT_SEASON - i)
const formatClSeason = (s) => `${s}/${(s + 1).toString().slice(-2)}`

const REGION_ORDER = ['Europe', 'South America', 'North America', 'Asia', 'Other']

function TeamsPage() {
  const [teams, setTeams] = useState([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('all')
  const [message, setMessage] = useState(null)
  const [teamSearch, setTeamSearch] = useState('')
  const [activeTab, setActiveTab] = useState('all')
  const [leagueRegions, setLeagueRegions] = useState({})

  // Server-side search across the ENTIRE teams database (not just the loaded
  // supported-league subset). null = no fetched results for the current query.
  const [searchResults, setSearchResults] = useState(null)
  const [searchLoading, setSearchLoading] = useState(false)

  // Champions League state
  const [clTeams, setClTeams] = useState([])
  const [clLoading, setClLoading] = useState(false)
  const [clSeason, setClSeason] = useState(CL_CURRENT_SEASON)

  // Subscribe dialog state
  const [subscribeOpen, setSubscribeOpen] = useState(false)
  const [selectedTeams, setSelectedTeams] = useState([])
  const [email, setEmail] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const isCL = activeTab === 'champions-league'

  useEffect(() => {
    const loadTeams = async () => {
      try {
        const filters = { european_only: 'true' }
        if (filter === 'with_loans') {
          filters.has_loans = 'true'
        }

        const data = await APIService.getTeams(filters)
        const { teams: filtered } = filterLatestSeasonTeams(Array.isArray(data) ? data : [])
        setTeams(filtered)
      } catch (error) {
        console.error('Failed to load teams:', error)
      } finally {
        setLoading(false)
      }
    }

    loadTeams()
  }, [filter])

  // League API id → region map for grouping the All tab by region.
  // Keyed by id, not name — league names collide globally (two "Serie A"s).
  useEffect(() => {
    APIService.getLeagues()
      .then((data) => {
        const map = {}
        for (const league of Array.isArray(data) ? data : []) {
          if (league?.league_id) map[league.league_id] = league.region || 'Europe'
        }
        setLeagueRegions(map)
      })
      .catch((err) => console.error('Failed to load leagues for regions', err))
  }, [])

  // Debounced server-side search: query the FULL teams database so results
  // include every league/region (and teams outside the supported-league
  // browse), independent of the active competition tab.
  useEffect(() => {
    const q = teamSearch.trim()
    if (!q) {
      setSearchResults(null)
      setSearchLoading(false)
      return
    }
    setSearchResults(null) // drop stale results from the previous query
    setSearchLoading(true)
    let cancelled = false
    const handle = setTimeout(async () => {
      try {
        const data = await APIService.getTeams({ search: q })
        if (!cancelled) setSearchResults(Array.isArray(data) ? data : [])
      } catch (err) {
        console.error('Team search failed:', err)
        if (!cancelled) setSearchResults([])
      } finally {
        if (!cancelled) setSearchLoading(false)
      }
    }, 250)
    return () => {
      cancelled = true
      clearTimeout(handle)
    }
  }, [teamSearch])

  // Load CL teams when CL tab is active
  useEffect(() => {
    if (!isCL) return
    const loadCLTeams = async () => {
      setClLoading(true)
      try {
        const data = await APIService.getFeederTeams(2, clSeason)
        setClTeams(data?.teams || [])
      } catch (err) {
        console.error('Failed to load CL teams', err)
        setClTeams([])
      } finally {
        setClLoading(false)
      }
    }
    loadCLTeams()
  }, [isCL, clSeason])

  const handleBulkSubscribe = async () => {
    if (!email.trim() || selectedTeams.length === 0) {
      setMessage({ type: 'error', text: 'Please enter email and select at least one team' })
      return
    }
    setSubmitting(true)
    try {
      await APIService.createSubscriptions({ email: email.trim(), team_ids: selectedTeams })
      setMessage({ type: 'success', text: `Successfully subscribed to ${selectedTeams.length} teams!` })
      setSelectedTeams([])
      setEmail('')
      setSubscribeOpen(false)
    } catch (error) {
      console.error('Failed to create subscriptions', error)
      setMessage({ type: 'error', text: 'Failed to create subscriptions' })
    } finally {
      setSubmitting(false)
    }
  }

  // Filter teams by search query
  const searchQuery = teamSearch.trim().toLowerCase()

  // For domestic tabs, filter base set by active tab.
  // Match on league API id when available — league names collide globally
  // (Italy's Serie A vs Brazil's Serie A).
  const domesticBaseTeams = useMemo(() => {
    if (isCL) return []
    if (activeTab === 'all') return teams
    const tab = COMPETITION_TABS.find(t => t.key === activeTab)
    if (tab?.apiId) {
      return teams.filter(t => (t.league_api_id ? t.league_api_id === tab.apiId : t.league_name === activeTab))
    }
    return teams.filter(t => t.league_name === activeTab)
  }, [teams, activeTab, isCL])

  // Instant client-side preview from already-loaded teams (any tab) while the
  // global server search is in flight — so results are never trapped inside
  // the active competition tab.
  const clientPreview = useMemo(() => {
    if (!searchQuery) return []
    return teams.filter((team) => team.name?.toLowerCase().includes(searchQuery))
  }, [teams, searchQuery])

  // What we render while searching: full-database server results once they
  // arrive, otherwise the instant client preview. The backend already dedupes
  // to one row per team, so no season filtering is applied here.
  const searchDisplay = useMemo(() => {
    const rows = searchResults !== null ? searchResults : clientPreview
    return [...rows].sort((a, b) => {
      const aStarts = a.name.toLowerCase().startsWith(searchQuery) ? 0 : 1
      const bStarts = b.name.toLowerCase().startsWith(searchQuery) ? 0 : 1
      return aStarts - bStarts || a.name.localeCompare(b.name)
    })
  }, [searchResults, clientPreview, searchQuery])

  const isSearching = searchQuery.length > 0

  // Group teams by region → league (used when not searching, domestic tabs only).
  // Leagues are keyed by API id so same-named leagues (Italy/Brazil "Serie A")
  // never merge; each group carries its display name + country.
  const teamsByRegion = useMemo(() => {
    const byLeague = {}
    for (const team of domesticBaseTeams) {
      const key = team.league_api_id || team.league_name || 'Other'
      if (!byLeague[key]) {
        byLeague[key] = {
          name: team.league_name || 'Other',
          country: team.league_country || null,
          teams: [],
        }
      }
      byLeague[key].teams.push(team)
    }
    const regions = {}
    for (const [key, group] of Object.entries(byLeague)) {
      const region = leagueRegions[Number(key)] || 'Europe'
      if (!regions[region]) regions[region] = {}
      regions[region][key] = group
    }
    return Object.fromEntries(
      Object.entries(regions).sort(([a], [b]) => {
        const ai = REGION_ORDER.indexOf(a); const bi = REGION_ORDER.indexOf(b)
        return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi)
      })
    )
  }, [domesticBaseTeams, leagueRegions])

  // Compact team card renderer
  const renderTeamCard = (team) => (
    <Link
      key={team.id}
      to={`/teams/${team.slug || team.id}`}
      className="flex items-center gap-3 p-3 rounded-lg border bg-card text-left transition-all w-full border-border hover:border-border hover:shadow-sm"
    >
      <Avatar className="h-9 w-9 shrink-0">
        {team.logo ? <AvatarImage src={team.logo} alt={team.name} /> : null}
        <AvatarFallback className="text-xs bg-secondary">
          {team.name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()}
        </AvatarFallback>
      </Avatar>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-foreground truncate">{team.name}</p>
        {team.league_name && <p className="text-xs text-muted-foreground/70 truncate">{team.league_name}</p>}
      </div>
      {team.is_tracked !== false && (
        <span className="text-xs text-muted-foreground/70 tabular-nums shrink-0">
          {team.tracked_player_count ?? team.current_loaned_out_count ?? 0}
        </span>
      )}
      {team.is_tracked === false && (
        <span className="text-xs text-amber-500 shrink-0">untracked</span>
      )}
      <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/50 shrink-0" />
    </Link>
  )

  const renderClTeamCard = (team) => (
    <Link
      key={team.team_api_id}
      to={`/teams/${team.team_api_id}?tab=alumni&view=origins&league=2&season=${clSeason}`}
      className="flex items-center gap-3 p-3 rounded-lg border bg-card text-left transition-all w-full border-border hover:border-border hover:shadow-sm"
    >
      <Avatar className="h-9 w-9 shrink-0">
        {team.logo ? <AvatarImage src={team.logo} alt={team.name} /> : null}
        <AvatarFallback className="text-xs bg-secondary">
          {team.name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()}
        </AvatarFallback>
      </Avatar>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-foreground truncate">{team.name}</p>
        <p className="text-xs text-muted-foreground/70 truncate">{team.country}</p>
      </div>
      <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/50 shrink-0" />
    </Link>
  )

  return (
    <div className="max-w-[1400px] mx-auto py-6 sm:px-6 lg:px-8">
      <div className="flex flex-col lg:flex-row gap-6">
        {/* Main Content */}
        <div className="flex-1 min-w-0 px-4 py-6 sm:px-0">
          {/* Sticky header */}
          <div className="sticky top-0 z-10 bg-card/90 backdrop-blur py-3 px-1 -mx-1 mb-6 border-b border-border">
            <div className="flex items-center gap-3 mb-3">
              <h1 className="text-2xl font-semibold text-foreground">Teams</h1>
              <div className="ml-auto flex items-center gap-2">
                <Button variant="outline" size="sm" className="text-xs" onClick={() => setSubscribeOpen(true)}>
                  <Mail className="h-3.5 w-3.5 mr-1" />
                  Subscribe
                </Button>
                <Select value={filter} onValueChange={setFilter}>
                  <SelectTrigger className="w-36 h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Teams</SelectItem>
                    <SelectItem value="with_loans">With Players</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            {/* Competition tabs */}
            <div className="flex gap-1.5 overflow-x-auto scrollbar-hide pb-1 -mx-1 px-1 mb-3">
              {COMPETITION_TABS.map(tab => (
                <button
                  key={tab.key}
                  onClick={() => { setActiveTab(tab.key); setTeamSearch('') }}
                  className={[
                    "shrink-0 px-3 py-1.5 rounded-full text-xs font-medium transition-colors",
                    activeTab === tab.key
                      ? "text-white shadow-sm"
                      : "text-foreground/70 hover:bg-secondary"
                  ].join(' ')}
                  style={activeTab === tab.key ? { backgroundColor: tab.color } : undefined}
                >
                  {tab.label}
                </button>
              ))}
            </div>
            {/* Season selector for CL */}
            {isCL && (
              <div className="mb-3">
                <Select value={String(clSeason)} onValueChange={(v) => setClSeason(Number(v))}>
                  <SelectTrigger className="w-[140px] h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {CL_SEASONS.map((s) => (
                      <SelectItem key={s} value={String(s)}>
                        {formatClSeason(s)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/70" />
              <Input
                type="text"
                placeholder="Search teams..."
                value={teamSearch}
                onChange={(e) => setTeamSearch(e.target.value)}
                className="pl-10 pr-10 h-9"
              />
              {teamSearch && (
                <button
                  onClick={() => setTeamSearch('')}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground/70 hover:text-muted-foreground"
                >
                  <X className="h-4 w-4" />
                </button>
              )}
            </div>
          </div>

          {message && (
            <Alert className={`mb-4 ${message.type === 'error' ? 'border-rose-500' : message.type === 'info' ? 'border-primary/20' : 'border-emerald-500'}`}>
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{message.text}</AlertDescription>
            </Alert>
          )}

          {isSearching ? (
            <div className="space-y-3">
              <div className="flex items-center justify-between px-1">
                <p className="text-sm text-muted-foreground flex items-center gap-2">
                  {searchLoading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                  {searchLoading
                    ? 'Searching all teams…'
                    : searchDisplay.length === 0
                      ? 'No teams found'
                      : `${searchDisplay.length} team${searchDisplay.length !== 1 ? 's' : ''} found`}
                </p>
                <Button variant="ghost" size="sm" className="text-xs" onClick={() => setTeamSearch('')}>
                  Clear
                </Button>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
                {searchDisplay.map((team) => renderTeamCard(team))}
              </div>
            </div>
          ) : (isCL ? clLoading : loading) ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground/70" />
            </div>
          ) : isCL ? (
            <div>
              <div className="flex items-center gap-3 mb-3 pl-1">
                <div className="w-1 h-5 rounded-full" style={{ backgroundColor: LEAGUE_COLORS['Champions League'] }} />
                <h2 className="text-sm font-semibold text-foreground">Champions League {formatClSeason(clSeason)}</h2>
                <span className="text-xs text-muted-foreground/70">{clTeams.length} teams</span>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
                {clTeams.map((team) => renderClTeamCard(team))}
              </div>
            </div>
          ) : (
            <div className="space-y-10">
              {Object.entries(teamsByRegion).map(([region, regionLeagues]) => (
                <div key={region}>
                  <div className="flex items-center gap-2 mb-4 pl-1">
                    <Globe className="h-3.5 w-3.5 text-primary" />
                    <h2 className="text-xs font-semibold uppercase tracking-[0.15em] text-primary">{region}</h2>
                    <div className="flex-1 h-px bg-border" />
                  </div>
                  <div className="space-y-8">
                    {Object.entries(regionLeagues).map(([leagueKey, group]) => (
                      <div key={leagueKey}>
                        <div className="flex items-center gap-3 mb-3 pl-1">
                          <div className="w-1 h-5 rounded-full" style={{ backgroundColor: LEAGUE_COLORS[group.name] || '#9ca3af' }} />
                          <h2 className="text-sm font-semibold text-foreground">{group.name}</h2>
                          {group.country && <span className="text-xs text-muted-foreground/70">{group.country}</span>}
                          <span className="text-xs text-muted-foreground/70 tabular-nums">{group.teams.length}</span>
                        </div>
                        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
                          {group.teams.map((team) => renderTeamCard(team))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Subscribe Dialog */}
          <Dialog open={subscribeOpen} onOpenChange={setSubscribeOpen}>
            <DialogContent className="sm:max-w-md">
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2">
                  <Mail className="h-5 w-5 text-primary" />
                  Subscribe to Team Updates
                </DialogTitle>
                <DialogDescription>
                  Get weekly newsletters for the teams you follow.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-4 py-2">
                <TeamMultiSelect
                  teams={teams}
                  value={selectedTeams}
                  onChange={setSelectedTeams}
                  placeholder="Search and select teams..."
                  className="w-full"
                />
                <div>
                  <Label htmlFor="sub-email" className="text-xs">Email Address</Label>
                  <Input
                    id="sub-email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="your.email@example.com"
                    className="h-9 mt-1"
                  />
                </div>
              </div>
              <DialogFooter className="gap-2 sm:gap-0">
                <Button variant="outline" onClick={() => setSubscribeOpen(false)}>Cancel</Button>
                <Button onClick={handleBulkSubscribe} disabled={submitting || selectedTeams.length === 0}>
                  {submitting ? 'Subscribing...' : `Subscribe (${selectedTeams.length})`}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

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

// Newsletters page component
function NewslettersPage() {
  const [rawNewsletters, setRawNewsletters] = useState([])
  const [newsletters, setNewsletters] = useState([])
  const [focusedNewsletterDetail, setFocusedNewsletterDetail] = useState(null)
  const [_focusedNewsletterLoading, setFocusedNewsletterLoading] = useState(false)
  const commentaryIdParam = useQueryParam('commentary_id', null)
  const [loading, setLoading] = useState(true)
  const [dateRange, setDateRange] = useState({ startDate: '', endDate: '', preset: 'all_time' })
  const [expandedId, setExpandedId] = useState(null)
  const auth = useAuth()
  const { openLoginModal } = useAuthUI()
  const navigate = useNavigate()
  const location = useLocation()
  const searchParams = new URLSearchParams(location.search)
  const journalistIdParam = searchParams.get('journalist_id')
  const teamIdParam = searchParams.get('team')
  const teamNameParam = searchParams.get('team_name')
  const { newsletterId: newsletterIdParam } = useParams()
  const buildNewsletterUrl = useCallback((item) => {
    if (!item) return null
    const slug = item.public_slug || item.slug || item.id
    if (!slug && slug !== 0) return null
    return `/newsletters/${encodeURIComponent(String(slug))}`
  }, [])
  const [commentsByNewsletter, setCommentsByNewsletter] = useState({})
  const commentsRef = useRef(new Map())
  const [commentsLoading, setCommentsLoading] = useState({})
  const [commentsError, setCommentsError] = useState({})
  const [commentDrafts, setCommentDrafts] = useState({})
  const [commentBusy, setCommentBusy] = useState({})
  const [displayNameEditing, setDisplayNameEditing] = useState(false)
  const [displayNameInput, setDisplayNameInput] = useState(auth.displayName || '')
  const [displayNameBusy, setDisplayNameBusy] = useState(false)
  const [displayNameStatus, setDisplayNameStatus] = useState(null)
  const prefetchedCommentsRef = useRef(new Set())
  const [trackedTeamIds, setTrackedTeamIds] = useState([])
  const [trackedTeamMeta, setTrackedTeamMeta] = useState({})
  const [currentPage, setCurrentPage] = useState(1)
  const [allTeams, setAllTeams] = useState([])
  const [latestSeason, setLatestSeason] = useState(null)
  const [followedTeamFilter, setFollowedTeamFilter] = useState('')
  const [leagueFilter, setLeagueFilter] = useState('')
  const [teamFilter, setTeamFilter] = useState('')
  const [_mySubscriptions, setMySubscriptions] = useState([])
  const [viewingJournalist, setViewingJournalist] = useState(null)

  useEffect(() => {
    if (!journalistIdParam) {
      setViewingJournalist(null)
      return
    }
    APIService.getJournalists().then(list => {
      const found = list.find(j => j.id === parseInt(journalistIdParam))
      setViewingJournalist(found)
    }).catch(console.error)
  }, [journalistIdParam])

  // Set team filter from URL param
  useEffect(() => {
    if (teamIdParam) {
      setTeamFilter(teamIdParam)
      // Also set the league filter if we can find the team's league
      if (allTeams.length > 0) {
        const team = allTeams.find(t => String(t.id) === teamIdParam)
        if (team && team.league_name) {
          setLeagueFilter(team.league_name)
        }
      }
    }
  }, [teamIdParam, allTeams])

  useEffect(() => {
    if (auth.token) {
      APIService.getMySubscriptions().then(setMySubscriptions).catch(console.error)
    }
  }, [auth.token])

  const trackedTeamIdSet = useMemo(() => new Set(trackedTeamIds.map((id) => String(id))), [trackedTeamIds])
  const latestTeamIds = useMemo(() => {
    if (!allTeams.length) return new Set()
    return new Set(allTeams.map((team) => String(team.id)))
  }, [allTeams])

  const focusedNewsletterId = useMemo(() => {
    const parsed = parseNewsletterId(newsletterIdParam)
    return parsed ?? null
  }, [newsletterIdParam])

  const focusedViewActive = useMemo(() => focusedNewsletterId !== null, [focusedNewsletterId])

  const teamMetaById = useMemo(() => {
    const meta = {}
    for (const [key, value] of Object.entries(trackedTeamMeta)) {
      if (!key) continue
      meta[key] = {
        name: value?.name || `Team #${key}`,
        league: value?.league || 'Other'
      }
    }
    for (const team of allTeams) {
      if (!team || typeof team.id === 'undefined' || team.id === null) continue
      const key = String(team.id)
      meta[key] = {
        name: team.name || `Team #${key}`,
        league: team.league_name || team.league || 'Other'
      }
    }
    for (const newsletter of newsletters) {
      if (!newsletter || typeof newsletter.team_id === 'undefined' || newsletter.team_id === null) continue
      const key = String(newsletter.team_id)
      const existing = meta[key] || {}
      meta[key] = {
        name: existing.name || newsletter.team_name || `Team #${key}`,
        league: existing.league || newsletter.team_league_name || 'Other'
      }
    }
    return meta
  }, [trackedTeamMeta, allTeams, newsletters])

  const teamsByLeagueMap = useMemo(() => {
    const result = {}
    for (const [id, meta] of Object.entries(teamMetaById)) {
      const league = meta?.league || 'Other'
      if (!result[league]) result[league] = []
      result[league].push({ id, name: meta?.name || `Team #${id}` })
    }
    for (const values of Object.values(result)) {
      values.sort((a, b) => a.name.localeCompare(b.name))
    }
    return result
  }, [teamMetaById])

  const leagueOptions = useMemo(() => Object.keys(teamsByLeagueMap).sort((a, b) => a.localeCompare(b)), [teamsByLeagueMap])

  const teamsForSelectedLeague = useMemo(() => {
    if (!leagueFilter) return []
    return teamsByLeagueMap[leagueFilter] || []
  }, [leagueFilter, teamsByLeagueMap])

  const followedTeamOptions = useMemo(() => {
    if (!trackedTeamIds.length) return []
    const seen = new Set()
    const options = []
    for (const id of trackedTeamIds) {
      const key = String(id)
      if (seen.has(key)) continue
      seen.add(key)
      const meta = teamMetaById[key]
      options.push({ id: key, name: meta?.name || `Team #${key}` })
    }
    options.sort((a, b) => a.name.localeCompare(b.name))
    return options
  }, [trackedTeamIds, teamMetaById])

  const filtersActive = useMemo(() => Boolean(followedTeamFilter || leagueFilter || teamFilter), [followedTeamFilter, leagueFilter, teamFilter])

  const clearFilters = useCallback(() => {
    setFollowedTeamFilter('')
    setLeagueFilter('')
    setTeamFilter('')
  }, [])

  const prioritizedNewsletters = useMemo(() => {
    if (!trackedTeamIdSet.size) return newsletters
    const favorites = []
    const others = []
    for (const item of newsletters) {
      const key = typeof item.team_id !== 'undefined' ? String(item.team_id) : undefined
      if (key && trackedTeamIdSet.has(key)) {
        favorites.push(item)
      } else {
        others.push(item)
      }
    }
    return [...favorites, ...others]
  }, [newsletters, trackedTeamIdSet])

  const filteredNewsletters = useMemo(() => {
    let pool = prioritizedNewsletters
    if (focusedViewActive && focusedNewsletterId !== null) {
      return pool.filter((item) => Number(item.id) === focusedNewsletterId)
    }
    if (followedTeamFilter) {
      pool = pool.filter((item) => String(item.team_id) === followedTeamFilter)
    } else if (teamFilter) {
      pool = pool.filter((item) => String(item.team_id) === teamFilter)
    } else if (leagueFilter) {
      pool = pool.filter((item) => {
        if (typeof item.team_id === 'undefined' || item.team_id === null) return false
        const key = String(item.team_id)
        const meta = teamMetaById[key]
        const leagueName = meta?.league || item.team_league_name || 'Other'
        return leagueName === leagueFilter
      })
    }
    return pool
  }, [prioritizedNewsletters, followedTeamFilter, teamFilter, leagueFilter, teamMetaById])

  const totalPages = useMemo(() => {
    if (!filteredNewsletters.length) return 1
    return Math.max(1, Math.ceil(filteredNewsletters.length / NEWSLETTER_PAGE_SIZE))
  }, [filteredNewsletters])

  const paginatedNewsletters = useMemo(() => {
    if (!filteredNewsletters.length) return []
    const start = (currentPage - 1) * NEWSLETTER_PAGE_SIZE
    return filteredNewsletters.slice(start, start + NEWSLETTER_PAGE_SIZE)
  }, [filteredNewsletters, currentPage])

  const focusedNewsletters = useMemo(() => {
    if (!focusedViewActive || focusedNewsletterId === null) return []
    if (focusedNewsletterDetail && Number(focusedNewsletterDetail.id) === focusedNewsletterId) {
      return [focusedNewsletterDetail]
    }
    return filteredNewsletters.filter((item) => Number(item.id) === focusedNewsletterId)
  }, [focusedViewActive, filteredNewsletters, focusedNewsletterId, focusedNewsletterDetail])

  const displayNewsletters = focusedViewActive ? focusedNewsletters : paginatedNewsletters

  const focusedNewsletterFound = focusedViewActive && focusedNewsletters.length > 0

  const filteredTotal = focusedViewActive ? focusedNewsletters.length : filteredNewsletters.length
  const pageStart = displayNewsletters.length
    ? (focusedViewActive ? 1 : (currentPage - 1) * NEWSLETTER_PAGE_SIZE + 1)
    : 0
  const pageEnd = displayNewsletters.length ? pageStart + displayNewsletters.length - 1 : 0

  useEffect(() => {
    const loadNewsletters = async () => {
      try {
        const params = { published_only: 'true' }

        // Use date range if available, otherwise show all newsletters
        if (dateRange.startDate && dateRange.endDate) {
          params.week_start = dateRange.startDate
          params.week_end = dateRange.endDate
        }

        const data = await APIService.getNewsletters(params)
        setRawNewsletters(Array.isArray(data) ? data : [])
      } catch (error) {
        console.error('Failed to load newsletters:', error)
      } finally {
        setLoading(false)
      }
    }

    loadNewsletters()
  }, [dateRange])

  useEffect(() => {
    if (!rawNewsletters.length) {
      setNewsletters([])
      return
    }
    if (!latestTeamIds.size) {
      setNewsletters(rawNewsletters)
      return
    }
    const filtered = rawNewsletters.filter((item) => latestTeamIds.has(String(item.team_id)))
    setNewsletters(filtered)
  }, [rawNewsletters, latestTeamIds])

  // Load focused newsletter detail (for commentaries) when a specific newsletter is requested
  useEffect(() => {
    let cancelled = false
    if (!focusedViewActive || focusedNewsletterId === null) {
      setFocusedNewsletterDetail(null)
      return () => { }
    }

    const fetchDetail = async () => {
      setFocusedNewsletterLoading(true)
      try {
        const params = {}
        if (journalistIdParam) {
          params.journalist_id = journalistIdParam
        }
        const detail = await APIService.getNewsletter(focusedNewsletterId, params)
        if (cancelled) return

        // Refresh fixture results (updates any past fixtures with scores)
        try {
          const refreshResult = await APIService.refreshNewsletterFixtures(focusedNewsletterId)
          if (refreshResult?.enriched_content) {
            detail.enriched_content = refreshResult.enriched_content
          }
        } catch (_) {
          // ignore refresh errors - continue with original data
        }

        // If a specific commentary is requested and missing, fetch and merge it
        if (commentaryIdParam && (!detail.commentaries || !detail.commentaries.some(c => String(c.id) === String(commentaryIdParam)))) {
          try {
            const c = await APIService.getCommentary(commentaryIdParam)
            if (c) {
              if (!Array.isArray(detail.commentaries)) detail.commentaries = []
              detail.commentaries.push(c)
            }
          } catch (_) {
            // ignore commentary fetch errors
          }
        }

        setFocusedNewsletterDetail(detail)
      } catch {
        if (!cancelled) setFocusedNewsletterDetail(null)
      } finally {
        if (!cancelled) setFocusedNewsletterLoading(false)
      }
    }

    fetchDetail()
    return () => { cancelled = true }
  }, [focusedViewActive, focusedNewsletterId, journalistIdParam, commentaryIdParam])

  useEffect(() => {
    commentsRef.current = new Map(Object.entries(commentsByNewsletter))
  }, [commentsByNewsletter])

  useEffect(() => {
    let cancelled = false
    if (!auth.token) {
      setTrackedTeamIds((prev) => (prev.length ? [] : prev))
      setTrackedTeamMeta({})
      return () => { cancelled = true }
    }

    const loadTrackedTeams = async () => {
      try {
        const rows = await APIService.getMySubscriptions()
        if (cancelled) return
        const normalized = Array.isArray(rows)
          ? Array.from(new Set(
            rows
              .map((row) => row?.team_id)
              .filter((id) => id !== null && id !== undefined)
              .map((id) => String(id))
          ))
          : []
        const meta = {}
        if (Array.isArray(rows)) {
          for (const row of rows) {
            if (!row || row.team_id === null || row.team_id === undefined) continue
            const key = String(row.team_id)
            const team = row.team || {}
            if (!meta[key]) {
              meta[key] = {
                name: team.name || team.team_name || `Team #${key}`,
                league: team.league_name || team.league || 'Other'
              }
            }
          }
        }
        setTrackedTeamIds((prev) => {
          if (prev.length === normalized.length && prev.every((id, index) => id === normalized[index])) {
            return prev
          }
          return normalized
        })
        setTrackedTeamMeta(meta)
      } catch (error) {
        if (!cancelled) {
          console.warn('Failed to load user subscriptions', error)
          setTrackedTeamIds((prev) => (prev.length ? [] : prev))
          setTrackedTeamMeta({})
        }
      }
    }

    loadTrackedTeams()
    return () => {
      cancelled = true
    }
  }, [auth.token])

  useEffect(() => {
    setCurrentPage(1)
  }, [dateRange, trackedTeamIds, followedTeamFilter, leagueFilter, teamFilter])

  useEffect(() => {
    if (currentPage > totalPages) {
      setCurrentPage(totalPages)
    }
  }, [currentPage, totalPages])

  useEffect(() => {
    if (focusedViewActive) return
    if (!expandedId) return
    const visibleIds = new Set(displayNewsletters.map((n) => n.id))
    if (!visibleIds.has(expandedId)) {
      setExpandedId(null)
    }
  }, [focusedViewActive, displayNewsletters, expandedId])

  useEffect(() => {
    let cancelled = false
    if (allTeams.length) return undefined

    const loadTeamsMeta = async () => {
      try {
        const rows = await APIService.getTeams({ european_only: 'true' })
        if (cancelled) return
        if (!Array.isArray(rows)) {
          setAllTeams([])
          setLatestSeason(null)
          return
        }
        const seasons = rows
          .map((team) => parseInt(team.season, 10))
          .filter((value) => !Number.isNaN(value))
        const latest = seasons.length ? Math.max(...seasons) : null
        const filtered = latest !== null
          ? rows.filter((team) => parseInt(team.season, 10) === latest)
          : rows
        setLatestSeason(latest)
        setAllTeams(filtered)
      } catch (error) {
        if (!cancelled) {
          console.warn('Failed to load team metadata', error)
        }
      }
    }

    loadTeamsMeta()
    return () => {
      cancelled = true
    }
  }, [allTeams.length])

  useEffect(() => {
    if (followedTeamFilter) {
      if (leagueFilter) setLeagueFilter('')
      if (teamFilter) setTeamFilter('')
    }
  }, [followedTeamFilter, leagueFilter, teamFilter])

  useEffect(() => {
    if (leagueFilter) {
      if (followedTeamFilter) setFollowedTeamFilter('')
    } else if (teamFilter) {
      setTeamFilter('')
    }
  }, [leagueFilter, followedTeamFilter, teamFilter])

  useEffect(() => {
    if (teamFilter && followedTeamFilter) {
      setFollowedTeamFilter('')
    }
  }, [teamFilter, followedTeamFilter])

  const loadComments = useCallback(async (newsletterId, { force = false } = {}) => {
    if (!newsletterId) return
    if (!force && commentsRef.current.has(String(newsletterId))) return
    commentsRef.current.set(String(newsletterId), true)
    setCommentsError(prev => ({ ...prev, [newsletterId]: null }))
    setCommentsLoading(prev => ({ ...prev, [newsletterId]: true }))
    try {
      const rows = await APIService.listNewsletterComments(newsletterId)
      setCommentsByNewsletter(prev => ({ ...prev, [newsletterId]: Array.isArray(rows) ? rows : [] }))
    } catch (error) {
      const message = error?.body?.error || error?.message || 'Failed to load comments'
      setCommentsError(prev => ({ ...prev, [newsletterId]: message }))
    } finally {
      setCommentsLoading(prev => ({ ...prev, [newsletterId]: false }))
    }
  }, [])

  useEffect(() => {
    if (!displayNewsletters.length) return
    const toPrefetch = displayNewsletters.slice(0, 5)
    for (const n of toPrefetch) {
      const key = String(n.id)
      if (prefetchedCommentsRef.current.has(key)) continue
      prefetchedCommentsRef.current.add(key)
      loadComments(n.id)
    }
  }, [displayNewsletters, loadComments])

  useEffect(() => {
    setDisplayNameInput(auth.displayName || '')
  }, [auth.displayName, auth.token])

  useEffect(() => {
    if (!auth.token) {
      setDisplayNameEditing(false)
      setDisplayNameStatus(null)
    }
  }, [auth.token])

  const canComment = Boolean(auth.token)

  useEffect(() => {
    if (expandedId) {
      loadComments(expandedId)
    }
  }, [expandedId, loadComments])

  useEffect(() => {
    if (!focusedViewActive) return
    if (focusedNewsletterFound) {
      const targetId = focusedNewsletters[0]?.id
      if (typeof targetId !== 'undefined' && targetId !== null) {
        setExpandedId((prev) => (prev === targetId ? prev : targetId))
      }
    } else if (!loading) {
      setExpandedId(null)
    }
  }, [focusedViewActive, focusedNewsletterFound, focusedNewsletters, loading])

  useEffect(() => {
    if (focusedViewActive) return
    if (!expandedId) return
    const visibleIds = new Set(displayNewsletters.map((n) => n.id))
    if (!visibleIds.has(expandedId)) {
      setExpandedId(null)
    }
  }, [focusedViewActive, displayNewsletters, expandedId])

  const handleDraftChange = (newsletterId, value) => {
    setCommentsError(prev => ({ ...prev, [newsletterId]: null }))
    setCommentDrafts(prev => ({ ...prev, [newsletterId]: value }))
  }

  const handleSubmitComment = async (newsletterId) => {
    if (!newsletterId) return
    if (!auth.token) {
      openLoginModal()
      return
    }
    const draft = (commentDrafts[newsletterId] || '').trim()
    if (!draft) {
      setCommentsError(prev => ({ ...prev, [newsletterId]: 'Comment cannot be empty' }))
      return
    }
    setCommentBusy(prev => ({ ...prev, [newsletterId]: true }))
    setCommentsError(prev => ({ ...prev, [newsletterId]: null }))
    try {
      const res = await APIService.createNewsletterComment(newsletterId, draft)
      const comment = res?.comment || res
      setCommentsByNewsletter(prev => {
        const existing = prev[newsletterId] || []
        return { ...prev, [newsletterId]: [...existing, comment] }
      })
      setCommentDrafts(prev => ({ ...prev, [newsletterId]: '' }))
      try {
        await APIService.refreshProfile()
      } catch (err) {
        console.warn('Profile refresh after comment failed', err)
      }
    } catch (error) {
      const message = error?.body?.error || error?.message || 'Failed to post comment'
      setCommentsError(prev => ({ ...prev, [newsletterId]: message }))
    } finally {
      setCommentBusy(prev => ({ ...prev, [newsletterId]: false }))
    }
  }

  const handleDisplayNameSave = async () => {
    const trimmed = (displayNameInput || '').trim()
    if (trimmed.length < 3) {
      setDisplayNameStatus({ type: 'error', message: 'Display name must be at least 3 characters.' })
      return
    }
    setDisplayNameBusy(true)
    setDisplayNameStatus(null)
    try {
      await APIService.updateDisplayName(trimmed)
      await APIService.refreshProfile().catch(() => { })
      setDisplayNameStatus({ type: 'success', message: 'Display name updated.' })
      setDisplayNameEditing(false)
    } catch (error) {
      const message = error?.body?.error || error?.message || 'Failed to update display name'
      setDisplayNameStatus({ type: 'error', message })
    } finally {
      setDisplayNameBusy(false)
    }
  }

  const toggleDisplayNameEdit = () => {
    setDisplayNameEditing((editing) => {
      const next = !editing
      if (next) {
        setDisplayNameInput(auth.displayName || '')
        setDisplayNameStatus(null)
      }
      return next
    })
  }



  return (
    <div
      className={
        focusedViewActive
          ? 'max-w-[1440px] mx-auto py-6 px-4 sm:px-6 lg:px-8'
          : 'max-w-[1400px] mx-auto py-6 px-4 sm:px-6 lg:px-8'
      }
    >
      <div
        className={
          focusedViewActive
            ? 'flex flex-col gap-6'
            : 'flex flex-col lg:flex-row gap-6'
        }
      >
        {/* Main Content — full width in detail view, capped + flanked by
            SponsorSidebar in list view. */}
        <div
          className={
            focusedViewActive
              ? 'flex-1 min-w-0 w-full py-6 sm:px-0'
              : 'flex-1 min-w-0 max-w-4xl py-6 sm:px-0 overflow-hidden'
          }
        >
          <div className="text-center mb-8">
            <h1 className="text-2xl sm:text-3xl font-bold text-foreground mb-4">
              Published Newsletters
            </h1>
            <p className="text-lg text-muted-foreground">
              Insights about European academy prospects
            </p>
            {latestSeason !== null && (
              <p className="text-sm text-muted-foreground">
                Showing season {latestSeason}–{String(latestSeason + 1).slice(-2)} newsletters
              </p>
            )}
          </div>
          {focusedViewActive && (
            <div className="mb-4 flex flex-col gap-4">
              <div className="flex justify-start">
                <Button variant="ghost" size="sm" onClick={() => navigate('/newsletters')}>
                  <ArrowLeft className="mr-2 h-4 w-4" /> Back to all newsletters
                </Button>
              </div>
              {viewingJournalist && (
                <Alert className="bg-primary/5 border-primary/20">
                  <div className="flex items-center gap-4">
                    <Avatar className="h-10 w-10 border border-primary/20">
                      <AvatarImage src={viewingJournalist.profile_image_url} />
                      <AvatarFallback>{viewingJournalist.display_name?.substring(0, 2).toUpperCase()}</AvatarFallback>
                    </Avatar>
                    <div>
                      <AlertDescription className="text-primary font-medium">
                        Viewing analysis by {viewingJournalist.display_name}
                      </AlertDescription>
                      <p className="text-sm text-primary">
                        Showing only commentaries written by this journalist.
                      </p>
                    </div>
                    <Button variant="outline" size="sm" className="ml-auto bg-card hover:bg-primary/5 text-primary border-primary/20" onClick={() => navigate(`/journalists/${viewingJournalist.id}`)}>
                      View Profile
                    </Button>
                  </div>
                </Alert>
              )}
            </div>
          )}

          {/* Team filter from URL param banner */}
          {!focusedViewActive && teamIdParam && (() => {
            const filteredTeam = allTeams.find(t => String(t.id) === teamIdParam)
            const teamName = teamNameParam ? decodeURIComponent(teamNameParam) : filteredTeam?.name || 'this team'
            return (
              <div className="mb-6 rounded-xl bg-gradient-to-r from-slate-900 to-slate-800 p-4 sm:p-5 shadow-lg">
                <div className="flex flex-col sm:flex-row sm:items-center gap-4">
                  {/* Team info */}
                  <div className="flex items-center gap-3 flex-1 min-w-0">
                    {filteredTeam?.logo && (
                      <div className="shrink-0 w-12 h-12 sm:w-14 sm:h-14 bg-card rounded-lg p-2 shadow-sm">
                        <img
                          src={filteredTeam.logo}
                          alt={teamName}
                          className="w-full h-full object-contain"
                        />
                      </div>
                    )}
                    <div className="min-w-0">
                      <h3 className="text-white font-semibold text-lg sm:text-xl truncate">
                        {teamName}
                      </h3>
                      <p className="text-slate-400 text-sm">
                        Viewing all newsletters for this team
                      </p>
                    </div>
                  </div>

                  {/* Action button */}
                  <Button
                    variant="secondary"
                    size="sm"
                    className="w-full sm:w-auto bg-card/10 hover:bg-card/20 text-white border-0 backdrop-blur-sm"
                    onClick={() => navigate('/newsletters')}
                  >
                    <XCircle className="w-4 h-4 mr-2" />
                    Clear Filter
                  </Button>
                </div>
              </div>
            )
          })()}

          {!focusedViewActive && (
            <Card className="mb-6">
              <CardHeader>
                <CardTitle>Filter by Date Range</CardTitle>
                <CardDescription>Select a date range to view newsletters from that period</CardDescription>
              </CardHeader>
              <CardContent>
                <UniversalDatePicker onDateChange={setDateRange} />
              </CardContent>
            </Card>
          )}

          {!focusedViewActive && (
            <Card className="mb-6">
              <CardHeader>
                <CardTitle>Filter by Team</CardTitle>
                <CardDescription>
                  Jump to newsletters from teams you follow or browse by league and team.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {followedTeamOptions.length > 0 && (
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                    <Label className="text-sm font-medium text-foreground/80">Teams you follow</Label>
                    <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:items-center">
                      <Select
                        value={followedTeamFilter || 'all'}
                        onValueChange={(value) => setFollowedTeamFilter(value === 'all' ? '' : value)}
                      >
                        <SelectTrigger className="sm:w-64">
                          <SelectValue placeholder="All followed teams" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">All followed teams</SelectItem>
                          {followedTeamOptions.map((team) => (
                            <SelectItem key={team.id} value={team.id}>{team.name}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                )}

                <div className="space-y-2">
                  <Label className="text-sm font-medium text-foreground/80">Browse by league</Label>
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                    <Select
                      value={leagueFilter || 'all'}
                      onValueChange={(value) => setLeagueFilter(value === 'all' ? '' : value)}
                    >
                      <SelectTrigger className="sm:w-64">
                        <SelectValue placeholder="All leagues" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">All leagues</SelectItem>
                        {leagueOptions.map((league) => (
                          <SelectItem key={league} value={league}>{league}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Select
                      value={teamFilter || 'all'}
                      onValueChange={(value) => setTeamFilter(value === 'all' ? '' : value)}
                      disabled={!leagueFilter || !teamsForSelectedLeague.length}
                    >
                      <SelectTrigger className="sm:w-64">
                        <SelectValue placeholder={leagueFilter ? 'Select a team' : 'Select a league first'} />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">All teams in league</SelectItem>
                        {teamsForSelectedLeague.map((team) => (
                          <SelectItem key={team.id} value={team.id}>{team.name}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-muted-foreground">
                  <span>{filtersActive ? 'Filters applied' : 'No team filters applied'}</span>
                  <Button variant="ghost" size="sm" onClick={clearFilters} disabled={!filtersActive}>
                    Clear filters
                  </Button>
                </div>
                {auth.token && trackedTeamIds.length > 0 && (
                  <div className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-secondary p-3 text-sm text-foreground/80 border border-border">
                    <span>You’re following {trackedTeamIds.length} team{trackedTeamIds.length === 1 ? '' : 's'}.</span>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={async () => {
                        try {
                          const resp = await APIService.unsubscribeEmail({ email: auth.email, team_ids: trackedTeamIds })
                          const removed = resp?.count ?? 0
                          setTrackedTeamIds([])
                          // NewslettersPage has no message banner — log to console
                          // for now and rely on the page reload below.
                          console.log(removed ? `Unsubscribed from ${removed} team${removed === 1 ? '' : 's'}.` : 'No active subscriptions were found.')
                        } catch (error) {
                          console.error('Failed to unsubscribe', error)
                        }
                      }}
                    >
                      Unsubscribe from all followed teams
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {loading ? (
            <div className="text-center py-12">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto"></div>
              <p className="mt-4 text-muted-foreground">Loading newsletters...</p>
            </div>
          ) : newsletters.length === 0 ? (
            <div className="text-center py-12">
              <FileText className="h-12 w-12 text-muted-foreground/70 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-foreground mb-2">No newsletters yet</h3>
              <p className="text-muted-foreground">
                Newsletters will appear here once they are generated and published.
              </p>
            </div>
          ) : (focusedViewActive && !loading && !focusedNewsletterFound) ? (
            <div className="text-center py-12">
              <Alert className="max-w-lg mx-auto">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>
                  We couldn't find that newsletter. It may have been unpublished or removed. Return to the full list to browse other issues.
                </AlertDescription>
              </Alert>
            </div>
          ) : (!focusedViewActive && filteredNewsletters.length === 0) ? (
            <div className="text-center py-12">
              <FileText className="h-12 w-12 text-muted-foreground/70 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-foreground mb-2">No newsletters match your filters</h3>
              <p className="text-muted-foreground mb-4">
                Try adjusting the team filters or clearing them to see all newsletters.
              </p>
              <Button variant="outline" onClick={clearFilters} disabled={!filtersActive}>
                Clear filters
              </Button>
            </div>
          ) : (
            <div className="space-y-6">
              {!focusedViewActive && trackedTeamIdSet.size > 0 && (
                <div className="rounded-md border border-primary/20 bg-primary/5 px-3 py-2 text-sm text-primary">
                  Newsletters from teams you follow appear first.
                </div>
              )}
              {displayNewsletters.map((newsletter) => {
                const isTrackedTeam = trackedTeamIdSet.size > 0 && typeof newsletter.team_id !== 'undefined' && trackedTeamIdSet.has(String(newsletter.team_id))
                const readingTime = estimateReadingTime(newsletter.enriched_content || newsletter.content)
                const excerpt = extractNewsletterExcerpt(newsletter.enriched_content || newsletter.content)
                const isExpanded = expandedId === newsletter.id || focusedViewActive
                return (
                  <Card key={newsletter.id}>
                    <CardHeader className="space-y-3">
                      <div className="flex flex-col sm:flex-row sm:justify-between sm:items-start gap-3">
                        <div className="min-w-0 flex-1">
                          <CardTitle className="text-lg sm:text-xl break-words">{newsletter.title}</CardTitle>
                          <CardDescription className="mt-1">
                            {newsletter.team_name} • {newsletter.newsletter_type} newsletter
                          </CardDescription>
                        </div>
                        <div className="flex flex-wrap items-center gap-2">
                          {readingTime && (
                            <Badge variant="outline" className="text-muted-foreground border-border">
                              <Clock className="h-3 w-3 mr-1" />
                              {readingTime}
                            </Badge>
                          )}
                          {isTrackedTeam && (
                            <Badge variant="outline" className="border-emerald-200 bg-emerald-50 text-emerald-700">
                              Tracking
                            </Badge>
                          )}
                          <Badge variant="secondary">
                            {new Date(newsletter.published_date).toLocaleDateString()}
                          </Badge>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => {
                              const target = buildNewsletterUrl(newsletter)
                              if (target) navigate(target)
                            }}
                            disabled={focusedViewActive && expandedId === newsletter.id}
                          >
                            {focusedViewActive ? 'Viewing details' : 'Open detail view'}
                          </Button>
                          {!focusedViewActive && (
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => setExpandedId(expandedId === newsletter.id ? null : newsletter.id)}
                            >
                              {expandedId === newsletter.id ? 'Hide preview' : 'Quick preview'}
                            </Button>
                          )}
                        </div>
                      </div>
                      {/* Content excerpt - shown when not expanded */}
                      {!isExpanded && excerpt && (
                        <p className="text-sm text-muted-foreground line-clamp-2">
                          {excerpt}
                        </p>
                      )}
                    </CardHeader>
                    <CardContent className="overflow-hidden">
                      <div className="text-sm text-muted-foreground mb-2">
                        <Calendar className="h-4 w-4 inline mr-1" />
                        {newsletter.week_start_date && newsletter.week_end_date && (
                          `${new Date(newsletter.week_start_date).toLocaleDateString()} - ${new Date(newsletter.week_end_date).toLocaleDateString()}`
                        )}
                      </div>
                      {isExpanded ? (
                        <NewsletterWriterProvider newsletterId={focusedNewsletterId || newsletter.id}>
                          <div className="max-w-none space-y-6">
                            {/* Writer Bar & Summary Commentaries - Always show in focused view */}
                            {focusedViewActive && (
                              <WriterHeaderSection />
                            )}

                            {/* Prefer JSON-parsed content over pre-rendered HTML so InlinePlayerWriteups can render inside player cards. The Tactical Lens NewsletterView component handles the entire layout — header, summary, highlights, by-numbers, sections with player cards, twitter, community takes, footer. */}
                            {(newsletter.enriched_content && typeof newsletter.enriched_content === 'object') || newsletter.content ? (
                              (() => {
                                try {
                                  const obj = (newsletter.enriched_content && typeof newsletter.enriched_content === 'object')
                                    ? newsletter.enriched_content
                                    : JSON.parse(newsletter.content)
                                  return (
                                    <NewsletterView
                                      newsletter={newsletter}
                                      enrichedContent={obj}
                                      twitterTakesByPlayer={newsletter.twitter_takes_by_player || {}}
                                      twitterTakes={newsletter.twitter_takes || []}
                                      communityTakes={newsletter.community_takes || []}
                                      publicBaseUrl={obj.public_base_url}
                                    />
                                  )
                                } catch {
                                  return (
                                    <div className="prose max-w-none">
                                      <div className="bg-secondary p-4 rounded-lg">
                                        <h3 className="text-lg font-medium text-foreground mb-2">Newsletter Content</h3>
                                        <div className="whitespace-pre-wrap text-foreground/80">{newsletter.content}</div>
                                      </div>
                                    </div>
                                  )
                                }
                              })()
                            ) : newsletter.rendered?.web_html ? (
                              /* Fallback to pre-rendered HTML only when no JSON content exists */
                              <div
                                dangerouslySetInnerHTML={{ __html: newsletter.rendered.web_html }}
                                className="prose max-w-none newsletter-content"
                              />
                            ) : null}


                            <div className="mt-10 space-y-4 border-t pt-6">
                              <div className="flex flex-wrap items-center justify-between gap-2">
                                <div className="flex items-center gap-2">
                                  <MessageCircle className="h-5 w-5 text-primary" />
                                  <h3 className="text-lg font-semibold">Comments</h3>
                                  {(commentsByNewsletter[newsletter.id] || []).length > 0 && (
                                    <Badge variant="secondary">{(commentsByNewsletter[newsletter.id] || []).length}</Badge>
                                  )}
                                </div>
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  onClick={() => loadComments(newsletter.id, { force: true })}
                                  disabled={commentsLoading[newsletter.id]}
                                >
                                  {commentsLoading[newsletter.id] && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                  Refresh
                                </Button>
                              </div>
                              {commentsError[newsletter.id] && (
                                <div className="text-sm text-rose-600">{commentsError[newsletter.id]}</div>
                              )}
                              {commentsLoading[newsletter.id] ? (
                                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                  <Loader2 className="h-4 w-4 animate-spin" />
                                  Loading comments...
                                </div>
                              ) : (commentsByNewsletter[newsletter.id] || []).length === 0 ? (
                                <div className="rounded-md border border-dashed bg-secondary p-4 text-sm text-muted-foreground">
                                  No comments yet. Be the first to share your take.
                                </div>
                              ) : (
                                <div className="space-y-3">
                                  {(commentsByNewsletter[newsletter.id] || []).map((comment) => (
                                    <div key={comment.id} className="rounded-md border bg-card p-4 shadow-sm">
                                      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                                        <span className="text-sm font-semibold text-foreground">
                                          {comment.author_display_name || comment.author_name || 'GOL supporter'}
                                        </span>
                                        <span>{formatRelativeTime(comment.created_at)}</span>
                                      </div>
                                      <div className="mt-2 whitespace-pre-wrap text-sm text-foreground/80">
                                        {comment.body}
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              )}
                              <div className="rounded-lg border bg-card p-4 shadow-sm space-y-3">
                                {canComment ? (
                                  <>
                                    <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                                      <span>Commenting as</span>
                                      <span className="font-semibold text-foreground">{auth.displayName || 'GOL supporter'}</span>
                                      {auth.isAdmin && auth.hasApiKey && (
                                        <Badge variant="outline" className="border-primary/20 text-primary">Admin</Badge>
                                      )}
                                      {!auth.displayNameConfirmed && (
                                        <Badge variant="outline" className="border-amber-300 text-amber-700">Name pending</Badge>
                                      )}
                                      <Button type="button" variant="ghost" size="xs" onClick={toggleDisplayNameEdit}>
                                        {displayNameEditing ? 'Cancel name edit' : 'Edit display name'}
                                      </Button>
                                    </div>
                                    {displayNameEditing && (
                                      <form
                                        className="space-y-2"
                                        onSubmit={(event) => {
                                          event.preventDefault()
                                          handleDisplayNameSave()
                                        }}
                                      >
                                        <Input
                                          value={displayNameInput}
                                          onChange={(e) => setDisplayNameInput(e.target.value)}
                                          maxLength={40}
                                          placeholder="Choose a display name"
                                        />
                                        <div className="flex flex-wrap items-center gap-2">
                                          <Button size="sm" type="submit" disabled={displayNameBusy}>
                                            {displayNameBusy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                            Save
                                          </Button>
                                          <Button
                                            size="sm"
                                            variant="ghost"
                                            type="button"
                                            onClick={() => {
                                              setDisplayNameEditing(false)
                                              setDisplayNameInput(auth.displayName || '')
                                              setDisplayNameStatus(null)
                                            }}
                                          >
                                            Cancel
                                          </Button>
                                        </div>
                                        {displayNameStatus && (
                                          <p className={`text-xs ${displayNameStatus.type === 'error' ? 'text-rose-600' : 'text-emerald-600'}`}>
                                            {displayNameStatus.message}
                                          </p>
                                        )}
                                      </form>
                                    )}
                                    {!displayNameEditing && displayNameStatus && (
                                      <p className={`text-xs ${displayNameStatus.type === 'error' ? 'text-rose-600' : 'text-emerald-600'}`}>
                                        {displayNameStatus.message}
                                      </p>
                                    )}
                                    <Textarea
                                      value={commentDrafts[newsletter.id] || ''}
                                      onChange={(e) => handleDraftChange(newsletter.id, e.target.value)}
                                      placeholder="What stood out to you this week?"
                                      rows={3}
                                    />
                                    <div className="flex flex-wrap items-center justify-between gap-2">
                                      <Button size="sm" onClick={() => handleSubmitComment(newsletter.id)} disabled={commentBusy[newsletter.id]}>
                                        {commentBusy[newsletter.id] ? (
                                          <>
                                            <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Posting...
                                          </>
                                        ) : (
                                          'Post Comment'
                                        )}
                                      </Button>
                                      <span className="text-xs text-muted-foreground">Keep it friendly—no spam or spoilers.</span>
                                    </div>
                                  </>
                                ) : (
                                  <div className="flex flex-col items-start gap-2 text-sm text-muted-foreground">
                                    <p>Sign in to share your thoughts.</p>
                                    <Button size="sm" onClick={() => { setExpandedId(newsletter.id); openLoginModal() }}>
                                      <LogIn className="mr-2 h-4 w-4" /> Sign in to comment
                                    </Button>
                                  </div>
                                )}
                              </div>
                            </div>
                          </div>
                        </NewsletterWriterProvider>
                      ) : (
                        <>
                          <div className="prose max-w-none">
                            {(() => {
                              try {
                                const obj = JSON.parse(newsletter.content)
                                return (
                                  <div className="space-y-3">
                                    {/* Summary */}
                                    {obj.summary && (
                                      <div className="text-foreground/80 leading-relaxed">
                                        {obj.summary}
                                      </div>
                                    )}

                                    {/* Key Highlights */}
                                    {obj.highlights && Array.isArray(obj.highlights) && obj.highlights.length > 0 && (
                                      <div>
                                        <div className="text-sm font-semibold text-foreground mb-2">Key Highlights:</div>
                                        <ul className="list-disc ml-5 space-y-1">
                                          {obj.highlights.slice(0, 3).map((highlight, idx) => (
                                            <li key={idx} className="text-sm text-foreground/80">{highlight}</li>
                                          ))}
                                        </ul>
                                      </div>
                                    )}

                                    {/* Top Performers */}
                                    {obj.by_numbers && (
                                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-3">
                                        {obj.by_numbers.minutes_leaders && obj.by_numbers.minutes_leaders.length > 0 && (
                                          <div className="bg-secondary p-3 rounded-lg">
                                            <div className="text-sm font-semibold text-foreground mb-2">Minutes Leaders:</div>
                                            <div className="space-y-1">
                                              {obj.by_numbers.minutes_leaders.slice(0, 2).map((player, idx) => (
                                                <div key={idx} className="text-sm text-foreground/80">
                                                  <span className="font-medium">{player.player}</span>: {player.minutes}'
                                                </div>
                                              ))}
                                            </div>
                                          </div>
                                        )}

                                        {obj.by_numbers.ga_leaders && obj.by_numbers.ga_leaders.length > 0 && (
                                          <div className="bg-secondary p-3 rounded-lg">
                                            <div className="text-sm font-semibold text-foreground mb-2">Goal Contributors:</div>
                                            <div className="space-y-1">
                                              {obj.by_numbers.ga_leaders.slice(0, 2).map((player, idx) => (
                                                <div key={idx} className="text-sm text-foreground/80">
                                                  <span className="font-medium">{player.player}</span>: {player.g}G {player.a}A
                                                </div>
                                              ))}
                                            </div>
                                          </div>
                                        )}
                                      </div>
                                    )}

                                    {/* Preview of sections */}
                                    {obj.sections && obj.sections.length > 0 && (
                                      <div className="mt-3">
                                        <div className="text-sm font-semibold text-foreground mb-2">This Week's Activity:</div>
                                        <div className="space-y-2">
                                          {obj.sections.slice(0, 2).map((section, idx) => (
                                            <div key={idx} className="border-l-2 border-primary/20 pl-3">
                                              <div className="text-sm font-medium text-foreground">{section.title}</div>
                                              {section.items && section.items.length > 0 && (
                                                <div className="text-sm text-muted-foreground mt-1">
                                                  {section.items.length} player{section.items.length !== 1 ? 's' : ''} featured
                                                </div>
                                              )}
                                            </div>
                                          ))}
                                        </div>
                                      </div>
                                    )}

                                    {/* Read More indicator */}
                                    <div className="mt-4 pt-3 border-t border-border">
                                      <Button
                                        variant="link"
                                        size="sm"
                                        className="px-0"
                                        onClick={() => setExpandedId(newsletter.id)}
                                      >
                                        Open quick preview
                                      </Button>
                                    </div>
                                  </div>
                                )
                              } catch {
                                // Fallback to showing content summary if JSON parsing fails
                                const content = newsletter.content || newsletter.structured_content || ''
                                if (content.length > 200) {
                                  return (
                                    <div className="space-y-3">
                                      <div className="text-foreground/80 leading-relaxed">
                                        {content.substring(0, 200)}...
                                      </div>
                                      <div className="pt-3 border-t border-border">
                                        <Button
                                          variant="link"
                                          size="sm"
                                          className="px-0"
                                          onClick={() => setExpandedId(newsletter.id)}
                                        >
                                          Open quick preview
                                        </Button>
                                      </div>
                                    </div>
                                  )
                                }
                                return (
                                  <div className="space-y-3">
                                    <div className="text-foreground/80 leading-relaxed">
                                      {content}
                                    </div>
                                    <div className="pt-3 border-t border-border">
                                      <Button
                                        variant="link"
                                        size="sm"
                                        className="px-0"
                                        onClick={() => setExpandedId(newsletter.id)}
                                      >
                                        Open quick preview
                                      </Button>
                                    </div>
                                  </div>
                                )
                              }
                            })()}
                          </div>
                          {(() => {
                            const preview = (commentsByNewsletter[newsletter.id] || []).slice(0, 3)
                            if (!preview.length) return null
                            return (
                              <div className="mt-6 rounded-lg border bg-card p-4 shadow-sm space-y-2">
                                <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Top comments</div>
                                <div className="space-y-2">
                                  {preview.map((comment) => (
                                    <div key={comment.id} className="rounded border bg-secondary px-3 py-2">
                                      <div className="text-xs text-muted-foreground">{comment.author_display_name || comment.author_name || 'GOL supporter'}</div>
                                      <div className="mt-1 text-sm text-foreground/80 line-clamp-3">{comment.body}</div>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )
                          })()}
                        </>
                      )}
                    </CardContent >
                  </Card >
                )
              })}
              {
                !focusedViewActive && totalPages > 1 && (
                  <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
                    <span className="text-sm text-muted-foreground">
                      Page {currentPage} of {totalPages}
                      {pageStart > 0 && pageEnd >= pageStart ? ` • Showing ${pageStart}–${pageEnd} of ${filteredTotal}` : ''}
                    </span>
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setCurrentPage((page) => Math.max(1, page - 1))}
                        disabled={currentPage === 1}
                      >
                        Previous
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setCurrentPage((page) => Math.min(totalPages, page + 1))}
                        disabled={currentPage === totalPages}
                      >
                        Next
                      </Button>
                    </div>
                  </div>
                )
              }
            </div >
          )}
        </div>

        {/* Sponsor Sidebar - list view only, visible on larger screens.
            Detail view drops the sidebar entirely so the newsletter can
            use the full canvas — sponsor moves to a footer band below. */}
        {!focusedViewActive && (
          <SponsorSidebar className="hidden lg:block" />
        )}
      </div>

      {/* Sponsor Strip — full width below content. In list view this is
          mobile-only (sidebar handles desktop). In detail view it's the
          sole sponsor surface, shown at every width. */}
      <div className={focusedViewActive ? 'pb-6' : 'lg:hidden pb-6'}>
        <SponsorStrip />
      </div>
    </div >
  )
}

// Authenticated settings page
function SettingsPage() {
  const auth = useAuth()
  const { openLoginModal } = useAuthUI()

  const [displayNameInput, setDisplayNameInput] = useState(auth.displayName || '')
  const [displayNameStatus, setDisplayNameStatus] = useState(null)
  const [displayNameBusy, setDisplayNameBusy] = useState(false)

  // Email delivery preference state
  const [emailPreference, setEmailPreference] = useState('individual')
  const [emailPrefLoading, setEmailPrefLoading] = useState(false)
  const [emailPrefStatus, setEmailPrefStatus] = useState(null)

  // Journalist Profile State
  const [journalistProfile, setJournalistProfile] = useState({ bio: '', profile_image_url: '' })
  const [journalistSaving, setJournalistSaving] = useState(false)
  const [journalistStatus, setJournalistStatus] = useState(null)

  const [teams, setTeams] = useState([])
  const [selectedTeamIds, setSelectedTeamIds] = useState([])
  const [subscriptions, setSubscriptions] = useState([])
  const [loading, setLoading] = useState(true)
  const [initialError, setInitialError] = useState(null)
  const [message, setMessage] = useState(null)
  const [savingSubs, setSavingSubs] = useState(false)

  // Paid subscriptions and journalist follows state
  const [paidSubscriptions, setPaidSubscriptions] = useState([])
  const [journalistFollows, setJournalistFollows] = useState([])
  const [processingSubId, setProcessingSubId] = useState(null)

  useEffect(() => {
    setDisplayNameInput(auth.displayName || '')
  }, [auth.displayName])

  useEffect(() => {
    if (!auth.token) {
      setTeams([])
      setSelectedTeamIds([])
      setSubscriptions([])
      setLoading(false)
      return
    }

    let cancelled = false

    const load = async () => {
      setLoading(true)
      setInitialError(null)
      try {
        const promises = [
          APIService.getTeams({ is_active: 'true' }),
          APIService.getMySubscriptions(),
          APIService.getUserEmailPreferences().catch(() => ({ email_delivery_preference: 'individual' })),
          APIService.getAllSubscriptions().catch(() => ({ free_subscriptions: [], paid_subscriptions: [] })),
        ]

        if (auth.isJournalist) {
          promises.push(APIService.request('/writer/profile').catch(() => ({})))
        }

        const results = await Promise.all(promises)
        const teamData = results[0]
        const subscriptionData = results[1]
        const emailPrefData = results[2]
        const allSubsData = results[3]
        const writerData = results[4]

        if (cancelled) return

        const teamList = Array.isArray(teamData) ? teamData.slice() : []
        teamList.sort((a, b) => (a.name || '').localeCompare(b.name || ''))

        setTeams(teamList)
        const subs = Array.isArray(subscriptionData) ? subscriptionData : []
        setSubscriptions(subs)
        setSelectedTeamIds(subs.map((sub) => sub.team_id))
        setEmailPreference(emailPrefData?.email_delivery_preference || 'individual')
        setPaidSubscriptions(allSubsData?.paid_subscriptions || [])
        setJournalistFollows(allSubsData?.journalist_follows || [])

        if (writerData) {
          setJournalistProfile({
            bio: writerData.bio || '',
            profile_image_url: writerData.profile_image_url || '',
            attribution_url: writerData.attribution_url || '',
            attribution_name: writerData.attribution_name || ''
          })
        }
      } catch (error) {
        if (cancelled) return
        console.error('Failed to load account settings', error)
        setInitialError(error?.body?.error || error.message || 'Failed to load account settings.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [auth.token])

  const selectedTeamDetails = useMemo(() => {
    if (!selectedTeamIds.length) return []
    const teamMap = new Map(teams.map((team) => [team.id, team]))
    const subscriptionMap = new Map(
      subscriptions
        .filter((sub) => sub?.team)
        .map((sub) => [sub.team_id, sub.team])
    )
    return selectedTeamIds.map((id) => {
      const team = teamMap.get(id) || subscriptionMap.get(id) || {}
      return {
        id,
        name: team.name || `Team #${id}`,
        league: team.league_name || team.league || null,
        loans: team.tracked_player_count ?? team.current_loaned_out_count,
      }
    })
  }, [selectedTeamIds, subscriptions, teams])

  const handleEmailPreferenceChange = async (newPreference) => {
    if (!auth.token) return
    setEmailPrefLoading(true)
    setEmailPrefStatus(null)
    try {
      await APIService.updateUserEmailPreferences(newPreference)
      setEmailPreference(newPreference)
      setEmailPrefStatus({ type: 'success', message: 'Email preference updated.' })
    } catch (error) {
      console.error('Failed to update email preference', error)
      setEmailPrefStatus({ type: 'error', message: error?.message || 'Failed to update preference.' })
    } finally {
      setEmailPrefLoading(false)
    }
  }

  const handleCancelPaidSubscription = async (subscriptionId) => {
    if (!confirm('Are you sure you want to cancel this subscription? You will still have access until the end of your billing period.')) {
      return
    }
    setProcessingSubId(subscriptionId)
    setMessage(null)
    try {
      await APIService.request(`/stripe/cancel-subscription/${subscriptionId}`, { method: 'POST' })
      // Refresh paid subscriptions
      const allSubs = await APIService.getAllSubscriptions().catch(() => ({ paid_subscriptions: [] }))
      setPaidSubscriptions(allSubs?.paid_subscriptions || [])
      setMessage({ type: 'success', text: 'Subscription canceled. You will have access until the end of your billing period.' })
    } catch (error) {
      console.error('Failed to cancel subscription', error)
      setMessage({ type: 'error', text: error?.message || 'Failed to cancel subscription.' })
    } finally {
      setProcessingSubId(null)
    }
  }

  const handleReactivatePaidSubscription = async (subscriptionId) => {
    setProcessingSubId(subscriptionId)
    setMessage(null)
    try {
      await APIService.request(`/stripe/reactivate-subscription/${subscriptionId}`, { method: 'POST' })
      // Refresh paid subscriptions
      const allSubs = await APIService.getAllSubscriptions().catch(() => ({ paid_subscriptions: [] }))
      setPaidSubscriptions(allSubs?.paid_subscriptions || [])
      setMessage({ type: 'success', text: 'Subscription reactivated successfully!' })
    } catch (error) {
      console.error('Failed to reactivate subscription', error)
      setMessage({ type: 'error', text: error?.message || 'Failed to reactivate subscription.' })
    } finally {
      setProcessingSubId(null)
    }
  }

  const handleDisplayNameSave = async (event) => {
    event?.preventDefault?.()
    if (!auth.token) {
      setDisplayNameStatus({ type: 'error', message: 'Sign in to update your display name.' })
      return
    }
    const trimmed = (displayNameInput || '').trim()
    if (trimmed.length < 3) {
      setDisplayNameStatus({ type: 'error', message: 'Display name must be at least 3 characters.' })
      return
    }
    setDisplayNameStatus(null)
    setDisplayNameBusy(true)
    try {
      const res = await APIService.updateDisplayName(trimmed)
      setDisplayNameInput(res?.display_name || trimmed)
      setDisplayNameStatus({ type: 'success', message: 'Display name updated.' })
    } catch (error) {
      console.error('Failed to update display name', error)
      setDisplayNameStatus({ type: 'error', message: error?.body?.error || error.message || 'Unable to update display name.' })
    } finally {
      setDisplayNameBusy(false)
    }
  }

  const handleJournalistSave = async (e) => {
    e.preventDefault()
    if (!auth.token || !auth.isJournalist) return

    setJournalistStatus(null)
    setJournalistSaving(true)
    try {
      await APIService.request('/writer/profile', {
        method: 'POST',
        body: JSON.stringify(journalistProfile)
      })
      setJournalistStatus({ type: 'success', message: 'Profile updated successfully.' })
    } catch (error) {
      console.error('Failed to update profile', error)
      setJournalistStatus({ type: 'error', message: error?.message || 'Failed to update profile.' })
    } finally {
      setJournalistSaving(false)
    }
  }

  const handleSaveSubscriptions = async () => {
    if (!auth.token) {
      setMessage({ type: 'error', text: 'Sign in to manage subscriptions.' })
      return
    }
    setMessage(null)
    setSavingSubs(true)
    try {
      const res = await APIService.updateMySubscriptions({ team_ids: selectedTeamIds })
      const subs = Array.isArray(res?.subscriptions) ? res.subscriptions : []
      setSubscriptions(subs)
      setSelectedTeamIds(subs.map((sub) => sub.team_id))

      const parts = []
      if (res?.created_count) parts.push(`${res.created_count} joined`)
      if (res?.reactivated_count) parts.push(`${res.reactivated_count} reactivated`)
      if (res?.deactivated_count) parts.push(`${res.deactivated_count} paused`)
      const ignored = Array.isArray(res?.ignored_team_ids) ? res.ignored_team_ids.length : 0
      if (ignored) parts.push(`${ignored} ignored`)
      const suffix = parts.length ? ` (${parts.join(', ')})` : ''

      let text = `Subscription preferences saved${suffix}.`

      // Add waitlist notification if applicable
      const teamsWithoutNewsletters = res?.teams_without_newsletters || []
      if (teamsWithoutNewsletters.length > 0) {
        const teamNames = teamsWithoutNewsletters.map(t => t.team_name).join(', ')
        text += ` Note: ${teamNames} ${teamsWithoutNewsletters.length === 1 ? "doesn't have" : "don't have"} active newsletters yet. We'll notify you once we start generating them!`
      }

      setMessage({ type: 'success', text })
    } catch (error) {
      console.error('Failed to update subscriptions', error)
      setMessage({ type: 'error', text: error?.body?.error || error.message || 'Failed to update subscriptions.' })
    } finally {
      setSavingSubs(false)
    }
  }

  if (!auth.token) {
    return (
      <div className="max-w-3xl mx-auto py-12 sm:px-6 lg:px-8">
        <Card>
          <CardHeader>
            <CardTitle>Account Settings</CardTitle>
            <CardDescription>Sign in with the email you use for newsletters to manage your account.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4 text-sm text-muted-foreground">
              <p>To view your settings, please sign in using the one-time code flow.</p>
              <Button onClick={openLoginModal}>
                <LogIn className="mr-2 h-4 w-4" /> Sign in
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="max-w-4xl mx-auto py-8 sm:px-6 lg:px-8">
      <div className="px-4 sm:px-0">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-foreground mb-2">Account Settings</h1>
          <p className="text-lg text-muted-foreground">Update your profile and choose which teams send you newsletters.</p>
        </div>

        {message && (
          <Alert className={`mb-6 ${message.type === 'error' ? 'border-rose-500' : 'border-emerald-500'}`}>
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{message.text}</AlertDescription>
          </Alert>
        )}

        {initialError && (
          <Alert className="mb-6 border-rose-500">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{initialError}</AlertDescription>
          </Alert>
        )}

        {loading ? (
          <div className="text-center py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto"></div>
            <p className="mt-4 text-muted-foreground">Loading your preferences…</p>
          </div>
        ) : (
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Profile</CardTitle>
                <CardDescription>Control the display name shown with your comments and activity.</CardDescription>
              </CardHeader>
              <CardContent>
                <form className="space-y-3" onSubmit={handleDisplayNameSave}>
                  <div className="space-y-2">
                    <Label htmlFor="settings-display-name">Display name</Label>
                    <Input
                      id="settings-display-name"
                      value={displayNameInput}
                      onChange={(e) => setDisplayNameInput(e.target.value)}
                      maxLength={40}
                      placeholder="Your public name"
                    />
                    {displayNameStatus && (
                      <p className={`text-xs ${displayNameStatus.type === 'error' ? 'text-rose-600' : 'text-emerald-600'}`}>
                        {displayNameStatus.message}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <Button size="sm" type="submit" disabled={displayNameBusy}>
                      {displayNameBusy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Save display name
                    </Button>
                    <Button size="sm" variant="ghost" type="button" onClick={() => setDisplayNameInput(auth.displayName || '')}>
                      Reset
                    </Button>
                  </div>
                </form>
              </CardContent>
            </Card>

            {/* Email Delivery Preferences */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Mail className="h-5 w-5" />
                  Email Delivery
                </CardTitle>
                <CardDescription>Choose how you want to receive newsletters when subscribed to multiple teams.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-3">
                  <div
                    className={`flex items-start gap-3 p-4 rounded-lg border-2 cursor-pointer transition-colors ${emailPreference === 'individual'
                      ? 'border-primary bg-primary/5'
                      : 'border-border hover:border-border'
                      } ${emailPrefLoading ? 'opacity-50 pointer-events-none' : ''}`}
                    onClick={() => handleEmailPreferenceChange('individual')}
                  >
                    <div className={`mt-0.5 w-4 h-4 rounded-full border-2 flex items-center justify-center ${emailPreference === 'individual' ? 'border-primary' : 'border-border'
                      }`}>
                      {emailPreference === 'individual' && (
                        <div className="w-2 h-2 rounded-full bg-primary" />
                      )}
                    </div>
                    <div className="flex-1">
                      <div className="font-medium text-foreground">Individual emails</div>
                      <div className="text-sm text-muted-foreground">
                        Receive each newsletter as a separate email when it's published (typically once per week per team).
                      </div>
                    </div>
                  </div>

                  <div
                    className={`flex items-start gap-3 p-4 rounded-lg border-2 cursor-pointer transition-colors ${emailPreference === 'digest'
                      ? 'border-primary bg-primary/5'
                      : 'border-border hover:border-border'
                      } ${emailPrefLoading ? 'opacity-50 pointer-events-none' : ''}`}
                    onClick={() => handleEmailPreferenceChange('digest')}
                  >
                    <div className={`mt-0.5 w-4 h-4 rounded-full border-2 flex items-center justify-center ${emailPreference === 'digest' ? 'border-primary' : 'border-border'
                      }`}>
                      {emailPreference === 'digest' && (
                        <div className="w-2 h-2 rounded-full bg-primary" />
                      )}
                    </div>
                    <div className="flex-1">
                      <div className="font-medium text-foreground">Weekly digest</div>
                      <div className="text-sm text-muted-foreground">
                        Combine all your subscribed newsletters into one weekly email. Best if you follow multiple teams.
                      </div>
                    </div>
                  </div>
                </div>

                {emailPrefStatus && (
                  <p className={`text-sm ${emailPrefStatus.type === 'error' ? 'text-rose-600' : 'text-emerald-600'}`}>
                    {emailPrefStatus.message}
                  </p>
                )}

                {emailPrefLoading && (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Saving preference...
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Journalist Profile Settings */}
            {auth.isJournalist && (
              <Card>
                <CardHeader>
                  <CardTitle>Journalist Profile</CardTitle>
                  <CardDescription>Manage your public profile appearing on the Journalist page.</CardDescription>
                </CardHeader>
                <CardContent>
                  <form className="space-y-4" onSubmit={handleJournalistSave}>
                    <div className="space-y-2">
                      <Label htmlFor="journalist-bio">Bio</Label>
                      <Textarea
                        id="journalist-bio"
                        value={journalistProfile.bio}
                        onChange={(e) => setJournalistProfile(prev => ({ ...prev, bio: e.target.value }))}
                        placeholder="Tell subscribers about yourself..."
                        className="resize-none min-h-[100px]"
                      />
                      <p className="text-xs text-muted-foreground">Brief description of your background and coverage focus.</p>
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="journalist-image">Profile Image URL</Label>
                      <div className="flex gap-4 items-start">
                        <div className="flex-1 space-y-2">
                          <Input
                            id="journalist-image"
                            value={journalistProfile.profile_image_url}
                            onChange={(e) => setJournalistProfile(prev => ({ ...prev, profile_image_url: e.target.value }))}
                            placeholder="https://..."
                          />
                          <div className="text-xs text-muted-foreground space-y-1">
                            <p>Enter the URL of your profile picture.</p>
                            <p><strong>Tip:</strong> You can right-click your photo on LinkedIn or Twitter, select "Copy Image Link", and paste it here. Or upload to a free host like <a href="https://postimages.org/" target="_blank" rel="noopener noreferrer" className="underline hover:text-primary">PostImages</a>.</p>
                          </div>
                        </div>
                        <Avatar className="h-16 w-16 border-2 border-muted">
                          <AvatarImage src={journalistProfile.profile_image_url} />
                          <AvatarFallback>
                            {auth.displayName?.substring(0, 2).toUpperCase() || 'JP'}
                          </AvatarFallback>
                        </Avatar>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label htmlFor="attribution-name">Attribution Name (Optional)</Label>
                        <Input
                          id="attribution-name"
                          value={journalistProfile.attribution_name}
                          onChange={(e) => setJournalistProfile(prev => ({ ...prev, attribution_name: e.target.value }))}
                          placeholder="e.g. The Athletic"
                        />
                        <p className="text-xs text-muted-foreground">Name of the publication or site you want to link to.</p>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="attribution-url">Attribution URL (Optional)</Label>
                        <Input
                          id="attribution-url"
                          value={journalistProfile.attribution_url}
                          onChange={(e) => setJournalistProfile(prev => ({ ...prev, attribution_url: e.target.value }))}
                          placeholder="https://..."
                        />
                        <p className="text-xs text-muted-foreground">Link to your main site or author page.</p>
                      </div>
                    </div>

                    {journalistStatus && (
                      <Alert className={journalistStatus.type === 'error' ? 'border-rose-500 text-rose-600' : 'border-emerald-500 text-emerald-600'}>
                        <AlertDescription>{journalistStatus.message}</AlertDescription>
                      </Alert>
                    )}

                    <div className="flex justify-end">
                      <Button type="submit" disabled={journalistSaving}>
                        {journalistSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                        Save Profile
                      </Button>
                    </div>
                  </form>
                </CardContent>
              </Card>
            )}

            {/* Premium Journalist Subscriptions */}
            {paidSubscriptions.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <CreditCard className="h-5 w-5" />
                    Premium Subscriptions
                  </CardTitle>
                  <CardDescription>Manage your paid journalist subscriptions.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {paidSubscriptions.map((sub) => (
                    <div key={sub.id} className="border rounded-lg p-4 space-y-3">
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex items-center gap-3">
                          <Avatar className="h-12 w-12">
                            <AvatarImage src={sub.journalist_profile_image} />
                            <AvatarFallback>
                              {sub.journalist_name?.substring(0, 2).toUpperCase() || 'JN'}
                            </AvatarFallback>
                          </Avatar>
                          <div>
                            <div className="font-semibold">{sub.journalist_name || 'Unknown Journalist'}</div>
                            <div className="text-sm text-muted-foreground">{sub.journalist_email}</div>
                            {sub.assigned_teams && sub.assigned_teams.length > 0 && (
                              <div className="flex items-center gap-1 mt-1">
                                {sub.assigned_teams.slice(0, 3).map((team) => (
                                  <img key={team.id} src={team.logo} alt={team.name} className="w-4 h-4" title={team.name} />
                                ))}
                                {sub.assigned_teams.length > 3 && (
                                  <span className="text-xs text-muted-foreground/70">+{sub.assigned_teams.length - 3}</span>
                                )}
                              </div>
                            )}
                          </div>
                        </div>
                        <Badge
                          variant="outline"
                          className={sub.cancel_at_period_end
                            ? 'bg-amber-50 text-amber-700 border-amber-200'
                            : sub.status === 'active'
                              ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                              : 'bg-secondary'
                          }
                        >
                          {sub.cancel_at_period_end ? 'Canceling' : sub.status}
                        </Badge>
                      </div>

                      {sub.current_period_end && (
                        <div className="text-sm text-muted-foreground">
                          <Calendar className="h-4 w-4 inline mr-1" />
                          {sub.cancel_at_period_end ? 'Ends' : 'Renews'}: {new Date(sub.current_period_end).toLocaleDateString()}
                        </div>
                      )}

                      {sub.cancel_at_period_end && (
                        <Alert className="bg-amber-50 border-amber-200">
                          <AlertDescription className="text-amber-800">
                            This subscription will end on {new Date(sub.current_period_end).toLocaleDateString()}.
                            You can reactivate it anytime before then.
                          </AlertDescription>
                        </Alert>
                      )}

                      <div className="flex gap-2">
                        {sub.status === 'active' && !sub.cancel_at_period_end && (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleCancelPaidSubscription(sub.id)}
                            disabled={processingSubId === sub.id}
                          >
                            {processingSubId === sub.id ? (
                              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            ) : (
                              <XCircle className="mr-2 h-4 w-4" />
                            )}
                            Cancel Subscription
                          </Button>
                        )}
                        {sub.cancel_at_period_end && (
                          <Button
                            size="sm"
                            onClick={() => handleReactivatePaidSubscription(sub.id)}
                            disabled={processingSubId === sub.id}
                          >
                            {processingSubId === sub.id ? (
                              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            ) : (
                              <RotateCcw className="mr-2 h-4 w-4" />
                            )}
                            Reactivate
                          </Button>
                        )}
                      </div>
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}

            {/* Journalists You Follow (free) */}
            {journalistFollows.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <UserPlus className="h-5 w-5" />
                    Journalists You Follow
                  </CardTitle>
                  <CardDescription>Writers whose free content and updates you receive.</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {journalistFollows.map((follow) => (
                      <Link
                        key={follow.id}
                        to={`/journalists/${follow.journalist_id}`}
                        className="flex items-center gap-3 p-3 border rounded-lg bg-secondary hover:bg-secondary hover:border-border transition-colors group"
                      >
                        <Avatar className="h-10 w-10">
                          <AvatarImage src={follow.journalist_profile_image} />
                          <AvatarFallback>
                            {follow.journalist_name?.substring(0, 2).toUpperCase() || 'JN'}
                          </AvatarFallback>
                        </Avatar>
                        <div className="flex-1 min-w-0">
                          <div className="font-medium text-foreground truncate group-hover:text-primary transition-colors">{follow.journalist_name || 'Unknown'}</div>
                          {follow.assigned_teams && follow.assigned_teams.length > 0 && (
                            <div className="flex items-center gap-1 mt-0.5">
                              {follow.assigned_teams.slice(0, 3).map((team) => (
                                <img key={team.id} src={team.logo} alt={team.name} className="w-4 h-4" title={team.name} />
                              ))}
                              {follow.assigned_teams.length > 3 && (
                                <span className="text-xs text-muted-foreground/70">+{follow.assigned_teams.length - 3}</span>
                              )}
                            </div>
                          )}
                        </div>
                        <div className="flex items-center gap-2">
                          <Badge variant="outline" className="bg-primary/5 text-primary border-primary/20">Following</Badge>
                          <ChevronRight className="h-4 w-4 text-muted-foreground/70 group-hover:text-primary transition-colors" />
                        </div>
                      </Link>
                    ))}
                  </div>
                  <p className="text-xs text-muted-foreground mt-3">
                    Click on a journalist to view their profile or unfollow.
                  </p>
                </CardContent>
              </Card>
            )}

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Users className="h-5 w-5" />
                  Team Newsletter Subscriptions
                </CardTitle>
                <CardDescription>Select the teams you want weekly updates for (free).</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <TeamMultiSelect
                  teams={teams}
                  value={selectedTeamIds}
                  onChange={(ids) => setSelectedTeamIds(ids.map((id) => Number(id)))}
                  placeholder="Choose teams to follow…"
                />

                <div className="rounded-md border border-dashed bg-muted/40 p-4 text-sm text-foreground/80">
                  {selectedTeamDetails.length === 0 ? (
                    <p>You are not subscribed to any team newsletters. Select teams above to start receiving updates.</p>
                  ) : (
                    <div className="space-y-2">
                      <p className="font-medium text-foreground">You will receive newsletters for:</p>
                      <ul className="space-y-2">
                        {selectedTeamDetails.map((team) => (
                          <li key={team.id} className="flex flex-col sm:flex-row sm:items-center sm:justify-between rounded border border-transparent bg-card/60 px-3 py-2">
                            <div>
                              <div className="font-semibold text-foreground">{team.name}</div>
                              <div className="text-xs text-muted-foreground">
                                {[team.league, team.loans != null ? `${team.loans} players tracked` : null]
                                  .filter(Boolean)
                                  .join(' · ')}
                              </div>
                            </div>
                            <Button
                              size="sm"
                              variant="ghost"
                              className="mt-2 sm:mt-0"
                              onClick={() => setSelectedTeamIds((prev) => prev.filter((id) => id !== team.id))}
                            >
                              <X className="mr-1 h-4 w-4" /> Remove
                            </Button>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </CardContent>
              <CardFooter className="flex justify-end">
                <Button onClick={handleSaveSubscriptions} disabled={savingSubs}>
                  {savingSubs && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Save newsletter preferences
                </Button>
              </CardFooter>
            </Card>
          </div>
        )}
      </div>
    </div>
  )
}

// Manage subscriptions page
function ManagePage() {
  const [status, setStatus] = useState('loading') // loading | ready | error
  const [subs, setSubs] = useState([])
  const [message, setMessage] = useState(null)

  const token = new URLSearchParams(window.location.search).get('token')

  useEffect(() => {
    const load = async () => {
      if (!token) {
        setStatus('error')
        setMessage({ type: 'error', text: 'Missing token' })
        return
      }
      try {
        const data = await APIService.getManageState(token)
        setSubs(data.subscriptions || [])
        setStatus('ready')
      } catch (error) {
        console.error('Failed to load manage state', error)
        setStatus('error')
        setMessage({ type: 'error', text: 'Invalid or expired link. Request a new manage link from your email.' })
      }
    }
    load()
  }, [token])

  const toggleTeam = (teamId) => {
    setSubs((prev) => {
      const exists = prev.some((s) => s.team_id === teamId)
      if (exists) {
        return prev.filter((s) => s.team_id !== teamId)
      }
      return [...prev, { team_id: teamId }]
    })
  }

  const save = async () => {
    try {
      const teamIds = subs.map((s) => s.team_id)
      await APIService.updateManageState(token, { team_ids: teamIds })
      setMessage({ type: 'success', text: 'Preferences updated.' })
    } catch (error) {
      console.error('Failed to update preferences', error)
      setMessage({ type: 'error', text: 'Failed to update preferences.' })
    }
  }

  return (
    <div className="max-w-4xl mx-auto py-6 sm:px-6 lg:px-8">
      <div className="px-4 py-6 sm:px-0">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-foreground mb-4">Manage Subscriptions</h1>
          <p className="text-lg text-muted-foreground">Use the secure link from your email to manage preferences.</p>
        </div>

        {message && (
          <Alert className={`mb-6 ${message.type === 'error' ? 'border-rose-500' : 'border-emerald-500'}`}>
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{message.text}</AlertDescription>
          </Alert>
        )}

        {status === 'loading' && (
          <div className="text-center py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto"></div>
            <p className="mt-4 text-muted-foreground">Loading…</p>
          </div>
        )}

        {status === 'ready' && (
          <Card>
            <CardHeader>
              <CardTitle>Update Preferences</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label>Subscribed Teams</Label>
                <p className="text-sm text-muted-foreground mb-2">Toggle teams to stay subscribed. (Team list display simplified.)</p>
                <div className="grid grid-cols-1 gap-2">
                  {subs.map((s) => (
                    <div key={s.team_id} className="flex items-center justify-between border rounded p-2">
                      <span className="text-sm">Team #{s.team_id}</span>
                      <Button size="sm" variant="outline" onClick={() => toggleTeam(s.team_id)}>Remove</Button>
                    </div>
                  ))}
                </div>
              </div>

              <div className="flex justify-end">
                <Button onClick={save}>
                  Save Changes
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {status === 'error' && (
          <div className="text-center py-12">
            <p className="text-muted-foreground">Your link is invalid or expired.</p>
          </div>
        )}
      </div>
    </div>
  )
}

function UnsubscribePage() {
  const [message, setMessage] = useState(null)
  const token = new URLSearchParams(window.location.search).get('token')

  useEffect(() => {
    const run = async () => {
      if (!token) {
        setMessage({ type: 'error', text: 'Missing token' })
        return
      }
      try {
        await APIService.tokenUnsubscribe(token)
        setMessage({ type: 'success', text: 'You have been unsubscribed.' })
      } catch (error) {
        console.error('Failed to unsubscribe', error)
        setMessage({ type: 'error', text: 'Invalid or expired unsubscribe link.' })
      }
    }
    run()
  }, [token])

  return (
    <div className="max-w-xl mx-auto py-20 text-center">
      {message && (
        <Alert className={`inline-block ${message.type === 'error' ? 'border-rose-500' : 'border-emerald-500'}`}>
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{message.text}</AlertDescription>
        </Alert>
      )}
    </div>
  )
}

function VerifyPage() {
  const [message, setMessage] = useState(null)
  const token = new URLSearchParams(window.location.search).get('token')

  useEffect(() => {
    const run = async () => {
      if (!token) {
        setMessage({ type: 'error', text: 'Missing token' })
        return
      }
      try {
        const res = await APIService.verifyToken(token)
        if (res?.created_count !== undefined || res?.updated_count !== undefined) {
          const created = res.created_count ?? 0
          const updated = res.updated_count ?? 0
          const parts = []
          if (created) parts.push(`${created} new`)
          if (updated) parts.push(`${updated} updated`)
          const summary = parts.length ? ` (${parts.join(', ')})` : ''
          setMessage({
            type: 'success',
            text: `Subscriptions confirmed for ${res.email || 'your email'}${summary}.`,
          })
        } else {
          setMessage({ type: 'success', text: res?.message || 'Email verified. Thank you!' })
        }
      } catch (error) {
        console.error('Failed to verify email token', error)
        const detail = error?.body?.error || error.message || 'Invalid or expired verification link.'
        setMessage({ type: 'error', text: detail })
      }
    }
    run()
  }, [token])

  return (
    <div className="max-w-xl mx-auto py-20 text-center">
      {message && (
        <Alert className={`inline-block ${message.type === 'error' ? 'border-rose-500' : 'border-emerald-500'}`}>
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{message.text}</AlertDescription>
        </Alert>
      )}
    </div>
  )
}

// Statistics page
function StatsPage() {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)

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
    <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
      <div className="px-4 py-6 sm:px-0">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-foreground mb-4">
            System Statistics
          </h1>
          <p className="text-lg text-muted-foreground">
            Overview of the The Academy Watch platform
          </p>
        </div>

        {loading ? (
          <div className="text-center py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto"></div>
            <p className="mt-4 text-muted-foreground">Loading statistics...</p>
          </div>
        ) : stats ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Clubs Tracked</CardTitle>
                <Users className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{stats.teams_with_loans}</div>
                <p className="text-xs text-muted-foreground">
                  Academies currently tracked
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Teams in Database</CardTitle>
                <TrendingUp className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{stats.total_teams}</div>
                <p className="text-xs text-muted-foreground">
                  Unique clubs tracked
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Tracked Players</CardTitle>
                <Globe className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{stats.total_active_loans}</div>
                <p className="text-xs text-muted-foreground">
                  Academy prospects tracked
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Published Newsletters</CardTitle>
                <FileText className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{stats.total_newsletters}</div>
                <p className="text-xs text-muted-foreground">
                  AI-generated reports
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Active Subscriptions</CardTitle>
                <Mail className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{stats.total_subscriptions}</div>
                <p className="text-xs text-muted-foreground">
                  Newsletter subscribers
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">European Leagues</CardTitle>
                <Trophy className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{stats.european_leagues}</div>
                <p className="text-xs text-muted-foreground">
                  Top leagues covered
                </p>
              </CardContent>
            </Card>
          </div>
        ) : (
          <div className="text-center py-12">
            <Alert className="max-w-md mx-auto">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>
                Failed to load statistics. Please try again later.
              </AlertDescription>
            </Alert>
          </div>
        )}
      </div>
    </div>
  )
}

// Inner app component with Router context (for useNavigate in GlobalSearchDialog)
function AppWithRouter() {
  const globalSearch = useGlobalSearch()

  return (
    <GlobalSearchContext.Provider value={globalSearch}>
      <div className="min-h-screen bg-secondary">
        <Navigation />
        <SyncBanner />
        <GlobalSearchDialog
          open={globalSearch.isOpen}
          onOpenChange={globalSearch.setIsOpen}
          recentSearches={globalSearch.recentSearches}
          onSelect={globalSearch.addRecentSearch}
          onClearRecent={globalSearch.clearRecentSearches}
        />
        <main>
          <AppRoutes />
        </main>
        <footer className="bg-secondary border-t border-border py-8 mt-auto">
          <div className="max-w-6xl mx-auto px-4 text-center">
            <BuyMeCoffeeButton />
            <p className="text-sm text-muted-foreground mt-4">&copy; {new Date().getFullYear()} The Academy Watch. All rights reserved.</p>
          </div>
        </footer>
        <LoginModal />
      </div>
    </GlobalSearchContext.Provider>
  )
}

// App routes extracted for cleaner structure
function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/teams" element={<TeamsPage />} />
      <Route path="/teams/:teamSlug" element={<TeamDetailPage />} />
      <Route path="/dream-team" element={<PublicFormationBuilder />} />
      <Route path="/newsletters" element={<NewslettersPage />} />
      <Route path="/newsletters/:newsletterId" element={<NewslettersPage />} />
      <Route path="/newsletters/historical" element={<HistoricalNewslettersPage />} />
      <Route path="/writeups/:commentaryId" element={<WriteupPage />} />
      <Route path="/players/:playerId" element={<PlayerPage />} />
      <Route path="/journalists" element={<JournalistList apiService={APIService} />} />
      <Route
        path="/settings"
        element={(
          <RequireAuth>
            <SettingsPage />
          </RequireAuth>
        )}
      />
      {/* Hidden in nav, used only via email links */}
      <Route path="/manage" element={<ManagePage />} />
      <Route path="/unsubscribe" element={<UnsubscribePage />} />
      <Route path="/verify" element={<VerifyPage />} />
      <Route path="/claim-account" element={<ClaimAccount />} />
      <Route path="/submit-take" element={<SubmitTake />} />
      <Route path="/flag" element={<FlagData />} />
      <Route path="/scout" element={<ScoutPage />} />
      <Route path="/scout/watchlist" element={<WatchlistPage />} />
      <Route path="/pricing" element={<PricingPage />} />
      <Route path="/academy" element={<CohortBrowser />} />
      <Route path="/academy/cohorts/:cohortId" element={<CohortDetail />} />
      <Route path="/academy/analytics" element={<CohortAnalytics />} />
      <Route path="/admin" element={<AdminLayout />}>
        <Route index element={<Navigate to="/admin/dashboard" replace />} />
        <Route path="dashboard" element={<AdminDashboard />} />
        <Route path="inbox" element={<AdminInbox />} />
        <Route path="operations" element={<AdminOperations />} />
        <Route path="seeding" element={<AdminSeeding />} />
        <Route path="newsletters" element={<AdminNewsletters />} />
        <Route path="newsletters/:newsletterId" element={<AdminNewsletterDetail />} />
        <Route path="users" element={<AdminUsers />} />
        <Route path="players" element={<AdminPlayers />} />
        <Route path="teams" element={<AdminTeams />} />
        <Route path="teams/:teamId/formation" element={<AdminFormation />} />
        <Route path="sponsors" element={<AdminSponsors />} />
        <Route path="curation" element={<Navigate to="/admin/inbox?tab=takes" replace />} />
        <Route path="flags" element={<Navigate to="/admin/inbox?tab=flags" replace />} />
        <Route path="academy" element={<AdminAcademy />} />
        <Route path="cohorts" element={<AdminCohorts />} />
        <Route path="video" element={<AdminVideo />} />
        <Route path="video/:matchId" element={<AdminVideoMatch />} />
        <Route path="settings" element={<AdminSettings />} />
        <Route path="tools" element={<AdminTools />} />
        <Route path="sandbox" element={<AdminSandbox />} />
        {/* Catch-all for dead /admin/* paths (e.g. the deleted /admin/old):
            a sibling top-level path="*" cannot match nested unmatched admin
            routes, so without this the parent renders an empty <Outlet/>. */}
        <Route path="*" element={<Navigate to="/admin/dashboard" replace />} />
      </Route>
      <Route path="/journalists/:id" element={<JournalistProfile />} />
      <Route path="/newsletters/:newsletterId/writer/:journalistId" element={<JournalistNewsletterView />} />

      {/* Writer Portal Routes */}
      <Route path="/writer/login" element={<WriterLogin />} />
      <Route
        path="/writer/dashboard"
        element={
          <RequireAuth>
            <WriterDashboard />
          </RequireAuth>
        }
      />
      <Route
        path="/writer/writeup-editor"
        element={
          <RequireAuth>
            <WriteupEditor />
          </RequireAuth>
        }
      />
      <Route
        path="/writer/editor/:id"
        element={(
          <RequireAuth requireJournalist>
            <WriteupEditor />
          </RequireAuth>
        )}
      />
      <Route
        path="/writer/contributors"
        element={
          <RequireAuth>
            <ContributorManager />
          </RequireAuth>
        }
      />

      {/* Curator Routes */}
      <Route
        path="/curator/dashboard"
        element={
          <RequireAuth>
            <CuratorDashboard />
          </RequireAuth>
        }
      />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

// Login modal component extracted
function LoginModal() {
  const { isLoginModalOpen, closeLoginModal } = useAuthUI()
  return (
    <AuthModal
      open={isLoginModalOpen}
      onOpenChange={(open) => { if (!open) closeLoginModal() }}
    />
  )
}

// Main App component
function App() {
  const [authSnapshot, setAuthSnapshot] = useState(() => buildAuthSnapshot())
  const [loginModalOpen, setLoginModalOpen] = useState(false)

  const syncAuth = useCallback((detail = {}) => {
    setAuthSnapshot(buildAuthSnapshot(detail))
  }, [])

  useEffect(() => {
    if (typeof window === 'undefined') return undefined
    const handleAuthChange = (event) => {
      const detail = (event && event.detail) || {}
      syncAuth(detail)
    }
    handleAuthChange()
    window.addEventListener(APIService.authEventName, handleAuthChange)
    window.addEventListener('storage', handleAuthChange)
    return () => {
      window.removeEventListener(APIService.authEventName, handleAuthChange)
      window.removeEventListener('storage', handleAuthChange)
    }
  }, [syncAuth])

  useEffect(() => {
    if (!authSnapshot.token) return
    APIService.refreshProfile().catch(() => { })
  }, [authSnapshot.token])

  const openLoginModal = useCallback(() => setLoginModalOpen(true), [])
  const closeLoginModal = useCallback(() => setLoginModalOpen(false), [])
  const handleLogout = useCallback(({ clearAdminKey = false } = {}) => {
    APIService.logout({ clearAdminKey })
    setLoginModalOpen(false)
    syncAuth({ token: null, displayName: null, displayNameConfirmed: false })
  }, [syncAuth])

  return (
    <AuthContext.Provider value={authSnapshot}>
      <AuthUIContext.Provider value={{
        openLoginModal,
        closeLoginModal,
        logout: handleLogout,
        isLoginModalOpen: loginModalOpen,
      }}>
        <Router>
          <AppWithRouter />
          <GolPanel />
        </Router>
      </AuthUIContext.Provider>
    </AuthContext.Provider>
  )
}

export default App
