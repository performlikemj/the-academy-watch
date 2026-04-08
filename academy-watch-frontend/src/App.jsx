import { useState, useEffect, useMemo, useCallback, useRef, Fragment } from 'react'
import { BrowserRouter as Router, Routes, Route, Link, Navigate, useLocation, useParams, useNavigate, useSearchParams } from 'react-router-dom'
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
  normalizeNewsletterIds,
  parseNewsletterId,
  formatSendPreviewSummary,
  formatDeleteSummary,
  resolveBulkActionPayload,
  formatBulkSelectionToast,
  computeReviewProgress,
  getReviewModalSizing,
} from '@/lib/newsletter-admin.js'
import { getAdminQuickLinks } from '@/lib/admin-quick-links.js'
import {
  buildSelectUpdates,
  mergeCollapseState,
  toggleCollapseState,
  sandboxCardHeaderClasses,
  sofascoreRowKey,
  buildSofascoreUpdatePayload,
} from '@/lib/admin-sandbox.js'
import { resolveAdminTab, getAdminTabs } from '@/lib/admin-tabs.js'
import { buildPlayerNameUpdatePayload } from '@/lib/admin-players.js'
import { buildSofascoreEmbedUrl } from '@/lib/sofascore.js'
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
import { AdminLayout } from '@/components/layouts/AdminLayout'
import { SponsorSidebar, SponsorStrip } from '@/components/SponsorSidebar'
import { AdminDashboard } from '@/pages/admin/AdminDashboard'
import { AdminNewsletters } from '@/pages/admin/AdminNewsletters'
import { AdminPlayers } from '@/pages/admin/AdminPlayers'
import { AdminSettings } from '@/pages/admin/AdminSettings'
import { AdminUsers } from '@/pages/admin/AdminUsers'
import { AdminTeams } from '@/pages/admin/AdminTeams'
import { AdminSponsors } from '@/pages/admin/AdminSponsors'
import { AdminCuration } from '@/pages/admin/AdminCuration'
import { AdminFlags } from '@/pages/admin/AdminFlags'
import { AdminAcademy } from '@/pages/admin/AdminAcademy'
import { AdminCohorts } from '@/pages/admin/AdminCohorts'
import { AdminTools } from '@/pages/admin/AdminTools'
import { AdminSandbox } from '@/pages/admin/AdminSandbox'
import { AdminFormation } from '@/pages/admin/AdminFormation'
import { HomePage } from '@/pages/HomePage'
import { PublicFormationBuilder } from '@/pages/PublicFormationBuilder'
import { CohortBrowser } from '@/pages/CohortBrowser'
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
const ADMIN_NEWSLETTER_PAGE_SIZE = 10

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

function AdminNewsletterDetailPage() {
  const { newsletterId } = useParams()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [newsletter, setNewsletter] = useState(null)
  const [error, setError] = useState('')
  const [renderHtml, setRenderHtml] = useState('')
  const [htmlError, setHtmlError] = useState('')
  const [copyLabel, setCopyLabel] = useState('Copy ID')

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      const trimmedId = (newsletterId || '').trim()
      if (!trimmedId) {
        setError('Newsletter id is required')
        setLoading(false)
        return
      }

      setLoading(true)
      setError('')
      setHtmlError('')
      try {
        const data = await APIService.adminNewsletterGet(trimmedId)
        if (cancelled) return
        setNewsletter(data)
        try {
          const html = await APIService.adminNewsletterRender(trimmedId, 'web')
          if (!cancelled) {
            setRenderHtml(html)
          }
        } catch (renderErr) {
          if (!cancelled) {
            setHtmlError(renderErr?.message || 'Unable to load rendered preview')
          }
        }
      } catch (err) {
        if (!cancelled) {
          setError(err?.message || 'Failed to load newsletter')
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [newsletterId])

  const handleCopyId = useCallback(() => {
    if (!newsletter?.id) return
    const idStr = String(newsletter.id)
    if (navigator?.clipboard?.writeText) {
      navigator.clipboard.writeText(idStr)
        .then(() => {
          setCopyLabel('Copied!')
          setTimeout(() => setCopyLabel('Copy ID'), 2000)
        })
        .catch(() => setCopyLabel('Copy ID'))
    }
  }, [newsletter?.id])

  const handleOpenPreview = useCallback(() => {
    if (!renderHtml) return
    const blob = new Blob([renderHtml], { type: 'text/html' })
    const url = URL.createObjectURL(blob)
    window.open(url, '_blank', 'noopener')
    setTimeout(() => URL.revokeObjectURL(url), 60_000)
  }, [renderHtml])

  const fallbackContent = useMemo(() => {
    let obj = null
    if (newsletter?.enriched_content && typeof newsletter.enriched_content === 'object') {
      obj = newsletter.enriched_content
    } else if (newsletter?.content) {
      try {
        obj = typeof newsletter.content === 'string' ? JSON.parse(newsletter.content) : (newsletter.content || {})
      } catch {
        obj = null
      }
    }

    if (!obj || typeof obj !== 'object') {
      return null
    }

    try {
      const highlights = Array.isArray(obj.highlights) ? obj.highlights : []
      const sections = Array.isArray(obj.sections) ? obj.sections : []
      return (
        <div className="space-y-6">
          <div className="bg-gradient-to-r from-secondary to-background p-6 rounded-lg border-l-4 border-primary/20">
            <h2 className="text-2xl font-bold text-foreground mb-3">{obj.title || newsletter.title}</h2>
            {obj.range && (
              <div className="text-sm text-muted-foreground mb-3">
                📅 Week: {obj.range[0]} - {obj.range[1]}
              </div>
            )}
            {obj.summary && (
              <div className="text-foreground/80 leading-relaxed text-lg">
                {obj.summary}
              </div>
            )}
          </div>

          {highlights.length > 0 && (
            <div className="bg-amber-50 p-5 rounded-lg border-l-4 border-amber-400">
              <h3 className="text-lg font-bold text-foreground mb-3 flex items-center">
                ⭐ Key Highlights
              </h3>
              <ul className="space-y-2">
                {highlights.map((highlight, idx) => (
                  <li key={idx} className="flex items-start">
                    <span className="bg-amber-400 text-amber-900 rounded-full w-6 h-6 flex items-center justify-center text-xs font-bold mr-3 mt-0.5 flex-shrink-0">
                      {idx + 1}
                    </span>
                    <span className="text-foreground/80">{highlight}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {sections.map((section, index) => {
            const items = Array.isArray(section?.items) ? section.items : []
            if (!items.length) return null
            return (
              <div key={index} className="space-y-4">
                {section?.title && (
                  <div className="border-b pb-2">
                    <h3 className="text-xl font-semibold text-foreground">{section.title}</h3>
                    {section?.subtitle && (
                      <p className="text-sm text-muted-foreground">{section.subtitle}</p>
                    )}
                  </div>
                )}
                <div className="space-y-4">
                  {items.map((item, itemIdx) => (
                    <div key={itemIdx} className="border rounded-lg p-4 bg-card shadow-sm">
                      <div className="flex items-start gap-3">
                        {/* Player Photo */}
                        {item.player_photo && (
                          <img
                            src={item.player_photo}
                            alt={item.player_name}
                            className="w-14 h-14 rounded-full object-cover bg-secondary flex-shrink-0 border-2 border-white shadow-sm"
                          />
                        )}
                        <div className="flex-1">
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div>
                              {(item.player_api_id || item.player_id) ? (
                                <Link
                                  to={`/players/${item.player_api_id || item.player_id}`}
                                  className="text-lg font-semibold text-foreground hover:text-primary hover:underline transition-colors"
                                >
                                  {item.player_name}
                                </Link>
                              ) : (
                                <div className="text-lg font-semibold text-foreground">{item.player_name}</div>
                              )}
                              {/* Loan Team with Logo */}
                              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                {item.loan_team_logo && (
                                  <img
                                    src={item.loan_team_logo}
                                    alt={item.loan_team || item.loan_team_name}
                                    className="w-5 h-5 rounded-full object-cover bg-secondary"
                                  />
                                )}
                                <span>{item.loan_team || item.loan_team_name}</span>
                              </div>
                            </div>
                            <div className="text-sm text-muted-foreground">
                              {item.competition || item.match_name}
                            </div>
                          </div>
                        </div>
                      </div>
                      {item.week_summary && (
                        <p className="mt-3 text-foreground/80 leading-relaxed">{item.week_summary}</p>
                      )}
                      {/* This Week's Matches with Opponent Logos */}
                      {item.matches && Array.isArray(item.matches) && item.matches.length > 0 && (
                        <div className="mt-3 p-3 bg-secondary rounded-lg border border-border">
                          <h5 className="text-sm font-semibold text-foreground/80 mb-2">⚽ This Week's Matches</h5>
                          <div className="space-y-2">
                            {item.matches.map((match, mIdx) => (
                              <div key={mIdx} className="flex items-center gap-3 p-2 bg-card rounded border border-border">
                                {match.opponent_logo && (
                                  <img
                                    src={match.opponent_logo}
                                    alt={match.opponent}
                                    className="w-7 h-7 rounded-full object-cover bg-secondary flex-shrink-0"
                                  />
                                )}
                                <div className="flex-1">
                                  <span className="font-medium text-sm">{match.home ? 'vs' : '@'} {match.opponent}</span>
                                  {match.competition && <span className="text-xs text-muted-foreground ml-2">({match.competition})</span>}
                                </div>
                                {match.score && (
                                  <span className={`px-2 py-1 rounded text-xs font-bold ${match.result === 'W' ? 'bg-emerald-50 text-emerald-800' :
                                    match.result === 'D' ? 'bg-secondary text-foreground/80' :
                                      'bg-rose-50 text-rose-800'
                                    }`}>
                                    {match.score.home ?? 0}-{match.score.away ?? 0}
                                  </span>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                      {item.match_notes && Array.isArray(item.match_notes) && item.match_notes.length > 0 && !item.matches && (
                        <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                          {item.match_notes.map((note, noteIndex) => (
                            <li key={noteIndex}>{note}</li>
                          ))}
                        </ul>
                      )}
                      {(() => {
                        const embedUrl = buildSofascoreEmbedUrl(item.sofascore_player_id ?? item.sofascoreId)
                        if (!embedUrl) return null
                        return (
                          <div className="mt-4">
                            <iframe
                              title={`Sofascore profile for ${item.player_name || item.player_id}`}
                              src={embedUrl}
                              frameBorder="0"
                              scrolling="no"
                              className="h-[568px] w-full max-w-xs rounded-md border"
                            />
                            <p className="mt-2 text-xs text-muted-foreground">
                              Player stats provided by{' '}
                              <a
                                href="https://sofascore.com/"
                                className="text-primary hover:underline"
                                target="_blank"
                                rel="noopener"
                              >
                                Sofascore
                              </a>
                            </p>
                          </div>
                        )
                      })()}
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      )
    } catch {
      return (
        <div className="bg-secondary p-4 rounded-lg">
          <h3 className="text-lg font-medium text-foreground mb-2">Newsletter Content</h3>
          <div className="whitespace-pre-wrap text-foreground/80">{newsletter.content}</div>
        </div>
      )
    }
  }, [newsletter])

  const metaEntries = useMemo(() => {
    if (!newsletter) return []
    const items = []
    items.push({ label: 'Newsletter ID', value: newsletter.id })
    if (newsletter.team_name) items.push({ label: 'Team', value: newsletter.team_name })
    if (newsletter.week_start_date || newsletter.week_end_date) {
      const range = [newsletter.week_start_date, newsletter.week_end_date].filter(Boolean).join(' → ')
      items.push({ label: 'Week', value: range })
    }
    if (newsletter.issue_date) items.push({ label: 'Issue Date', value: newsletter.issue_date })
    if (newsletter.published_date) items.push({ label: 'Published', value: newsletter.published_date })
    if (newsletter.generated_date) items.push({ label: 'Generated', value: newsletter.generated_date })
    if (newsletter.email_sent_date) items.push({ label: 'Email Sent', value: newsletter.email_sent_date })
    if (typeof newsletter.subscriber_count === 'number') {
      items.push({ label: 'Subscriber Count', value: newsletter.subscriber_count })
    }
    return items
  }, [newsletter])

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-6">
      <Button variant="ghost" size="sm" onClick={() => navigate(-1)}>
        <ArrowLeft className="mr-2 h-4 w-4" />
        Back
      </Button>

      {loading ? (
        <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
          <Loader2 className="h-10 w-10 animate-spin mb-4" />
          Loading newsletter…
        </div>
      ) : error ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg text-rose-600">Unable to load newsletter</CardTitle>
            <CardDescription>{error}</CardDescription>
          </CardHeader>
          <CardFooter>
            <Button variant="outline" onClick={() => navigate('/admin')}>
              Return to admin dashboard
            </Button>
          </CardFooter>
        </Card>
      ) : (
        <div className="space-y-6">
          <Card>
            <CardHeader className="flex flex-col gap-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <CardTitle className="text-2xl">{newsletter?.title || 'Newsletter detail'}</CardTitle>
                  <CardDescription className="text-sm text-muted-foreground">
                    Review the generated newsletter and metadata before sending.
                  </CardDescription>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={newsletter?.published ? 'default' : 'secondary'}>
                    {newsletter?.published ? 'Published' : 'Draft'}
                  </Badge>
                  {newsletter?.email_sent && (
                    <Badge variant="outline" className="border-emerald-200 text-emerald-700">
                      Email sent
                    </Badge>
                  )}
                  <Button size="sm" variant="outline" onClick={handleCopyId}>
                    <Copy className="mr-2 h-4 w-4" />
                    {copyLabel}
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-6">
              {metaEntries.length > 0 && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                  {metaEntries.map((item) => (
                    <div key={item.label} className="flex flex-col rounded border bg-secondary p-3">
                      <span className="text-xs uppercase tracking-wide text-muted-foreground">{item.label}</span>
                      <span className="text-foreground font-medium break-words">{item.value || '—'}</span>
                    </div>
                  ))}
                </div>
              )}

              <div className="flex flex-wrap gap-3">
                <Button size="sm" disabled={!renderHtml} onClick={handleOpenPreview}>
                  Open web preview
                </Button>
                {htmlError && (
                  <span className="text-sm text-rose-600">{htmlError}</span>
                )}
              </div>

              <div className="rounded-lg border bg-card p-6">
                {renderHtml ? (
                  <div dangerouslySetInnerHTML={{ __html: renderHtml }} className="prose max-w-none" />
                ) : fallbackContent ? (
                  fallbackContent
                ) : (
                  <div className="text-sm text-muted-foreground">No content available for this newsletter.</div>
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}

function RequireAdmin({ children }) {
  const { token, isAdmin, hasApiKey } = useAuth()
  if (!token || !isAdmin || !hasApiKey) {
    return <Navigate to="/" replace />
  }
  return children
}

function RequireAuth({ children }) {
  const { token } = useAuth()
  if (!token) {
    return <Navigate to="/" replace />
  }
  return children
}

// Admin page
function AdminPage({ defaultTab = 'newsletters', includeSandbox = true, forcedTab = null, hideTabs = false }) {
  const [adminKey, setAdminKey] = useState(APIService.adminKey || '')
  const [adminKeyInput, setAdminKeyInput] = useState('')
  const [showKeyValue, setShowKeyValue] = useState(false)
  const [editingKey, setEditingKey] = useState(!APIService.adminKey)
  const [validatingKey, setValidatingKey] = useState(false)
  const [initialKeyValidated, setInitialKeyValidated] = useState(false)
  const [isAdmin, setIsAdmin] = useState(APIService.isAdmin())
  const [runDate, setRunDate] = useState('')
  const [seedSeason, setSeedSeason] = useState('')
  const [runStatus, setRunStatus] = useState(null)
  const [running, setRunning] = useState(false)
  const [settings, setSettings] = useState({
    brave_soft_rank: true,
    brave_site_boost: true,
    brave_cup_synonyms: true,
    search_strict_range: false,
  })
  const [flags, setFlags] = useState([])
  const [flagEditors, setFlagEditors] = useState({})
  const [loans, setLoans] = useState([])
  const [loanForm, setLoanForm] = useState({
    player_id: '',
    player_name: '',
    primary_team_api_id: '',
    loan_team_api_id: '',
    season: '',
  })
  const [loanFilters, _setLoanFilters] = useState({ season: '', sortBy: 'created_at', sortOrder: 'desc', showActive: true })
  const [_loansPagination, _setLoansPagination] = useState({ page: 1, pageSize: 25 })
  const [supplementalLoans, setSupplementalLoans] = useState([])
  const [supplementalFilters, setSupplementalFilters] = useState({ player_name: '', season: '' })
  const [supplementalForm, setSupplementalForm] = useState({ player_name: '', parent_team_name: '', loan_team_name: '', season_year: '' })
  const [missingNames, setMissingNames] = useState([])
  const [mnTeamDbId, setMnTeamDbId] = useState(null)
  const [mnTeamApiId, setMnTeamApiId] = useState('')
  const [mnBusy, setMnBusy] = useState(false)

  // Confirmation dialogs
  const [deleteSupplementalLoanConfirm, setDeleteSupplementalLoanConfirm] = useState(null)
  const [deleteNewsletterConfirm, setDeleteNewsletterConfirm] = useState(null)
  const [deletePlayerFromNlConfirm, setDeletePlayerFromNlConfirm] = useState(null)
  const [deletePlayerConfirm, setDeletePlayerConfirm] = useState(null)
  const [message, setMessage] = useState(null)
  const [nlFilters, setNlFilters] = useState({ published_only: '', week_start: '', week_end: '', issue_start: '', issue_end: '', created_start: '', created_end: '' })
  const [newslettersAdmin, setNewslettersAdmin] = useState([])
  const [newslettersAdminMeta, setNewslettersAdminMeta] = useState({ total: 0, meta: {} })
  const [selectedNewsletterIds, setSelectedNewsletterIds] = useState([])
  const [allFilteredSelected, setAllFilteredSelected] = useState(false)
  const [appliedNlFilters, setAppliedNlFilters] = useState({})
  const [bulkPublishBusy, setBulkPublishBusy] = useState(false)
  const [sendPreviewBusyIds, setSendPreviewBusyIds] = useState([])
  const [sendSelectedBusy, setSendSelectedBusy] = useState(false)
  const [bulkDeleteBusy, setBulkDeleteBusy] = useState(false)
  const [deleteBusyIds, setDeleteBusyIds] = useState([])
  const [editingNl, setEditingNl] = useState(null)
  const [nlYoutubeLinks, setNlYoutubeLinks] = useState([])
  const [nlYoutubeLinkForm, setNlYoutubeLinkForm] = useState({ player_name: '', youtube_link: '', player_id: null })
  const [editingNlYoutubeLink, setEditingNlYoutubeLink] = useState(null)
  const [previewHtml, setPreviewHtml] = useState('')
  const [previewError, setPreviewError] = useState('')
  const [previewFormat, setPreviewFormat] = useState('web')
  const [runHistory, setRunHistory] = useState([])
  const [runTeams, setRunTeams] = useState([])
  const [selectedRunTeams, setSelectedRunTeams] = useState([])
  const [teamRunBusy, setTeamRunBusy] = useState(false)
  const [teamRunMsg, setTeamRunMsg] = useState(null)
  const [confirmRunAllOpen, setConfirmRunAllOpen] = useState(false)
  const [estimatedTeamCount, setEstimatedTeamCount] = useState(null)
  const [seedSectionOpen, setSeedSectionOpen] = useState(false)
  const [adminNewsPage, setAdminNewsPage] = useState(1)
  const [reviewModalOpen, setReviewModalOpen] = useState(false)
  const [reviewQueue, setReviewQueue] = useState([])
  const [reviewIndex, setReviewIndex] = useState(0)
  const [reviewMode, setReviewMode] = useState('manual')
  const [reviewDetail, setReviewDetail] = useState(null)
  const [reviewPreviewFormat, setReviewPreviewFormat] = useState('web')
  const [reviewRenderedContent, setReviewRenderedContent] = useState({ web: '', email: '', webError: null, emailError: null })
  const [reviewLoadingDetail, setReviewLoadingDetail] = useState(false)
  const [reviewBatchExclude, setReviewBatchExclude] = useState([])
  const [reviewBatchDelete, setReviewBatchDelete] = useState([])
  const [reviewFinalizeBusy, setReviewFinalizeBusy] = useState(false)
  const [reviewTotalMatched, setReviewTotalMatched] = useState(0)
  const [playersHubData, setPlayersHubData] = useState({ items: [], total: 0, page: 1, page_size: 50, total_pages: 1 })
  const [playersHubFilters, setPlayersHubFilters] = useState({ team_id: '', search: '', has_sofascore: '' })
  const [playersHubPage, setPlayersHubPage] = useState(1)
  const [playersHubLoading, setPlayersHubLoading] = useState(false)
  const [editingPlayerSofascore, setEditingPlayerSofascore] = useState({})
  const [inlinePlayerNameEdits, setInlinePlayerNameEdits] = useState({})
  const [inlinePlayerNameSaving, setInlinePlayerNameSaving] = useState({})
  const [selectedPlayersForBulk, setSelectedPlayersForBulk] = useState([])
  const [bulkSofascoreMode, setBulkSofascoreMode] = useState(false)
  // Add Player form state
  const [showAddPlayerForm, setShowAddPlayerForm] = useState(false)
  const [addPlayerForm, setAddPlayerForm] = useState({
    name: '',
    firstname: '',
    lastname: '',
    position: '',
    nationality: '',
    age: '',
    sofascore_id: '',
    primary_team_id: '',
    loan_team_id: '',
    window_key: '',
    use_custom_primary_team: false,
    custom_primary_team_name: '',
    use_custom_loan_team: false,
    custom_loan_team_name: ''
  })
  // Subscriber Analytics state
  const [subscriberStats, setSubscriberStats] = useState({ teams: [], total_subscribers: 0 })
  const [subscriberStatsLoading, setSubscriberStatsLoading] = useState(false)
  const [subscriberSearch, setSubscriberSearch] = useState('')
  const [subscriberSort, setSubscriberSort] = useState('desc')
  const [toggleStatusBusy, setToggleStatusBusy] = useState({})

  const [playerFieldOptions, setPlayerFieldOptions] = useState({
    positions: [],
    nationalities: []
  })
  // Edit Player Dialog state
  const [editingPlayerDialog, setEditingPlayerDialog] = useState(null) // {player, loan}
  const [editPlayerForm, setEditPlayerForm] = useState({
    name: '',
    position: '',
    nationality: '',
    age: '',
    sofascore_id: '',
    primary_team_id: '',
    loan_team_id: '',
    use_custom_primary_team: false,
    custom_primary_team_name: '',
    use_custom_loan_team: false,
    custom_loan_team_name: '',
    window_key: ''
  })
  // Enhanced Newsletter Editor state
  const [enhancedEditorMode, setEnhancedEditorMode] = useState('visual') // 'visual' or 'json'
  const [editingPlayerCard, setEditingPlayerCard] = useState(null) // {sectionIndex, itemIndex, data}
  const pageSelectRef = useRef(null)
  const selectionToastRef = useRef({ total: null, excluded: null, active: false })
  const reviewDirtyRef = useRef(false)
  const _adminQuickLinks = useMemo(() => getAdminQuickLinks(), [])
  const adminTotalPages = useMemo(() => {
    const total = Math.ceil(newslettersAdmin.length / ADMIN_NEWSLETTER_PAGE_SIZE)
    return total > 0 ? total : 1
  }, [newslettersAdmin])

  // Unified Dashboard: Tab state and sandbox integration
  const [searchParams, setSearchParams] = useSearchParams()
  const adminTabs = useMemo(() => {
    if (forcedTab) return [forcedTab]
    return getAdminTabs({ includeSandbox })
  }, [forcedTab, includeSandbox])
  const activeTab = useMemo(
    () => resolveAdminTab({ searchParams, defaultTab, allowedTabs: adminTabs, forcedTab }),
    [searchParams, defaultTab, adminTabs, forcedTab],
  )
  const _navigate = useNavigate()

  // Sandbox task state (integrated from AdminSandboxPage)
  const [sandboxTasks, setSandboxTasks] = useState([])
  const [sandboxCollapsedTasks, setSandboxCollapsedTasks] = useState({})
  const [sandboxFormValues, setSandboxFormValues] = useState({})
  const [sandboxResults, setSandboxResults] = useState({})
  const [sandboxLoading, setSandboxLoading] = useState(false)
  const [sandboxError, setSandboxError] = useState('')
  const [runningTaskId, setRunningTaskId] = useState(null)
  const [sofascorePlayers, setSofascorePlayers] = useState([])
  const [sofascoreInputs, setSofascoreInputs] = useState({})
  const [sofascoreUpdatingKey, setSofascoreUpdatingKey] = useState(null)
  const [sofascoreStatus, setSofascoreStatus] = useState(null)

  useEffect(() => {
    const normalizedTab = resolveAdminTab({ searchParams, defaultTab, allowedTabs: adminTabs, forcedTab })
    const current = searchParams.get('tab')
    if (current !== normalizedTab) {
      setSearchParams({ tab: normalizedTab }, { replace: true })
    }
  }, [searchParams, defaultTab, adminTabs, setSearchParams, forcedTab])

  const handleTabChange = useCallback((value) => {
    setSearchParams({ tab: value }, { replace: true })
  }, [setSearchParams])
  const adminPageStart = newslettersAdmin.length ? (adminNewsPage - 1) * ADMIN_NEWSLETTER_PAGE_SIZE + 1 : 0
  const adminPageEnd = newslettersAdmin.length ? Math.min(adminNewsPage * ADMIN_NEWSLETTER_PAGE_SIZE, newslettersAdmin.length) : 0
  const paginatedNewslettersAdmin = useMemo(() => {
    const start = (adminNewsPage - 1) * ADMIN_NEWSLETTER_PAGE_SIZE
    return newslettersAdmin.slice(start, start + ADMIN_NEWSLETTER_PAGE_SIZE)
  }, [newslettersAdmin, adminNewsPage])
  const selectedNewsletterIdsSet = useMemo(() => new Set(selectedNewsletterIds), [selectedNewsletterIds])
  const currentPageNewsletterIds = useMemo(() => paginatedNewslettersAdmin.map((n) => n.id), [paginatedNewslettersAdmin])
  const pageSelectionState = useMemo(() => {
    if (currentPageNewsletterIds.length === 0) {
      return { all: false, some: false }
    }
    const flags = currentPageNewsletterIds.map((id) => {
      const numericId = Number(id)
      if (!Number.isInteger(numericId) || numericId <= 0) return false
      if (allFilteredSelected) return !selectedNewsletterIdsSet.has(numericId)
      return selectedNewsletterIdsSet.has(numericId)
    })
    const all = flags.every(Boolean)
    const some = flags.some(Boolean)
    return { all, some: some && !all }
  }, [currentPageNewsletterIds, selectedNewsletterIdsSet, allFilteredSelected])
  const allPageSelected = pageSelectionState.all
  const somePageSelected = pageSelectionState.some
  const totalFilteredCount = useMemo(() => {
    const metaTotal = Number(newslettersAdminMeta.total)
    if (Number.isFinite(metaTotal) && metaTotal >= 0) return metaTotal
    return newslettersAdmin.length
  }, [newslettersAdminMeta.total, newslettersAdmin.length])
  const selectionExcludedCount = allFilteredSelected ? selectedNewsletterIds.length : 0
  const selectedNewsletterCount = allFilteredSelected
    ? Math.max(totalFilteredCount - selectionExcludedCount, 0)
    : selectedNewsletterIds.length
  const reviewProgressLabel = useMemo(() => computeReviewProgress({ index: reviewIndex, total: reviewQueue.length }), [reviewIndex, reviewQueue.length])
  const currentReviewItem = reviewQueue[reviewIndex] || null
  const reviewModalSizing = useMemo(() => getReviewModalSizing({ minWidth: 760, minHeight: 520, maxWidth: 1280, maxHeight: 960 }), [])

  const buildTeamOptionsForLoan = useCallback((loanRecords = []) => {
    const map = new Map()
    for (const team of runTeams) {
      if (team && team.id) {
        map.set(team.id, team)
      }
    }
    for (const loan of loanRecords) {
      if (!loan) continue
      if (loan.primary_team_id && !map.has(loan.primary_team_id)) {
        map.set(loan.primary_team_id, {
          id: loan.primary_team_id,
          name: loan.primary_team_name || `Team #${loan.primary_team_id}`,
          league_name: loan.primary_team_league_name || 'Other',
          team_id: loan.primary_team_api_id,
        })
      }
      if (loan.loan_team_id && !map.has(loan.loan_team_id)) {
        map.set(loan.loan_team_id, {
          id: loan.loan_team_id,
          name: loan.loan_team_name || `Team #${loan.loan_team_id}`,
          league_name: loan.loan_team_league_name || 'Other',
          team_id: loan.loan_team_api_id,
        })
      }
    }
    return Array.from(map.values())
  }, [runTeams])

  const auth = useAuth()
  const { openLoginModal, logout: triggerLogout } = useAuthUI()

  const hasStoredKey = Boolean(adminKey)
  const hasAdminToken = Boolean(isAdmin)
  const hasAdminAccess = hasStoredKey && hasAdminToken
  const authToken = !!auth.token

  const accessChecklist = useMemo(() => {
    if (authToken && !hasAdminToken) {
      return [{
        key: 'unauthorized',
        label: 'Admin authorization',
        ok: false,
        description: 'This account is not on the approved admin list. Contact an administrator to request access.',
      }]
    }
    return [
      {
        key: 'login',
        label: 'Admin login',
        ok: hasAdminToken,
        description: hasAdminToken
          ? 'OTP session active for this browser.'
          : 'Sign in with your approved admin email to request a one-time code.',
      },
      {
        key: 'key',
        label: 'Admin API key',
        ok: hasStoredKey,
        description: hasStoredKey
          ? 'Key stored locally; never sent until an admin request is made.'
          : 'Paste the API key provided in settings to unlock admin tools.',
      },
    ]
  }, [authToken, hasAdminToken, hasStoredKey])

  const adminReady = hasAdminAccess

  const maskedKey = adminKey ? `${'•'.repeat(Math.max(adminKey.length - 4, 4))}${adminKey.slice(-4)}` : ''
  const adminWarning = !hasAdminToken
    ? authToken
      ? 'This account is not authorized for admin operations.'
      : 'Admin login required. Sign in with an approved admin email.'
    : !hasStoredKey
      ? 'Add your admin API key to enable admin operations.'
      : null

  useEffect(() => {
    if (typeof window === 'undefined') return undefined
    const handleAuthChange = () => {
      const currentKey = APIService.adminKey || ''
      setAdminKey(currentKey)
      setAdminKeyInput('')
      setShowKeyValue(false)
      setEditingKey(!currentKey)
      setIsAdmin(APIService.isAdmin())
    }
    window.addEventListener(APIService.authEventName, handleAuthChange)
    window.addEventListener('storage', handleAuthChange)
    return () => {
      window.removeEventListener(APIService.authEventName, handleAuthChange)
      window.removeEventListener('storage', handleAuthChange)
    }
  }, [])

  const load = useCallback(async () => {
    try {
      const conf = await APIService.adminGetConfig()
      setSettings(s => ({
        ...s,
        brave_soft_rank: (conf.brave_soft_rank || 'true').toString().toLowerCase() !== 'false',
        brave_site_boost: (conf.brave_site_boost || 'true').toString().toLowerCase() !== 'false',
        brave_cup_synonyms: (conf.brave_cup_synonyms || 'true').toString().toLowerCase() !== 'false',
        search_strict_range: (conf.search_strict_range || 'false').toString().toLowerCase() === 'true',
      }))
      const rs = await APIService.adminGetRunStatus()
      setRunStatus(rs.runs_paused)
      const pf = await APIService.adminListPendingFlags()
      setFlags(pf)
      // initial loans set: active
      const ls = await APIService.adminLoansList({ active_only: 'true' })
      setLoans(ls)
      // initial newsletters
      const nls = await APIService.adminNewslettersList({})
      setNewslettersAdmin(Array.isArray(nls) ? nls : [])
      setSelectedNewsletterIds([])
    } catch (error) {
      console.error('Admin load failed', error)
    }
  }, [])

  useEffect(() => {
    if (hasAdminAccess) {
      load()
    } else {
      setFlags([])
      setLoans([])
      setNewslettersAdmin([])
      setSelectedNewsletterIds([])
    }
  }, [hasAdminAccess, load])

  useEffect(() => {
    (async () => {
      try {
        const filters = {}  // Fetch ALL teams, not just European
        const seasonYear = parseInt((loanFilters.season || '').trim(), 10)
        if (!isNaN(seasonYear)) filters.season = seasonYear
        const teams = await APIService.getTeams(filters)
        const { teams: filtered } = filterLatestSeasonTeams(Array.isArray(teams) ? teams : [])
        setRunTeams(filtered)
      } catch (error) {
        console.error('Failed to load run teams', error)
        setRunTeams([])
      }
    })()
  }, [loanFilters.season])

  const refreshRunHistory = async () => {
    try {
      const rows = await APIService.request('/admin/runs/history', {}, { admin: true })
      setRunHistory(Array.isArray(rows) ? rows : [])
    } catch (error) {
      console.warn('Failed to refresh run history', error)
    }
  }
  useEffect(() => {
    if (hasAdminAccess) {
      refreshRunHistory()
    } else {
      setRunHistory([])
    }
  }, [hasAdminAccess])

  useEffect(() => {
    const total = Math.ceil(newslettersAdmin.length / ADMIN_NEWSLETTER_PAGE_SIZE)
    const normalizedTotal = total > 0 ? total : 1
    if (adminNewsPage > normalizedTotal) {
      setAdminNewsPage(normalizedTotal)
    }
  }, [newslettersAdmin, adminNewsPage])

  useEffect(() => {
    if (pageSelectRef.current) {
      pageSelectRef.current.indeterminate = somePageSelected && !allPageSelected
    }
  }, [somePageSelected, allPageSelected])
  useEffect(() => {
    if (!allFilteredSelected) {
      selectionToastRef.current = { total: null, excluded: null, active: false }
      return
    }
    const total = totalFilteredCount
    const excluded = selectedNewsletterIds.length
    const prev = selectionToastRef.current
    if (prev.total === total && prev.excluded === excluded && prev.active) {
      return
    }
    selectionToastRef.current = { total, excluded, active: true }
    if (total <= 0) {
      setMessage((current) => {
        if (current && current.type && current.type !== 'info') return current
        return { type: 'info', text: 'No newsletters match your filters.' }
      })
      return
    }
    setMessage((current) => {
      if (current && current.type && current.type !== 'info') return current
      return { type: 'info', text: formatBulkSelectionToast({ totalMatched: total, totalExcluded: excluded }) }
    })
  }, [allFilteredSelected, selectedNewsletterIds.length, totalFilteredCount])

  useEffect(() => {
    if (!hasAdminToken) {
      setInitialKeyValidated(false)
      return
    }
    if (initialKeyValidated) return
    if (!adminKey) return
    let cancelled = false
    const verifyExistingKey = async () => {
      try {
        await APIService.validateAdminCredentials()
        if (!cancelled) {
          setInitialKeyValidated(true)
        }
      } catch (error) {
        if (cancelled) return
        APIService.setAdminKey('')
        setAdminKey('')
        setAdminKeyInput('')
        const baseError = error?.body?.error || error.message || 'Key rejected by server'
        const detail = error?.body?.detail || (error?.body?.reference ? `Reference: ${error.body.reference}` : '')
        setMessage({
          type: 'error',
          text: `Stored admin key was rejected: ${baseError}${detail ? ` — ${detail}` : ''}`
        })
        setEditingKey(true)
        setInitialKeyValidated(true)
      }
    }
    verifyExistingKey()
    return () => {
      cancelled = true
    }
  }, [hasAdminToken, adminKey, initialKeyValidated])

  const saveKey = async () => {
    const trimmed = (adminKeyInput || '').trim()
    if (!trimmed) {
      clearKey()
      return
    }
    const previousKey = adminKey
    setValidatingKey(true)
    setMessage({ type: 'info', text: 'Validating admin API key…' })
    APIService.setAdminKey(trimmed)
    try {
      await APIService.validateAdminCredentials()
      setAdminKey(trimmed)
      setAdminKeyInput('')
      setEditingKey(false)
      setShowKeyValue(false)
      setMessage({ type: 'success', text: 'Admin key saved and verified' })
      setInitialKeyValidated(true)
    } catch (error) {
      APIService.setAdminKey(previousKey || '')
      setAdminKey(previousKey || '')
      setAdminKeyInput(trimmed)
      const baseError = error?.body?.error || error.message || 'Key rejected by server'
      const detail = error?.body?.detail || (error?.body?.reference ? `Reference: ${error.body.reference}` : '')
      setMessage({
        type: 'error',
        text: `Admin key not accepted: ${baseError}${detail ? ` — ${detail}` : ''}`
      })
      setEditingKey(true)
    } finally {
      setValidatingKey(false)
    }
  }

  const clearKey = () => {
    APIService.setAdminKey('')
    setAdminKey('')
    setAdminKeyInput('')
    setEditingKey(true)
    setShowKeyValue(false)
    setMessage({ type: 'success', text: 'Admin key cleared' })
    setInitialKeyValidated(false)
  }

  const startEditingKey = () => {
    setEditingKey(true)
    setAdminKeyInput(adminKey || '')
    setShowKeyValue(false)
  }
  const saveSettings = async () => {
    try {
      await APIService.adminUpdateConfig(settings)
      setMessage({ type: 'success', text: 'Settings updated' })
    } catch (error) {
      console.error('Failed to update admin settings', error)
      setMessage({ type: 'error', text: 'Failed to update settings' })
    }
  }
  const toggleRun = async () => {
    try {
      const next = !runStatus
      await APIService.adminSetRunStatus(next)
      setRunStatus(next)
    } catch (error) {
      console.error('Failed to toggle run status', error)
    }
  }
  const fetchTeamCountEstimate = useCallback(async () => {
    try {
      const stats = await APIService.getStats()
      setEstimatedTeamCount(stats?.teams_with_loans || null)
    } catch (error) {
      console.warn('Failed to fetch team count estimate', error)
      setEstimatedTeamCount(null)
    }
  }, [])

  const handleRunAllClick = useCallback(() => {
    fetchTeamCountEstimate()
    setConfirmRunAllOpen(true)
  }, [fetchTeamCountEstimate])

  const runAll = async () => {
    setConfirmRunAllOpen(false)
    setRunning(true)
    setMessage(null)
    try {
      const d = runDate || new Date().toISOString().slice(0, 10)
      const out = await APIService.adminGenerateAll(d)
      const results = Array.isArray(out?.results) ? out.results : []
      const ok = results.filter((r) => r && r.newsletter_id).length
      const errs = results.filter((r) => r && r.error).length
      const skipped = results.filter((r) => r && r.skipped === 'no_active_loanees').length
      const parts = []
      parts.push(`${ok} ok`)
      parts.push(`${errs} errors`)
      if (skipped) parts.push(`${skipped} skipped`)
      const extra = results.length ? ` (${parts.join(', ')})` : ''
      setMessage({ type: 'success', text: `Triggered run for ${out?.ran_for || d}${extra}` })
      // pull in new run-history entry
      try {
        await refreshRunHistory()
      } catch (error) {
        console.warn('Failed to refresh run history after runAll', error)
      }
    } catch (error) {
      const detail = (error && (error.body?.error || error.message))
        ? `: ${String(error.body?.error || error.message)}`
        : ''
      setMessage({ type: 'error', text: `Failed to trigger run${detail}` })
    } finally {
      setRunning(false)
    }
  }
  const resolveFlag = async (id, deactivate = false) => {
    try {
      await APIService.adminResolveFlag(id, { deactivateLoan: deactivate })
      setFlags((prev) => prev.filter((f) => f.id !== id))
      setFlagEditors((prev) => {
        if (!prev[id]) return prev
        const next = { ...prev }
        delete next[id]
        return next
      })
    } catch (error) {
      console.error('Failed to resolve flag', error)
    }
  }
  const openFlagEditor = async (flag) => {
    setFlagEditors((prev) => ({
      ...prev,
      [flag.id]: {
        open: true,
        loading: true,
        saving: false,
        error: null,
        loans: prev[flag.id]?.loans || [],
        selectedLoanId: prev[flag.id]?.selectedLoanId || null,
        primaryTeamId: prev[flag.id]?.primaryTeamId || null,
        loanTeamId: prev[flag.id]?.loanTeamId || null,
      },
    }))
    try {
      const rows = await APIService.adminLoansList({ player_id: flag.player_api_id, active_only: 'false' })
      const list = Array.isArray(rows) ? rows : []
      if (list.length === 0) {
        setFlagEditors((prev) => ({
          ...prev,
          [flag.id]: {
            open: true,
            loading: false,
            saving: false,
            error: 'No matching loan records were found for this player.',
            loans: [],
            selectedLoanId: null,
            primaryTeamId: null,
            loanTeamId: null,
          },
        }))
        return
      }
      const preferred = list.find((l) => l.is_active) || list[0]
      setFlagEditors((prev) => ({
        ...prev,
        [flag.id]: {
          open: true,
          loading: false,
          saving: false,
          error: null,
          loans: list,
          selectedLoanId: preferred?.id || null,
          primaryTeamId: preferred?.primary_team_id ?? null,
          loanTeamId: preferred?.loan_team_id ?? null,
        },
      }))
    } catch (error) {
      const msg = error?.body?.error || error.message || 'Failed to load loan details.'
      setFlagEditors((prev) => ({
        ...prev,
        [flag.id]: {
          open: true,
          loading: false,
          saving: false,
          error: msg,
          loans: [],
          selectedLoanId: null,
          primaryTeamId: null,
          loanTeamId: null,
        },
      }))
    }
  }
  const closeFlagEditor = (flagId) => {
    setFlagEditors((prev) => {
      if (!prev[flagId]) return prev
      const next = { ...prev }
      delete next[flagId]
      return next
    })
  }
  const selectFlagLoanRecord = (flagId, loanId) => {
    const numeric = Number(loanId)
    setFlagEditors((prev) => {
      const editor = prev[flagId]
      if (!editor) return prev
      const loan = (editor.loans || []).find((l) => l.id === numeric)
      if (!loan) return prev
      return {
        ...prev,
        [flagId]: {
          ...editor,
          selectedLoanId: numeric,
          primaryTeamId: loan.primary_team_id ?? editor.primaryTeamId ?? null,
          loanTeamId: loan.loan_team_id ?? editor.loanTeamId ?? null,
        },
      }
    })
  }
  const setFlagPrimaryTeam = (flagId, teamId) => {
    const numeric = teamId != null ? Number(teamId) : null
    setFlagEditors((prev) => {
      const editor = prev[flagId]
      if (!editor) return prev
      return {
        ...prev,
        [flagId]: {
          ...editor,
          primaryTeamId: Number.isNaN(numeric) ? null : numeric,
        },
      }
    })
  }
  const setFlagLoanTeam = (flagId, teamId) => {
    const numeric = teamId != null ? Number(teamId) : null
    setFlagEditors((prev) => {
      const editor = prev[flagId]
      if (!editor) return prev
      return {
        ...prev,
        [flagId]: {
          ...editor,
          loanTeamId: Number.isNaN(numeric) ? null : numeric,
        },
      }
    })
  }
  const saveFlagLoanChanges = async (flag) => {
    const editor = flagEditors[flag.id]
    if (!editor || editor.loading || editor.saving) return
    if (!editor.selectedLoanId) {
      setFlagEditors((prev) => ({
        ...prev,
        [flag.id]: {
          ...editor,
          error: 'Select a loan record before saving.',
        },
      }))
      return
    }
    setFlagEditors((prev) => ({
      ...prev,
      [flag.id]: {
        ...editor,
        saving: true,
        error: null,
      },
    }))
    try {
      const payload = {}
      if (editor.primaryTeamId) payload.primary_team_db_id = editor.primaryTeamId
      if (editor.loanTeamId) payload.loan_team_db_id = editor.loanTeamId
      if (flag.season) payload.season = flag.season
      const result = await APIService.adminLoanUpdate(editor.selectedLoanId, payload)
      const updatedLoan = result?.loan || null
      setFlagEditors((prev) => {
        const current = prev[flag.id]
        if (!current) return prev
        const nextLoans = updatedLoan
          ? (current.loans || []).map((l) => (l.id === updatedLoan.id ? updatedLoan : l))
          : current.loans || []
        return {
          ...prev,
          [flag.id]: {
            ...current,
            loans: nextLoans,
            primaryTeamId: updatedLoan?.primary_team_id ?? current.primaryTeamId,
            loanTeamId: updatedLoan?.loan_team_id ?? current.loanTeamId,
            saving: false,
            error: null,
          },
        }
      })
      if (updatedLoan) {
        setFlags((prev) => prev.map((f) => (f.id === flag.id
          ? {
            ...f,
            primary_team_api_id: updatedLoan.primary_team_api_id,
            loan_team_api_id: updatedLoan.loan_team_api_id,
          }
          : f)))
      }
      setMessage({ type: 'success', text: 'Loan assignment updated.' })
    } catch (error) {
      const msg = error?.body?.error || error.message || 'Failed to update loan.'
      setFlagEditors((prev) => {
        const current = prev[flag.id]
        if (!current) return prev
        return {
          ...prev,
          [flag.id]: {
            ...current,
            saving: false,
            error: msg,
          },
        }
      })
      setMessage({ type: 'error', text: `Loan update failed: ${msg}` })
    }
  }
  const refreshLoans = async () => {
    const params = { ...loanFilters }
    if (params.player_name && params.player_name.trim() === '') delete params.player_name
    const ls = await APIService.adminLoansList(params)
    setLoans(ls)
  }
  const backfillTeamLeagues = async () => {
    try {
      const seasonStr = (loanFilters.season || '').trim()
      const seasonYear = parseInt(seasonStr, 10)
      if (!seasonYear) {
        setMessage({ type: 'error', text: 'Enter a valid Season (YYYY) to backfill leagues' })
        return
      }
      const res = await APIService.adminBackfillTeamLeagues(seasonYear)
      setMessage({ type: 'success', text: `Backfilled leagues for ${seasonYear} (updated ${res.updated_teams} teams)` })
      // Reload teams list for this season
      const teams = await APIService.getTeams({ season: seasonYear })  // All teams, not just European
      const { teams: filtered } = filterLatestSeasonTeams(Array.isArray(teams) ? teams : [])
      setRunTeams(filtered)
    } catch (error) {
      setMessage({ type: 'error', text: `Backfill failed: ${error?.body?.error || error.message}` })
    }
  }
  const backfillAllSeasons = async () => {
    try {
      const res = await APIService.adminBackfillTeamLeaguesAll()
      const updated = res?.totals?.updated_teams || 0
      const seasons = res?.totals?.seasons || 0
      setMessage({ type: 'success', text: `Backfilled all seasons (${seasons}), updated ${updated} teams` })
      // Reload current filter's teams if any
      const seasonYear = parseInt((loanFilters.season || '').trim(), 10)
      const filters = {}  // All teams, not just European
      if (!isNaN(seasonYear)) filters.season = seasonYear
      const teams = await APIService.getTeams(filters)
      setRunTeams(Array.isArray(teams) ? teams : [])
    } catch (error) {
      setMessage({ type: 'error', text: `Backfill (all) failed: ${error?.body?.error || error.message}` })
    }
  }
  const listMissingNames = async () => {
    try {
      setMnBusy(true)
      const seasonStr = (loanFilters.season || '').trim()
      const seasonYear = parseInt(seasonStr, 10)
      const params = { active_only: 'true' }
      if (!isNaN(seasonYear)) params.season = seasonYear
      if (mnTeamDbId) params.primary_team_db_id = parseInt(mnTeamDbId, 10)
      else if (mnTeamApiId && mnTeamApiId.trim()) params.primary_team_api_id = parseInt(mnTeamApiId, 10)
      const rows = await APIService.adminMissingNames(params)
      setMissingNames(Array.isArray(rows) ? rows : [])
    } catch (error) {
      setMissingNames([])
      setMessage({ type: 'error', text: `List missing names failed: ${error?.body?.error || error.message}` })
    } finally {
      setMnBusy(false)
    }
  }
  const backfillMissingNames = async () => {
    try {
      setMnBusy(true)
      const seasonStr = (loanFilters.season || '').trim()
      const seasonYear = parseInt(seasonStr, 10)
      if (!seasonYear) {
        setMessage({ type: 'error', text: 'Enter Season (YYYY) first to backfill names' })
        return
      }
      const payload = { season: seasonYear, active_only: true }
      if (mnTeamDbId) payload.primary_team_db_id = parseInt(mnTeamDbId, 10)
      else if (mnTeamApiId && mnTeamApiId.trim()) payload.primary_team_api_id = parseInt(mnTeamApiId, 10)
      const res = await APIService.adminBackfillNames(payload)
      const up = res?.updated || 0
      setMessage({ type: 'success', text: `Backfilled ${up} player names` })
      await refreshLoans()
      await listMissingNames()
    } catch (error) {
      setMessage({ type: 'error', text: `Backfill names failed: ${error?.body?.error || error.message}` })
    } finally {
      setMnBusy(false)
    }
  }
  const _createLoan = async () => {
    try {
      const payload = {
        player_id: parseInt(loanForm.player_id, 10),
        player_name: loanForm.player_name || undefined,
        primary_team_api_id: loanForm.primary_team_api_id ? parseInt(loanForm.primary_team_api_id, 10) : undefined,
        loan_team_api_id: loanForm.loan_team_api_id ? parseInt(loanForm.loan_team_api_id, 10) : undefined,
        season: loanForm.season ? parseInt(loanForm.season, 10) : undefined,
      }
      await APIService.adminLoanCreate(payload)
      setMessage({ type: 'success', text: 'Loan created' })
      setLoanForm({ player_id: '', player_name: '', primary_team_api_id: '', loan_team_api_id: '', season: '' })
      await refreshLoans()
    } catch (error) {
      setMessage({ type: 'error', text: `Create failed: ${error?.body?.error || error.message}` })
    }
  }
  const moveLoanDb = async (loan, kind, dbId) => {
    try {
      const payload = {}
      if (kind === 'primary') payload.primary_team_db_id = parseInt(dbId, 10)
      else payload.loan_team_db_id = parseInt(dbId, 10)
      await APIService.adminLoanUpdate(loan.id, payload)
      await refreshLoans()
      await loadPlayersHub()  // Also refresh Players & Loans Manager
    } catch (error) {
      setMessage({ type: 'error', text: `Update failed: ${error?.body?.error || error.message}` })
    }
  }
  const _deactivateLoan = async (loan) => {
    try {
      await APIService.adminLoanDeactivate(loan.id)
      await refreshLoans()
    } catch (error) {
      setMessage({ type: 'error', text: `Deactivate failed: ${error?.body?.error || error.message}` })
    }
  }
  const refreshSupplementalLoans = async () => {
    const params = { ...supplementalFilters }
    if (params.player_name && params.player_name.trim() === '') delete params.player_name
    const ls = await APIService.adminSupplementalLoansList(params)
    setSupplementalLoans(ls)
  }
  const createSupplementalLoan = async () => {
    try {
      const payload = {
        player_name: supplementalForm.player_name.trim(),
        parent_team_name: supplementalForm.parent_team_name.trim(),
        loan_team_name: supplementalForm.loan_team_name.trim(),
        season_year: parseInt(supplementalForm.season_year, 10),
      }
      if (!payload.player_name || !payload.parent_team_name || !payload.loan_team_name || !payload.season_year) {
        setMessage({ type: 'error', text: 'All fields are required' })
        return
      }
      await APIService.adminSupplementalLoanCreate(payload)
      setMessage({ type: 'success', text: 'Manual player added successfully' })
      setSupplementalForm({ player_name: '', parent_team_name: '', loan_team_name: '', season_year: '' })
      await refreshSupplementalLoans()
    } catch (error) {
      setMessage({ type: 'error', text: `Create failed: ${error?.body?.error || error.message}` })
    }
  }
  const deleteSupplementalLoan = (loan) => {
    setDeleteSupplementalLoanConfirm(loan)
  }

  const confirmDeleteSupplementalLoan = async () => {
    if (!deleteSupplementalLoanConfirm) return
    try {
      await APIService.adminSupplementalLoanDelete(deleteSupplementalLoanConfirm.id)
      setMessage({ type: 'success', text: 'Manual player deleted successfully' })
      setDeleteSupplementalLoanConfirm(null)
      await refreshSupplementalLoans()
    } catch (error) {
      setMessage({ type: 'error', text: `Delete failed: ${error?.body?.error || error.message}` })
      setDeleteSupplementalLoanConfirm(null)
    }
  }
  const teamIdToTeam = useMemo(() => {
    const m = new Map()
    for (const t of runTeams) m.set(t.id, t)
    return m
  }, [runTeams])
  const filteredLoans = useMemo(() => {
    const seasonStr = (loanFilters.season || '').trim()
    if (!seasonStr) return loans
    const seasonYear = parseInt(seasonStr, 10)
    if (!seasonYear) return loans
    const matchesSeason = (l) => {
      const ls = l.loan_season
      if (ls) {
        const start = parseInt(String(ls).split('-')[0], 10)
        return start === seasonYear
      }
      const wk = l.window_key || ''
      try {
        const start = parseInt(String(wk).split('::')[0].split('-')[0], 10)
        return start === seasonYear
      } catch {
        return false
      }
    }
    return loans.filter(matchesSeason)
  }, [loans, loanFilters.season])
  const _loansByLeague = useMemo(() => {
    const leagues = {}
    for (const l of filteredLoans) {
      const t = teamIdToTeam.get(l.primary_team_id)
      const league = t?.league_name || 'Other'
      if (!leagues[league]) leagues[league] = {}
      const teamKey = l.primary_team_id
      if (!leagues[league][teamKey]) leagues[league][teamKey] = { teamId: teamKey, teamName: l.primary_team_name, loans: [] }
      leagues[league][teamKey].loans.push(l)
    }
    return leagues
  }, [filteredLoans, teamIdToTeam])
  const refreshNewsletters = async () => {
    const params = {}
    if (nlFilters.published_only) params.published_only = nlFilters.published_only
    if (nlFilters.week_start && nlFilters.week_end) {
      params.week_start = nlFilters.week_start
      params.week_end = nlFilters.week_end
    }
    if (nlFilters.issue_start && nlFilters.issue_end) {
      params.issue_start = nlFilters.issue_start
      params.issue_end = nlFilters.issue_end
    }
    if (nlFilters.created_start && nlFilters.created_end) {
      params.created_start = nlFilters.created_start
      params.created_end = nlFilters.created_end
    }
    const result = await APIService.adminNewslettersList(params)
    const normalizedRows = Array.isArray(result?.items)
      ? result.items
      : Array.isArray(result)
        ? result
        : []
    const allowedIds = new Set(normalizedRows.map((row) => row.id))
    setSelectedNewsletterIds((prev) => prev.filter((id) => allowedIds.has(id)))
    setNewslettersAdmin(normalizedRows)
    setNewslettersAdminMeta({ total: Number(result?.total) || normalizedRows.length, meta: result?.meta || {} })
    setAppliedNlFilters(params)
    setAdminNewsPage(1)
  }
  const resetNewsletterFilters = () => setNlFilters({ published_only: '', week_start: '', week_end: '', issue_start: '', issue_end: '', created_start: '', created_end: '' })
  const toggleNewsletterSelection = (id) => {
    const numericId = Number(id)
    if (!Number.isInteger(numericId) || numericId <= 0) return
    setSelectedNewsletterIds((prev) => {
      const set = new Set(prev)
      if (allFilteredSelected) {
        if (set.has(numericId)) {
          set.delete(numericId)
        } else {
          set.add(numericId)
        }
      } else {
        if (set.has(numericId)) {
          set.delete(numericId)
        } else {
          set.add(numericId)
        }
      }
      return Array.from(set)
    })
  }
  const togglePageSelection = (checked) => {
    const ids = currentPageNewsletterIds
    if (ids.length === 0) return
    if (allFilteredSelected) {
      if (checked) {
        setSelectedNewsletterIds((prev) => prev.filter((value) => !ids.includes(value)))
      } else {
        setSelectedNewsletterIds((prev) => {
          const merged = new Set(prev)
          for (const value of ids) merged.add(value)
          return Array.from(merged)
        })
      }
    } else if (checked) {
      setSelectedNewsletterIds((prev) => {
        const merged = new Set(prev)
        for (const value of ids) merged.add(value)
        return Array.from(merged)
      })
    } else {
      setSelectedNewsletterIds((prev) => prev.filter((value) => !ids.includes(value)))
    }
  }
  const handleToggleAllFiltered = (checked) => {
    setAllFilteredSelected(!!checked)
    setSelectedNewsletterIds([])
    selectionToastRef.current = { total: null, excluded: null, active: false }
  }
  const clearNewsletterSelection = () => {
    setSelectedNewsletterIds([])
    setAllFilteredSelected(false)
  }
  const addSendingIds = useCallback((ids) => {
    const normalized = normalizeNewsletterIds(ids)
    if (normalized.length === 0) return
    setSendPreviewBusyIds((prev) => {
      const merged = new Set(prev)
      for (const id of normalized) merged.add(id)
      return Array.from(merged)
    })
  }, [])
  const removeSendingIds = useCallback((ids) => {
    const normalized = normalizeNewsletterIds(ids)
    if (normalized.length === 0) return
    setSendPreviewBusyIds((prev) => prev.filter((value) => !normalized.includes(value)))
  }, [])
  const addDeletingIds = useCallback((ids) => {
    const normalized = normalizeNewsletterIds(ids)
    if (normalized.length === 0) return
    setDeleteBusyIds((prev) => {
      const merged = new Set(prev)
      for (const id of normalized) merged.add(id)
      return Array.from(merged)
    })
  }, [])
  const removeDeletingIds = useCallback((ids) => {
    const normalized = normalizeNewsletterIds(ids)
    if (normalized.length === 0) return
    setDeleteBusyIds((prev) => prev.filter((value) => !normalized.includes(value)))
  }, [])
  const deleteNewsletters = useCallback(async (ids, { confirmPrompt = true, trackBulk = false } = {}) => {
    const normalized = normalizeNewsletterIds(ids)
    if (normalized.length === 0) {
      setMessage({ type: 'error', text: 'Select at least one newsletter first.' })
      return { successIds: [], failureDetails: [] }
    }

    if (confirmPrompt && typeof window !== 'undefined') {
      const label = normalized.length === 1 ? `newsletter #${normalized[0]}` : `${normalized.length} newsletters`
      return new Promise((resolve) => {
        setDeleteNewsletterConfirm({ ids: normalized, label, resolve, trackBulk })
      })
    }

    if (trackBulk) setBulkDeleteBusy(true)
    addDeletingIds(normalized)
    const successIds = []
    const failureDetails = []
    try {
      for (const id of normalized) {
        try {
          await APIService.adminNewsletterDelete(id)
          successIds.push(id)
        } catch (error) {
          failureDetails.push({ id, error })
        }
      }
    } finally {
      removeDeletingIds(normalized)
      if (trackBulk) setBulkDeleteBusy(false)
    }

    if (successIds.length > 0) {
      setSelectedNewsletterIds((prev) => prev.filter((value) => !successIds.includes(value)))
      try {
        await refreshNewsletters()
      } catch (error) {
        console.warn('Failed to refresh newsletters after delete', error)
      }
    }

    const type = failureDetails.length ? (successIds.length ? 'warning' : 'error') : 'success'
    setMessage({ type, text: formatDeleteSummary({ successIds, failureDetails }) })
    return { successIds, failureDetails }
  }, [addDeletingIds, removeDeletingIds, refreshNewsletters, setMessage, setSelectedNewsletterIds])

  const confirmDeleteNewsletter = async () => {
    if (!deleteNewsletterConfirm) return
    const { ids, resolve, trackBulk, isFiltered, filterParams, totalMatched, excludedIds } = deleteNewsletterConfirm

    setDeleteNewsletterConfirm(null)

    if (resolve && typeof resolve === 'function') {
      // For review mode with custom resolve
      await resolve()
      return
    }

    if (isFiltered) {
      // For filtered bulk delete
      setBulkDeleteBusy(true)
      try {
        const payload = resolveBulkActionPayload({
          useFilters: true,
          filterParams,
          totalMatched,
          excludedIds,
          explicitIds: [],
        })
        const result = await APIService.adminNewsletterBulkDelete(payload)
        const deleted = result?.deleted || 0
        setMessage({ type: 'success', text: `Deleted ${deleted} newsletter(s)` })
        setAllFilteredSelected(false)
        setSelectedNewsletterIds([])
        await refreshNewsletters()
      } catch (error) {
        setMessage({ type: 'error', text: `Bulk delete failed: ${error?.body?.error || error.message}` })
      } finally {
        setBulkDeleteBusy(false)
      }
      return
    }

    // For standard deletion with ids
    if (ids && ids.length > 0) {
      await deleteNewsletters(ids, { confirmPrompt: false, trackBulk })
    }
  }

  const sendAdminPreview = useCallback(async (ids, { trackBulk = false } = {}) => {
    const normalized = normalizeNewsletterIds(ids)
    if (normalized.length === 0) {
      setMessage({ type: 'error', text: 'Select at least one newsletter first.' })
      return { successIds: [], failureDetails: [] }
    }
    if (trackBulk) setSendSelectedBusy(true)
    addSendingIds(normalized)
    const successIds = []
    const failureDetails = []
    try {
      for (const id of normalized) {
        try {
          await APIService.adminNewsletterSendPreview(id)
          successIds.push(id)
        } catch (error) {
          failureDetails.push({ id, error })
        }
      }
    } finally {
      removeSendingIds(normalized)
      if (trackBulk) setSendSelectedBusy(false)
    }
    const type = failureDetails.length ? (successIds.length ? 'warning' : 'error') : 'success'
    setMessage({ type, text: formatSendPreviewSummary({ successIds, failureDetails }) })
    return { successIds, failureDetails }
  }, [addSendingIds, removeSendingIds, setMessage])
  const sendAdminPreviewSelected = useCallback(async () => {
    if (allFilteredSelected) {
      setMessage({ type: 'warning', text: 'Disable “Select all filtered” to send previews for specific newsletters.' })
      return { successIds: [], failureDetails: [] }
    }
    return sendAdminPreview(selectedNewsletterIds, { trackBulk: true })
  }, [allFilteredSelected, sendAdminPreview, selectedNewsletterIds])
  const deleteSelectedNewsletters = useCallback(async () => {
    if (allFilteredSelected) {
      const total = totalFilteredCount
      if (total === 0) {
        setMessage({ type: 'error', text: 'No newsletters match your filters.' })
        return { successIds: [], failureDetails: [] }
      }
      if (typeof window !== 'undefined') {
        const label = `${total - selectedNewsletterIds.length} filtered newsletters`
        return new Promise((resolve) => {
          setDeleteNewsletterConfirm({
            ids: null,
            label,
            resolve,
            trackBulk: true,
            isFiltered: true,
            filterParams: appliedNlFilters,
            totalMatched: total,
            excludedIds: selectedNewsletterIds
          })
        })
      }
      setBulkDeleteBusy(true)
      try {
        const payload = resolveBulkActionPayload({
          useFilters: true,
          filterParams: appliedNlFilters,
          totalMatched: total,
          excludedIds: selectedNewsletterIds,
          explicitIds: [],
        })
        const res = await APIService.adminNewsletterBulkDelete({ ...payload.body })
        setMessage({
          type: 'success',
          text: `Deleted ${res?.deleted || 0} newsletter${(res?.deleted || 0) === 1 ? '' : 's'}.`,
        })
        setSelectedNewsletterIds([])
        await refreshNewsletters()
        return { successIds: [], failureDetails: [] }
      } catch (error) {
        setMessage({ type: 'error', text: `Bulk delete failed: ${error?.body?.error || error.message}` })
        return { successIds: [], failureDetails: [] }
      } finally {
        setBulkDeleteBusy(false)
      }
    }
    return deleteNewsletters(selectedNewsletterIds, { confirmPrompt: true, trackBulk: true })
  }, [allFilteredSelected, deleteNewsletters, selectedNewsletterIds, appliedNlFilters, totalFilteredCount, refreshNewsletters])
  const bulkPublishSelected = async (publishFlag) => {
    const payloadInfo = resolveBulkActionPayload({
      useFilters: allFilteredSelected,
      filterParams: appliedNlFilters,
      totalMatched: totalFilteredCount,
      excludedIds: allFilteredSelected ? selectedNewsletterIds : [],
      explicitIds: allFilteredSelected ? [] : selectedNewsletterIds,
    })
    if (payloadInfo.mode === 'ids' && (!payloadInfo.body.ids || payloadInfo.body.ids.length === 0)) {
      setMessage({ type: 'error', text: 'Select at least one newsletter first.' })
      return
    }
    if (payloadInfo.mode === 'filters' && totalFilteredCount === 0) {
      setMessage({ type: 'error', text: 'No newsletters match your filters.' })
      return
    }
    setBulkPublishBusy(true)
    const previousExcluded = selectedNewsletterIds.length
    try {
      const response = await APIService.adminNewsletterBulkPublish({ ...payloadInfo.body }, publishFlag)
      setSelectedNewsletterIds([])
      await refreshNewsletters()
      const updatedCount = Number(response?.updated) || 0
      const excludedCount = payloadInfo.mode === 'filters'
        ? Number(response?.meta?.total_excluded ?? previousExcluded)
        : 0
      const verb = publishFlag ? 'Published' : 'Unpublished'
      const suffix = updatedCount === 1 ? '' : 's'
      const excludedText = excludedCount > 0 ? ` (${excludedCount} excluded)` : ''
      setMessage({ type: 'success', text: `${verb} ${updatedCount} newsletter${suffix}.${excludedText}`.trim() })
    } catch (error) {
      setMessage({ type: 'error', text: `Bulk update failed: ${error?.body?.error || error.message}` })
    } finally {
      setBulkPublishBusy(false)
    }
  }

  const openReviewModal = useCallback((mode = 'manual') => {
    if (!newslettersAdmin.length) {
      setMessage({ type: 'info', text: 'No newsletters match your filters.' })
      return
    }
    const queue = [...newslettersAdmin].sort((a, b) => {
      const dateFor = (row) => row.generated_date || row.published_date || row.issue_date || row.created_at || ''
      return new Date(dateFor(b)) - new Date(dateFor(a))
    })
    setReviewQueue(queue)
    setReviewIndex(0)
    setReviewMode(mode === 'auto' ? 'auto' : 'manual')
    setReviewDetail(null)
    setReviewRenderedContent({ web: '', email: '', webError: null, emailError: null })
    setReviewBatchExclude([])
    setReviewBatchDelete([])
    setReviewPreviewFormat('web')
    setReviewTotalMatched(newslettersAdminMeta.total || newslettersAdmin.length)
    setReviewLoadingDetail(false)
    setReviewFinalizeBusy(false)
    setReviewModalOpen(true)
  }, [newslettersAdmin, newslettersAdminMeta.total, setMessage])

  const closeReviewModal = useCallback(async () => {
    setReviewModalOpen(false)
    setReviewQueue([])
    setReviewIndex(0)
    setReviewDetail(null)
    setReviewRenderedContent({ web: '', email: '', webError: null, emailError: null })
    setReviewBatchExclude([])
    setReviewBatchDelete([])
    setReviewPreviewFormat('web')
    setReviewLoadingDetail(false)
    setReviewFinalizeBusy(false)
    if (reviewDirtyRef.current) {
      try {
        await refreshNewsletters()
      } catch (error) {
        console.error('Failed to refresh newsletters after review', error)
      }
      reviewDirtyRef.current = false
    }
  }, [refreshNewsletters])

  const finalizeAutoReview = useCallback(async () => {
    setReviewFinalizeBusy(true)
    try {
      const total = reviewTotalMatched
      const excludeSet = new Set(reviewBatchExclude)
      for (const id of reviewBatchDelete) excludeSet.add(id)
      const excludeIds = Array.from(excludeSet)
      if (total > 0 && (total - excludeIds.length) >= 0) {
        const payload = resolveBulkActionPayload({
          useFilters: true,
          filterParams: appliedNlFilters,
          totalMatched: total,
          excludedIds: excludeIds,
          explicitIds: [],
        })
        await APIService.adminNewsletterBulkPublish({ ...payload.body }, true)
      }
      if (reviewBatchDelete.length > 0) {
        await APIService.adminNewsletterBulkDelete({ ids: reviewBatchDelete })
      }
      reviewDirtyRef.current = true
      const publishedCount = Math.max(reviewTotalMatched - excludeIds.length, 0)
      const deleteCount = reviewBatchDelete.length
      const summaryParts = []
      summaryParts.push(`Published ${publishedCount} newsletter${publishedCount === 1 ? '' : 's'}.`)
      if (deleteCount > 0) {
        summaryParts.push(`Deleted ${deleteCount}.`)
      }
      setMessage({ type: 'success', text: summaryParts.join(' ') })
    } catch (error) {
      setMessage({ type: 'error', text: `Review flow failed: ${error?.body?.error || error.message}` })
    } finally {
      setReviewFinalizeBusy(false)
      await closeReviewModal()
    }
  }, [reviewBatchDelete, reviewBatchExclude, reviewTotalMatched, appliedNlFilters, closeReviewModal])

  const goToNextReview = useCallback(() => {
    if (reviewQueue.length === 0) return
    if (reviewIndex >= reviewQueue.length - 1) {
      if (reviewMode === 'auto') {
        finalizeAutoReview()
      } else {
        closeReviewModal()
      }
      return
    }
    setReviewIndex((idx) => Math.min(idx + 1, reviewQueue.length - 1))
    setReviewPreviewFormat('web')
  }, [reviewIndex, reviewQueue.length, reviewMode, finalizeAutoReview, closeReviewModal])

  const goToPrevReview = useCallback(() => {
    if (reviewQueue.length === 0) return
    if (reviewIndex === 0) return
    setReviewIndex((idx) => Math.max(idx - 1, 0))
    setReviewPreviewFormat('web')
  }, [reviewIndex, reviewQueue.length])

  const ensureEmailPreview = useCallback(async (newsletterId) => {
    if (!newsletterId) return
    if (reviewRenderedContent.email) return
    try {
      const html = await APIService.adminNewsletterRender(newsletterId, 'email')
      setReviewRenderedContent((prev) => ({ ...prev, email: html, emailError: null }))
    } catch (error) {
      setReviewRenderedContent((prev) => ({ ...prev, email: '', emailError: error?.body || error.message || 'Failed to load email preview.' }))
    }
  }, [reviewRenderedContent.email])

  const queueExcludeId = useCallback((id) => {
    setReviewBatchExclude((prev) => (prev.includes(id) ? prev : [...prev, id]))
  }, [])

  const queueDeleteId = useCallback((id) => {
    setReviewBatchDelete((prev) => (prev.includes(id) ? prev : [...prev, id]))
  }, [])



  const changeReviewFormat = useCallback(async (format) => {
    const nextFormat = format === 'email' ? 'email' : 'web'
    setReviewPreviewFormat(nextFormat)
    const current = reviewQueue[reviewIndex]
    if (nextFormat === 'email' && current) {
      await ensureEmailPreview(current.id)
    }
  }, [ensureEmailPreview, reviewIndex, reviewQueue])

  const handlePublishReview = useCallback(async () => {
    const current = reviewQueue[reviewIndex]
    if (!current) return
    if (reviewMode === 'auto') {
      goToNextReview()
      return
    }
    try {
      setReviewLoadingDetail(true)
      await APIService.adminNewsletterUpdate(current.id, { published: true })
      reviewDirtyRef.current = true
      setMessage({ type: 'success', text: `Published newsletter #${current.id}.` })
      setReviewDetail((prev) => (prev && prev.id === current.id ? { ...prev, published: true } : prev))
      goToNextReview()
    } catch (error) {
      setMessage({ type: 'error', text: `Publish failed: ${error?.body?.error || error.message}` })
    } finally {
      setReviewLoadingDetail(false)
    }
  }, [reviewQueue, reviewIndex, reviewMode, goToNextReview, setMessage])

  const handleSkipReview = useCallback(() => {
    const current = reviewQueue[reviewIndex]
    if (!current) return
    if (reviewMode === 'auto') {
      queueExcludeId(current.id)
    }
    goToNextReview()
  }, [reviewQueue, reviewIndex, reviewMode, queueExcludeId, goToNextReview])

  const handleDeleteReview = useCallback(async () => {
    const current = reviewQueue[reviewIndex]
    if (!current) return
    if (reviewMode === 'auto') {
      queueDeleteId(current.id)
      queueExcludeId(current.id)
      goToNextReview()
      return
    }
    if (typeof window !== 'undefined') {
      setDeleteNewsletterConfirm({
        ids: [current.id],
        label: `newsletter #${current.id}`,
        resolve: async () => {
          try {
            setReviewLoadingDetail(true)
            await APIService.adminNewsletterDelete(current.id)
            reviewDirtyRef.current = true
            setMessage({ type: 'success', text: `Deleted newsletter #${current.id}.` })
            setReviewQueue((prev) => prev.filter((item) => item.id !== current.id))
            setReviewIndex((idx) => {
              const nextLength = reviewQueue.length - 1
              if (nextLength <= 0) return 0
              if (idx >= nextLength) return Math.max(0, nextLength - 1)
              return idx
            })
          } catch (error) {
            setMessage({ type: 'error', text: `Delete failed: ${error?.body?.error || error.message}` })
          } finally {
            setReviewLoadingDetail(false)
          }
        },
        trackBulk: false
      })
      return
    }
    try {
      setReviewLoadingDetail(true)
      await APIService.adminNewsletterDelete(current.id)
      reviewDirtyRef.current = true
      setMessage({ type: 'success', text: `Deleted newsletter #${current.id}.` })
      setReviewQueue((prev) => prev.filter((item) => item.id !== current.id))
      setReviewIndex((idx) => {
        const nextLength = reviewQueue.length - 1
        if (nextLength <= 0) return 0
        return Math.min(idx, nextLength - 1)
      })
      if (reviewQueue.length <= 1) {
        await closeReviewModal()
      }
    } catch (error) {
      setMessage({ type: 'error', text: `Delete failed: ${error?.body?.error || error.message}` })
    } finally {
      setReviewLoadingDetail(false)
    }
  }, [reviewQueue, reviewIndex, reviewMode, queueDeleteId, queueExcludeId, closeReviewModal, setMessage])

  const handleApproveAndNext = useCallback(() => {
    const current = reviewQueue[reviewIndex]
    if (!current) return
    goToNextReview()
  }, [reviewQueue, reviewIndex, goToNextReview])

  useEffect(() => {
    if (!reviewModalOpen) return
    const current = reviewQueue[reviewIndex]
    if (!current) return
    let cancelled = false
    const load = async () => {
      setReviewLoadingDetail(true)
      try {
        const detail = await APIService.adminNewsletterGet(current.id)
        if (cancelled) return
        setReviewDetail(detail)
      } catch (error) {
        if (cancelled) return
        setReviewDetail(null)
        setReviewRenderedContent({ web: '', email: '', webError: error?.body || error.message || 'Failed to load detail.', emailError: null })
        setReviewLoadingDetail(false)
        return
      }
      try {
        const html = await APIService.adminNewsletterRender(current.id, 'web')
        if (cancelled) return
        setReviewRenderedContent({ web: html, email: '', webError: null, emailError: null })
      } catch (error) {
        if (cancelled) return
        setReviewRenderedContent({ web: '', email: '', webError: error?.body || error.message || 'Failed to load preview.', emailError: null })
      } finally {
        if (!cancelled) setReviewLoadingDetail(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [reviewModalOpen, reviewIndex, reviewQueue])

  useEffect(() => {
    if (!reviewModalOpen) return
    const handler = (event) => {
      if (reviewFinalizeBusy || reviewLoadingDetail) return
      if (['ArrowRight', 'ArrowLeft', 'j', 'k', ' '].includes(event.key)) {
        event.preventDefault()
      }
      if (event.key === 'ArrowRight' || event.key.toLowerCase() === 'j') {
        goToNextReview()
      } else if (event.key === 'ArrowLeft' || event.key.toLowerCase() === 'k') {
        goToPrevReview()
      } else if (event.key === ' ') {
        if (reviewMode === 'auto') {
          goToNextReview()
        } else {
          handlePublishReview()
        }
      }
    }
    window.addEventListener('keydown', handler)
    return () => {
      window.removeEventListener('keydown', handler)
    }
  }, [reviewModalOpen, reviewMode, reviewFinalizeBusy, reviewLoadingDetail, goToNextReview, goToPrevReview, handlePublishReview])

  const startEditNewsletter = async (row) => {
    const full = await APIService.adminNewsletterGet(row.id)
    setEditingNl(full)
    setPreviewHtml('')
    setPreviewError('')
  }
  const saveNewsletter = async () => {
    if (!editingNl) return
    try {
      const payload = {
        title: editingNl.title,
        content_json: (() => { try { return typeof editingNl.content === 'string' ? JSON.parse(editingNl.content) : editingNl.content } catch { return editingNl.content } })(),
        published: !!editingNl.published,
        issue_date: editingNl.issue_date?.slice(0, 10),
        week_start_date: editingNl.week_start_date?.slice(0, 10),
        week_end_date: editingNl.week_end_date?.slice(0, 10),
      }
      await APIService.adminNewsletterUpdate(editingNl.id, payload)
      setMessage({ type: 'success', text: 'Newsletter updated' })
      setEditingNl(null)
      await refreshNewsletters()
    } catch (error) {
      setMessage({ type: 'error', text: `Save failed: ${error?.body?.error || error.message}` })
    }
  }
  const refreshPreview = useCallback(async () => {
    if (!editingNl) return
    try {
      const html = await APIService.adminNewsletterRender(
        editingNl.id,
        previewFormat === 'email' ? 'email' : 'web'
      )
      setPreviewHtml(html)
      setPreviewError('')
    } catch (error) {
      setPreviewHtml('')
      setPreviewError(`Failed to load preview: ${String(error.body || error.message || error)}`)
    }
  }, [editingNl, previewFormat])

  useEffect(() => {
    if (editingNl && editingNl.id) {
      refreshPreview()
    }
  }, [editingNl, previewFormat, refreshPreview])

  const loadNewsletterYoutubeLinks = async (newsletterId) => {
    try {
      const links = await APIService.adminNewsletterYoutubeLinksList(newsletterId)
      setNlYoutubeLinks(Array.isArray(links) ? links : [])
    } catch (error) {
      console.error('Failed to load YouTube links:', error)
      setNlYoutubeLinks([])
    }
  }

  const createNewsletterYoutubeLink = async () => {
    if (!editingNl || !nlYoutubeLinkForm.player_name || !nlYoutubeLinkForm.youtube_link) {
      setMessage({ type: 'error', text: 'Player name and YouTube link are required' })
      return
    }
    try {
      await APIService.adminNewsletterYoutubeLinkCreate(editingNl.id, {
        player_name: nlYoutubeLinkForm.player_name,
        youtube_link: nlYoutubeLinkForm.youtube_link,
        player_id: nlYoutubeLinkForm.player_id
      })
      setMessage({ type: 'success', text: 'YouTube link added' })
      setNlYoutubeLinkForm({ player_name: '', youtube_link: '', player_id: null })
      await loadNewsletterYoutubeLinks(editingNl.id)
    } catch (error) {
      setMessage({ type: 'error', text: `Failed to add YouTube link: ${error?.body?.error || error.message}` })
    }
  }

  const updateNewsletterYoutubeLink = async (linkId) => {
    if (!editingNl || !editingNlYoutubeLink || !editingNlYoutubeLink.youtube_link) {
      setMessage({ type: 'error', text: 'YouTube link is required' })
      return
    }
    try {
      await APIService.adminNewsletterYoutubeLinkUpdate(editingNl.id, linkId, {
        youtube_link: editingNlYoutubeLink.youtube_link
      })
      setMessage({ type: 'success', text: 'YouTube link updated' })
      setEditingNlYoutubeLink(null)
      await loadNewsletterYoutubeLinks(editingNl.id)
    } catch (error) {
      setMessage({ type: 'error', text: `Failed to update YouTube link: ${error?.body?.error || error.message}` })
    }
  }

  const deleteNewsletterYoutubeLink = async (linkId) => {
    if (!editingNl) return
    try {
      await APIService.adminNewsletterYoutubeLinkDelete(editingNl.id, linkId)
      setMessage({ type: 'success', text: 'YouTube link deleted' })
      await loadNewsletterYoutubeLinks(editingNl.id)
    } catch (error) {
      setMessage({ type: 'error', text: `Failed to delete YouTube link: ${error?.body?.error || error.message}` })
    }
  }

  const extractPlayersFromNewsletter = (newsletter) => {
    if (!newsletter) return []
    try {
      const content = typeof newsletter.content === 'string' ? JSON.parse(newsletter.content) : newsletter.content
      const enrichedContent = newsletter.enriched_content || content
      const players = []
      const sections = enrichedContent?.sections || []
      for (const section of sections) {
        const items = section?.items || []
        for (const item of items) {
          if (item.player_name) {
            players.push({
              player_name: item.player_name,
              player_id: item.player_id || null,
              loan_team: item.loan_team || item.loan_team_name || ''
            })
          }
        }
      }
      return players
    } catch {
      return []
    }
  }

  // Enhanced Newsletter Editor functions
  const updatePlayerInNewsletter = (sectionIndex, itemIndex, updatedItem) => {
    if (!editingNl) return
    try {
      const content = typeof editingNl.content === 'string' ? JSON.parse(editingNl.content) : editingNl.content
      const sections = content?.sections || []
      if (sections[sectionIndex] && sections[sectionIndex].items && sections[sectionIndex].items[itemIndex]) {
        sections[sectionIndex].items[itemIndex] = { ...sections[sectionIndex].items[itemIndex], ...updatedItem }
        setEditingNl({ ...editingNl, content: JSON.stringify(content, null, 2) })
        setEditingPlayerCard(null)
        setMessage({ type: 'success', text: 'Player updated' })
      }
    } catch (error) {
      console.error('Failed to update player:', error)
      setMessage({ type: 'error', text: 'Failed to update player' })
    }
  }

  const movePlayerInNewsletter = (fromSectionIdx, fromItemIdx, toSectionIdx, direction) => {
    if (!editingNl) return
    try {
      const content = typeof editingNl.content === 'string' ? JSON.parse(editingNl.content) : editingNl.content
      const sections = content?.sections || []

      if (!sections[fromSectionIdx] || !sections[fromSectionIdx].items || !sections[fromSectionIdx].items[fromItemIdx]) {
        setMessage({ type: 'error', text: 'Invalid source position' })
        return
      }

      const player = sections[fromSectionIdx].items[fromItemIdx]

      // Moving within same section
      if (fromSectionIdx === toSectionIdx) {
        const items = sections[fromSectionIdx].items
        const newIndex = direction === 'up' ? Math.max(0, fromItemIdx - 1) : Math.min(items.length - 1, fromItemIdx + 1)
        if (newIndex !== fromItemIdx) {
          items.splice(fromItemIdx, 1)
          items.splice(newIndex, 0, player)
          setEditingNl({ ...editingNl, content: JSON.stringify(content, null, 2) })
          setMessage({ type: 'success', text: 'Player moved' })
        }
      } else {
        // Moving to different section
        if (!sections[toSectionIdx] || !sections[toSectionIdx].items) {
          setMessage({ type: 'error', text: 'Invalid destination section' })
          return
        }
        sections[fromSectionIdx].items.splice(fromItemIdx, 1)
        sections[toSectionIdx].items.push(player)
        setEditingNl({ ...editingNl, content: JSON.stringify(content, null, 2) })
        setMessage({ type: 'success', text: `Player moved to ${sections[toSectionIdx].title || 'section'}` })
      }
    } catch (error) {
      console.error('Failed to move player:', error)
      setMessage({ type: 'error', text: 'Failed to move player' })
    }
  }

  const deletePlayerFromNewsletter = (sectionIndex, itemIndex) => {
    if (!editingNl) return
    setDeletePlayerFromNlConfirm({ sectionIndex, itemIndex })
  }

  const confirmDeletePlayerFromNewsletter = () => {
    if (!deletePlayerFromNlConfirm || !editingNl) return
    const { sectionIndex, itemIndex } = deletePlayerFromNlConfirm
    try {
      const content = typeof editingNl.content === 'string' ? JSON.parse(editingNl.content) : editingNl.content
      const sections = content?.sections || []
      if (sections[sectionIndex] && sections[sectionIndex].items) {
        sections[sectionIndex].items.splice(itemIndex, 1)
        setEditingNl({ ...editingNl, content: JSON.stringify(content, null, 2) })
        setMessage({ type: 'success', text: 'Player removed from newsletter' })
      }
      setDeletePlayerFromNlConfirm(null)
    } catch (error) {
      console.error('Failed to delete player:', error)
      setMessage({ type: 'error', text: 'Failed to delete player' })
      setDeletePlayerFromNlConfirm(null)
    }
  }

  useEffect(() => {
    if (editingNl && editingNl.id) {
      loadNewsletterYoutubeLinks(editingNl.id)
    } else {
      setNlYoutubeLinks([])
    }
  }, [editingNl?.id])

  // Players Hub functions
  const loadPlayersHub = async () => {
    if (!adminReady) return
    setPlayersHubLoading(true)
    try {
      const params = {
        page: playersHubPage,
        page_size: 50,
      }
      if (playersHubFilters.team_id) params.team_id = playersHubFilters.team_id
      if (playersHubFilters.search) params.search = playersHubFilters.search
      if (playersHubFilters.has_sofascore) params.has_sofascore = playersHubFilters.has_sofascore

      const data = await APIService.adminPlayersList(params)
      setPlayersHubData(data)

      // Load field options for the add player form
      try {
        const options = await APIService.adminPlayerFieldOptions()
        setPlayerFieldOptions({
          positions: options.positions || [],
          nationalities: options.nationalities || []
        })
      } catch (optionsError) {
        console.warn('Failed to load player field options:', optionsError)
        // Non-critical error, continue without options
      }
    } catch (error) {
      console.error('Failed to load players:', error)
      setMessage({ type: 'error', text: `Failed to load players: ${error?.body?.error || error.message}` })
    } finally {
      setPlayersHubLoading(false)
    }
  }

  const applyPlayersHubFilters = () => {
    setPlayersHubPage(1)
    loadPlayersHub()
  }

  const resetPlayersHubFilters = () => {
    setPlayersHubFilters({ team_id: '', search: '', has_sofascore: '' })
    setPlayersHubPage(1)
  }

  const updatePlayerSofascoreId = async (playerId, sofascoreId) => {
    try {
      const payload = { sofascore_id: sofascoreId || null }
      await APIService.adminPlayerUpdate(playerId, payload)
      setMessage({ type: 'success', text: 'Sofascore ID updated' })
      setEditingPlayerSofascore((prev) => {
        const next = { ...prev }
        delete next[playerId]
        return next
      })
      await loadPlayersHub()
    } catch (error) {
      setMessage({ type: 'error', text: `Update failed: ${error?.body?.error || error.message}` })
    }
  }

  const startInlinePlayerNameEdit = (player) => {
    setInlinePlayerNameEdits((prev) => ({
      ...prev,
      [player.player_id]: player.player_name || '',
    }))
  }

  const cancelInlinePlayerNameEdit = (playerId) => {
    setInlinePlayerNameEdits((prev) => {
      const next = { ...prev }
      delete next[playerId]
      return next
    })
    setInlinePlayerNameSaving((prev) => {
      if (!prev[playerId]) {
        return prev
      }
      const next = { ...prev }
      delete next[playerId]
      return next
    })
  }

  const saveInlinePlayerNameEdit = async (playerId) => {
    const draft = inlinePlayerNameEdits[playerId] ?? ''
    const playerRecord = playersHubData.items.find((p) => p.player_id === playerId)
    const currentName = playerRecord?.player_name || ''
    const trimmedDraft = typeof draft === 'string' ? draft.trim() : ''

    if (!trimmedDraft) {
      setMessage({ type: 'error', text: 'Player name cannot be empty' })
      return
    }

    const payloadInfo = buildPlayerNameUpdatePayload(playerId, draft, currentName)
    if (!payloadInfo) {
      setMessage({ type: 'warning', text: 'No changes to save' })
      cancelInlinePlayerNameEdit(playerId)
      return
    }

    setInlinePlayerNameSaving((prev) => ({ ...prev, [playerId]: true }))
    try {
      await APIService.adminPlayerUpdate(playerId, payloadInfo.payload)
      setMessage({ type: 'success', text: `Updated player name to "${payloadInfo.payload.name}"` })
      cancelInlinePlayerNameEdit(playerId)
      await loadPlayersHub()
    } catch (error) {
      setMessage({ type: 'error', text: `Failed to update player: ${error?.body?.error || error.message}` })
    } finally {
      setInlinePlayerNameSaving((prev) => {
        const next = { ...prev }
        delete next[playerId]
        return next
      })
    }
  }

  const togglePlayerSelection = (playerId) => {
    setSelectedPlayersForBulk((prev) => {
      if (prev.includes(playerId)) {
        return prev.filter((id) => id !== playerId)
      } else {
        return [...prev, playerId]
      }
    })
  }

  const toggleAllPlayersSelection = () => {
    if (selectedPlayersForBulk.length === playersHubData.items.length) {
      setSelectedPlayersForBulk([])
    } else {
      setSelectedPlayersForBulk(playersHubData.items.map((p) => p.player_id))
    }
  }

  const bulkUpdateSofascoreIds = async () => {
    if (selectedPlayersForBulk.length === 0) {
      setMessage({ type: 'error', text: 'No players selected' })
      return
    }

    const updates = selectedPlayersForBulk.map((playerId) => {
      const player = playersHubData.items.find((p) => p.player_id === playerId)
      const sofascoreValue = editingPlayerSofascore[playerId]
      return {
        player_id: playerId,
        player_name: player?.player_name,
        sofascore_id: sofascoreValue !== undefined ? (sofascoreValue || null) : player?.sofascore_id
      }
    })

    try {
      const result = await APIService.adminPlayerBulkUpdateSofascore(updates)
      const successCount = result.results?.updated?.length || 0
      const failCount = result.results?.failed?.length || 0

      if (failCount > 0) {
        setMessage({
          type: 'warning',
          text: `Bulk update: ${successCount} succeeded, ${failCount} failed. Check console for details.`
        })
      } else {
        setMessage({ type: 'success', text: `Bulk updated ${successCount} players` })
      }

      setSelectedPlayersForBulk([])
      setEditingPlayerSofascore({})
      setBulkSofascoreMode(false)
      await loadPlayersHub()
    } catch (error) {
      setMessage({ type: 'error', text: `Bulk update failed: ${error?.body?.error || error.message}` })
    }
  }

  const generateSeasonOptions = () => {
    const currentYear = new Date().getFullYear()
    const options = []
    // Generate last 3 seasons + current + next 2
    for (let i = -3; i <= 2; i++) {
      const startYear = currentYear + i
      const endYear = startYear + 1
      const endYearShort = String(endYear).slice(-2)
      options.push({
        value: `${startYear}-${endYearShort}::FULL`,
        label: `${startYear}-${endYear} (Full Season)`
      })
      options.push({
        value: `${startYear}-${endYearShort}::SUMMER`,
        label: `${startYear}-${endYear} (Summer Window)`
      })
      options.push({
        value: `${startYear}-${endYearShort}::WINTER`,
        label: `${startYear}-${endYear} (Winter Window)`
      })
    }
    return options
  }

  const createManualPlayer = async () => {
    if (!addPlayerForm.name.trim()) {
      setMessage({ type: 'error', text: 'Player name is required' })
      return
    }

    // Validate primary team
    if (!addPlayerForm.use_custom_primary_team && !addPlayerForm.primary_team_id) {
      setMessage({ type: 'error', text: 'Primary team is required (or check "Custom team")' })
      return
    }
    if (addPlayerForm.use_custom_primary_team && !addPlayerForm.custom_primary_team_name.trim()) {
      setMessage({ type: 'error', text: 'Custom primary team name is required' })
      return
    }

    // Validate loan team
    if (!addPlayerForm.use_custom_loan_team && !addPlayerForm.loan_team_id) {
      setMessage({ type: 'error', text: 'Loan team is required (or check "Custom team")' })
      return
    }
    if (addPlayerForm.use_custom_loan_team && !addPlayerForm.custom_loan_team_name.trim()) {
      setMessage({ type: 'error', text: 'Custom loan team name is required' })
      return
    }

    if (!addPlayerForm.window_key) {
      setMessage({ type: 'error', text: 'Season/window is required' })
      return
    }

    try {
      const payload = {
        name: addPlayerForm.name.trim(),
        firstname: addPlayerForm.firstname.trim() || null,
        lastname: addPlayerForm.lastname.trim() || null,
        position: addPlayerForm.position.trim() || null,
        nationality: addPlayerForm.nationality.trim() || null,
        age: addPlayerForm.age ? parseInt(addPlayerForm.age) : null,
        sofascore_id: addPlayerForm.sofascore_id ? parseInt(addPlayerForm.sofascore_id) : null,
        window_key: addPlayerForm.window_key
      }

      // Add primary team (either ID or custom name)
      if (addPlayerForm.use_custom_primary_team) {
        payload.custom_primary_team_name = addPlayerForm.custom_primary_team_name.trim()
      } else {
        payload.primary_team_id = parseInt(addPlayerForm.primary_team_id)
      }

      // Add loan team (either ID or custom name)
      if (addPlayerForm.use_custom_loan_team) {
        payload.custom_loan_team_name = addPlayerForm.custom_loan_team_name.trim()
      } else {
        payload.loan_team_id = parseInt(addPlayerForm.loan_team_id)
      }

      const result = await APIService.adminPlayerCreate(payload)
      setMessage({ type: 'success', text: result.message || `Player "${payload.name}" created successfully` })
      setShowAddPlayerForm(false)
      setAddPlayerForm({
        name: '',
        firstname: '',
        lastname: '',
        position: '',
        nationality: '',
        age: '',
        sofascore_id: '',
        primary_team_id: '',
        loan_team_id: '',
        window_key: '',
        use_custom_primary_team: false,
        custom_primary_team_name: '',
        use_custom_loan_team: false,
        custom_loan_team_name: ''
      })
      // Reload both players and field options
      await loadPlayersHub()
    } catch (error) {
      setMessage({ type: 'error', text: `Failed to create player: ${error?.body?.error || error.message}` })
    }
  }

  const openEditPlayerDialog = async (playerId) => {
    try {
      // Fetch full player details
      const playerData = await APIService.adminPlayerGet(playerId)

      // Get the first/primary loan record
      const primaryLoan = playerData.loans && playerData.loans.length > 0 ? playerData.loans[0] : null

      if (!primaryLoan) {
        setMessage({ type: 'error', text: 'No loan record found for this player' })
        return
      }

      // Populate form
      const isCustomPrimaryTeam = !primaryLoan.primary_team_id
      const isCustomLoanTeam = !primaryLoan.loan_team_id

      setEditPlayerForm({
        name: playerData.name || '',
        position: playerData.position || '',
        nationality: playerData.nationality || '',
        age: playerData.age || '',
        sofascore_id: playerData.sofascore_id || '',
        primary_team_id: primaryLoan.primary_team_id || '',
        loan_team_id: primaryLoan.loan_team_id || '',
        use_custom_primary_team: isCustomPrimaryTeam,
        custom_primary_team_name: isCustomPrimaryTeam ? primaryLoan.primary_team_name : '',
        use_custom_loan_team: isCustomLoanTeam,
        custom_loan_team_name: isCustomLoanTeam ? primaryLoan.loan_team_name : '',
        window_key: primaryLoan.window_key || ''
      })

      setEditingPlayerDialog({ player: playerData, loan: primaryLoan })
    } catch (error) {
      setMessage({ type: 'error', text: `Failed to load player: ${error?.body?.error || error.message}` })
    }
  }

  const savePlayerEdit = async () => {
    if (!editingPlayerDialog) return

    try {
      const { player, loan } = editingPlayerDialog

      // Update Player record
      const playerPayload = {
        name: editPlayerForm.name.trim(),
        position: editPlayerForm.position.trim() || null,
        nationality: editPlayerForm.nationality.trim() || null,
        age: editPlayerForm.age ? parseInt(editPlayerForm.age) : null,
        sofascore_id: editPlayerForm.sofascore_id ? parseInt(editPlayerForm.sofascore_id) : null
      }

      await APIService.adminPlayerUpdate(player.player_id, playerPayload)

      // Update LoanedPlayer record (teams)
      const loanPayload = {
        player_name: editPlayerForm.name.trim(),
        window_key: editPlayerForm.window_key
      }

      // Handle primary team
      if (editPlayerForm.use_custom_primary_team) {
        loanPayload.primary_team_name = editPlayerForm.custom_primary_team_name.trim()
        // Set team_id to null for custom teams
        loanPayload.primary_team_db_id = null
      } else if (editPlayerForm.primary_team_id) {
        loanPayload.primary_team_db_id = parseInt(editPlayerForm.primary_team_id)
      }

      // Handle loan team
      if (editPlayerForm.use_custom_loan_team) {
        loanPayload.loan_team_name = editPlayerForm.custom_loan_team_name.trim()
        // Set team_id to null for custom teams
        loanPayload.loan_team_db_id = null
      } else if (editPlayerForm.loan_team_id) {
        loanPayload.loan_team_db_id = parseInt(editPlayerForm.loan_team_id)
      }

      await APIService.adminLoanUpdate(loan.id, loanPayload)

      setMessage({ type: 'success', text: `Player "${editPlayerForm.name}" updated successfully` })
      setEditingPlayerDialog(null)
      await loadPlayersHub()
    } catch (error) {
      setMessage({ type: 'error', text: `Failed to update player: ${error?.body?.error || error.message}` })
    }
  }

  const deletePlayer = async (playerId, playerName, loanCount) => {
    const isManual = playerId < 0
    const playerType = isManual ? 'manual player' : 'player'
    const warningMessage = loanCount > 0
      ? `This will remove ${loanCount} loan record(s), any associated YouTube links, and remove the player from all tracking.`
      : `This ${playerType} will be permanently removed from tracking.`

    setDeletePlayerConfirm({
      playerId,
      playerName,
      warningMessage,
      isManual,
      loanCount
    })
  }

  const confirmDeletePlayer = async () => {
    if (!deletePlayerConfirm) return
    const { playerId, playerName } = deletePlayerConfirm

    try {
      const result = await APIService.adminPlayerDelete(playerId)
      const deletedInfo = result.deleted || {}
      const details = []
      if (deletedInfo.loaned_records > 0) details.push(`${deletedInfo.loaned_records} loan record(s)`)
      if (deletedInfo.youtube_links > 0) details.push(`${deletedInfo.youtube_links} YouTube link(s)`)
      if (deletedInfo.player_record) details.push('player record')

      const detailsText = details.length > 0 ? ` (removed: ${details.join(', ')})` : ''
      setMessage({ type: 'success', text: `Player "${playerName}" deleted successfully${detailsText}` })
      setDeletePlayerConfirm(null)
      await loadPlayersHub()
    } catch (error) {
      setMessage({ type: 'error', text: `Failed to delete player: ${error?.body?.error || error.message}` })
    }
  }

  useEffect(() => {
    if (adminReady && playersHubPage) {
      loadPlayersHub()
    }
  }, [adminReady, playersHubPage])

  // Sandbox task loading functions (from AdminSandboxPage)
  const buildSandboxDefaults = useCallback((taskList) => {
    const defaults = {}
    for (const task of taskList) {
      const params = task?.parameters || []
      defaults[task.task_id] = params.reduce((acc, param) => {
        if (param.type === 'checkbox') {
          acc[param.name] = false
        } else {
          acc[param.name] = ''
        }
        return acc
      }, {})
    }
    return defaults
  }, [])

  const ensureAdminSession = useCallback(() => {
    const storedToken = APIService.userToken || (typeof localStorage !== 'undefined' ? localStorage.getItem('academy_watch_user_token') : null)
    if (storedToken && !APIService.userToken) {
      APIService.setUserToken(storedToken)
    }
    if (!storedToken) {
      const err = new Error('Admin login required. Sign in with an admin email to continue.')
      err.code = 'missing_token'
      throw err
    }
    const storedKey = APIService.adminKey || (typeof localStorage !== 'undefined' ? localStorage.getItem('academy_watch_admin_key') : null)
    if (storedKey && !APIService.adminKey) {
      APIService.setAdminKey(storedKey)
    }
    if (!storedKey) {
      const err = new Error('Admin API key required. Add your key in the admin dashboard.')
      err.code = 'missing_key'
      throw err
    }
  }, [])

  const loadSandboxTasks = useCallback(async () => {
    setSandboxLoading(true)
    setSandboxError('')
    try {
      ensureAdminSession()

      let payload
      try {
        payload = await APIService.adminSandboxTasks()
      } catch (err) {
        if (err?.status === 401) {
          await APIService.refreshProfile()
          ensureAdminSession()
          payload = await APIService.adminSandboxTasks()
        } else {
          throw err
        }
      }
      const taskList = Array.isArray(payload?.tasks) ? payload.tasks : []
      setSandboxTasks(taskList)
      setSandboxCollapsedTasks((prev) => mergeCollapseState(prev, taskList))
      setSandboxFormValues((prev) => ({ ...buildSandboxDefaults(taskList), ...prev }))
    } catch (err) {
      setSandboxError(err?.message || 'Failed to load sandbox tasks')
    } finally {
      setSandboxLoading(false)
    }
  }, [buildSandboxDefaults, ensureAdminSession])

  useEffect(() => {
    if (!includeSandbox) return
    if (activeTab === 'tools' && hasAdminAccess) {
      loadSandboxTasks()
    }
  }, [activeTab, hasAdminAccess, loadSandboxTasks, includeSandbox])

  const toggleSandboxTaskCollapsed = useCallback((taskId) => {
    setSandboxCollapsedTasks((prev) => toggleCollapseState(prev, taskId))
  }, [])

  const handleSandboxInputChange = useCallback((taskId, fieldName, fieldType) => (event) => {
    const value = fieldType === 'checkbox' ? event.target.checked : event.target.value
    setSandboxFormValues((prev) => ({
      ...prev,
      [taskId]: {
        ...(prev[taskId] || {}),
        [fieldName]: value,
      },
    }))
  }, [])

  const handleSandboxSelectChange = useCallback((taskId, param, option, params) => {
    setSandboxFormValues((prev) => {
      const updates = buildSelectUpdates(param, option, params)
      if (!updates || Object.keys(updates).length === 0) {
        return prev
      }
      const nextTaskValues = { ...(prev[taskId] || {}) }
      for (const [key, value] of Object.entries(updates)) {
        nextTaskValues[key] = value
      }
      return { ...prev, [taskId]: nextTaskValues }
    })
  }, [])

  const buildSandboxPayload = useCallback((task) => {
    const params = task?.parameters || []
    const currentValues = sandboxFormValues[task.task_id] || {}
    const payload = {}
    for (const param of params) {
      const rawValue = currentValues[param.name]
      if (param.type === 'checkbox') {
        payload[param.name] = !!rawValue
        continue
      }
      if (rawValue === '' || typeof rawValue === 'undefined' || rawValue === null) {
        continue
      }
      if (param.type === 'number') {
        const numeric = Number(rawValue)
        if (!Number.isNaN(numeric)) {
          payload[param.name] = numeric
        }
      } else {
        payload[param.name] = rawValue
      }
    }
    return payload
  }, [sandboxFormValues])

  const runSandboxTask = useCallback(async (task) => {
    if (!task?.task_id) return
    setRunningTaskId(task.task_id)
    try {
      const payload = buildSandboxPayload(task)
      ensureAdminSession()
      let result
      try {
        result = await APIService.adminSandboxRun(task.task_id, payload)
      } catch (err) {
        if (err?.status === 401) {
          await APIService.refreshProfile()
          ensureAdminSession()
          result = await APIService.adminSandboxRun(task.task_id, payload)
        } else {
          throw err
        }
      }
      if (task.task_id === 'list-missing-sofascore-ids') {
        const players = Array.isArray(result?.payload?.players) ? result.payload.players : []
        const enriched = players.map((player, index) => ({
          ...player,
          __row_key: sofascoreRowKey(player, index),
        }))
        const inputDefaults = {}
        for (const player of enriched) {
          const rowKey = player.__row_key
          inputDefaults[rowKey] = player?.sofascore_id ? String(player.sofascore_id) : ''
        }
        setSofascorePlayers(enriched)
        setSofascoreInputs(inputDefaults)
        setSofascoreStatus(null)
        setSofascoreUpdatingKey(null)
      }
      if (task.task_id === 'update-player-sofascore-id') {
        setSofascoreStatus({ type: 'success', message: result?.summary || 'Sofascore id updated.' })
      }
      setSandboxResults((prev) => ({
        ...prev,
        [task.task_id]: { status: 'ok', result },
      }))
    } catch (err) {
      if (task?.task_id === 'update-player-sofascore-id') {
        setSofascoreStatus({ type: 'error', message: err?.message || 'Failed to update Sofascore id.' })
      }
      setSandboxResults((prev) => ({
        ...prev,
        [task.task_id]: {
          status: 'error',
          message: err?.message || 'Task execution failed',
          detail: err?.body,
        },
      }))
    } finally {
      setRunningTaskId(null)
    }
  }, [buildSandboxPayload, ensureAdminSession])

  const handleSofascoreAssign = useCallback(async (row, inputValue) => {
    const payload = buildSofascoreUpdatePayload(row, typeof inputValue === 'string' ? inputValue.trim() : inputValue)
    if (!payload) {
      setSofascoreStatus({ type: 'error', message: 'Unable to update Sofascore id for this row.' })
      return
    }

    const rowKey = row?.__row_key || sofascoreRowKey(row)
    setSofascoreStatus(null)
    setSofascoreUpdatingKey(rowKey)
    try {
      ensureAdminSession()
      const result = await APIService.adminSandboxRun('update-player-sofascore-id', payload)
      setSofascoreStatus({ type: 'success', message: result?.summary || 'Sofascore id updated.' })
      setSofascorePlayers((prev) => prev.filter((item) => (item.__row_key || sofascoreRowKey(item)) !== rowKey))
      setSofascoreInputs((prev) => {
        const next = { ...prev }
        delete next[rowKey]
        return next
      })
    } catch (err) {
      setSofascoreStatus({ type: 'error', message: err?.message || 'Failed to update Sofascore id.' })
    } finally {
      setSofascoreUpdatingKey(null)
    }
  }, [ensureAdminSession])

  const handleSupplementalDelete = useCallback(async (row) => {
    if (!row?.supplemental_id) return
    const rowKey = row?.__row_key || sofascoreRowKey(row)
    setSofascoreStatus(null)
    setSofascoreUpdatingKey(rowKey)
    try {
      ensureAdminSession()
      const result = await APIService.adminSandboxRun('delete-supplemental-loan', {
        supplemental_id: row.supplemental_id,
        confirm: true,
      })
      setSofascoreStatus({ type: 'success', message: result?.summary || 'Supplemental row deleted.' })
      setSofascorePlayers((prev) => prev.filter((item) => (item.__row_key || sofascoreRowKey(item)) !== rowKey))
      setSofascoreInputs((prev) => {
        const next = { ...prev }
        delete next[rowKey]
        return next
      })
    } catch (err) {
      setSofascoreStatus({ type: 'error', message: err?.message || 'Failed to delete supplemental loan.' })
    } finally {
      setSofascoreUpdatingKey(null)
    }
  }, [ensureAdminSession])

  const loadSubscriberStats = useCallback(async () => {
    const startedAt = Date.now()
    const debugRequestId = (typeof crypto !== 'undefined' && crypto.randomUUID)
      ? crypto.randomUUID()
      : `sub-stats-${startedAt.toString(36)}-${Math.random().toString(36).slice(2, 8)}`
    const params = {
      search: subscriberSearch,
      sort: subscriberSort
    }
    console.info(`[subscriber-stats:${debugRequestId}] fetching`, params)
    setSubscriberStatsLoading(true)
    try {
      ensureAdminSession()
      const data = await APIService.getSubscriberStats(params, { requestId: debugRequestId })
      setSubscriberStats(data || { teams: [], total_subscribers: 0 })
      console.info(`[subscriber-stats:${debugRequestId}] success`, {
        durationMs: Date.now() - startedAt,
        teamCount: data?.teams?.length ?? 0,
        totalSubscribers: data?.total_subscribers ?? 0,
        serverRequestId: data?.request_id,
      })
    } catch (err) {
      const duration = Date.now() - startedAt
      const serverDetail = typeof err?.body === 'string'
        ? err.body
        : err?.body?.detail || err?.body?.error || err?.body?.message
      const serverRequestId = err?.body?.request_id || err?.body?.reference
      console.error(`[subscriber-stats:${debugRequestId}] failed`, {
        params,
        durationMs: duration,
        status: err?.status,
        serverRequestId,
        body: err?.body,
        message: err?.message,
        stack: err?.stack,
      })
      const readableDetail = serverDetail || err?.message
      const messageText = [
        'Failed to load subscriber statistics',
        readableDetail ? `(${readableDetail})` : null,
        serverRequestId ? `ref ${serverRequestId}` : `ref ${debugRequestId}`
      ].filter(Boolean).join(' ')
      setMessage({ type: 'error', text: messageText })
    } finally {
      setSubscriberStatsLoading(false)
    }
  }, [ensureAdminSession, subscriberSearch, subscriberSort])

  const handleToggleNewsletterStatus = useCallback(async (teamId, currentStatus) => {
    setToggleStatusBusy((prev) => ({ ...prev, [teamId]: true }))
    try {
      ensureAdminSession()
      await APIService.toggleNewsletterStatus(teamId, !currentStatus)
      // Reload stats
      await loadSubscriberStats()
      setMessage({ type: 'success', text: 'Newsletter status updated successfully' })
    } catch (err) {
      console.error('Failed to toggle newsletter status:', err)
      setMessage({ type: 'error', text: 'Failed to update newsletter status' })
    } finally {
      setToggleStatusBusy((prev) => ({ ...prev, [teamId]: false }))
    }
  }, [ensureAdminSession, loadSubscriberStats])

  // Load subscriber stats when tab changes to newsletters
  useEffect(() => {
    if (activeTab === 'newsletters' && hasAdminAccess) {
      loadSubscriberStats()
    }
  }, [activeTab, hasAdminAccess, loadSubscriberStats])

  return (
    <div className="max-w-6xl mx-auto py-6 sm:px-6 lg:px-8">
      <div className="px-4 py-6 sm:px-0 space-y-6">
        <h1 className="text-3xl font-bold">Admin</h1>
        {message && (
          <div
            className={`p-3 rounded ${message.type === 'error'
              ? 'bg-rose-50 text-rose-800'
              : message.type === 'warning'
                ? 'bg-amber-50 text-amber-800'
                : 'bg-emerald-50 text-emerald-800'}`}
          >
            {message.text}
          </div>
        )}
        {adminWarning && (
          <Alert className="border-amber-200 bg-amber-50 text-amber-900">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{adminWarning}</AlertDescription>
          </Alert>
        )}

        <div className="space-y-6">
          <div id="admin-access" className="rounded-lg border bg-card/80 p-4 shadow-sm space-y-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold flex items-center gap-2">
                  {adminReady ? (
                    <ShieldCheck className="h-4 w-4 text-emerald-600" />
                  ) : (
                    <ShieldAlert className="h-4 w-4 text-amber-600" />
                  )}
                  Admin Access
                </h2>
                <p className="text-sm text-muted-foreground">
                  Complete both steps to unlock the management console.
                </p>
              </div>
              <Badge variant={adminReady ? 'default' : 'secondary'}>
                {adminReady ? 'Ready' : 'Action needed'}
              </Badge>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              {accessChecklist.map(({ key, label, ok, description }) => (
                <div
                  key={key}
                  className={`flex items-start gap-3 rounded-md border p-3 ${ok ? 'border-emerald-200/80 bg-emerald-50/70' : 'border-amber-200/70 bg-amber-50/70'}`}
                >
                  {ok ? (
                    <CheckCircle className="mt-0.5 h-4 w-4 text-emerald-600" />
                  ) : (
                    <AlertCircle className="mt-0.5 h-4 w-4 text-amber-600" />
                  )}
                  <div>
                    <div className="text-sm font-medium">{label}</div>
                    <p className="text-xs text-muted-foreground">{description}</p>
                  </div>
                </div>
              ))}
            </div>
            {!adminReady && (
              <div className="flex flex-wrap gap-2 pt-2">
                {!hasAdminToken
                  ? (
                    authToken
                      ? (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            triggerLogout({ clearAdminKey: true })
                            setIsAdmin(false)
                          }}
                        >
                          Log out
                        </Button>
                      )
                      : (
                        <Button size="sm" onClick={openLoginModal}>
                          <LogIn className="mr-1 h-4 w-4" /> Sign in as admin
                        </Button>
                      )
                  ) : null}
                {hasAdminToken && !hasStoredKey && !editingKey && (
                  <Button size="sm" variant="outline" onClick={startEditingKey}>
                    <KeyRound className="mr-1 h-4 w-4" /> Add API key
                  </Button>
                )}
              </div>
            )}
          </div>

          {hasAdminToken && (
            <div id="admin-api" className="rounded-lg border bg-card/90 p-4 shadow-sm space-y-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold flex items-center gap-2">
                    <KeyRound className="h-4 w-4 text-primary" />
                    API Key
                  </h2>
                  <p className="text-sm text-muted-foreground">
                    Stored locally; only sent when you trigger an admin action.
                  </p>
                </div>
                {hasStoredKey && !editingKey && (
                  <Button size="sm" variant="ghost" type="button" onClick={() => setShowKeyValue(v => !v)}>
                    {showKeyValue ? 'Hide key' : 'Reveal key'}
                  </Button>
                )}
              </div>
              {hasStoredKey && !editingKey ? (
                <div className="rounded-md border bg-muted/40 p-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <code className="font-mono text-sm break-all">
                    {showKeyValue ? adminKey : maskedKey}
                  </code>
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" variant="secondary" type="button" onClick={startEditingKey}>Replace</Button>
                    <Button size="sm" variant="ghost" type="button" onClick={clearKey}>Clear</Button>
                  </div>
                </div>
              ) : (
                <form
                  className="space-y-4"
                  onSubmit={async (event) => {
                    event.preventDefault()
                    await saveKey()
                  }}
                >
                  <div className="space-y-2">
                    <Label htmlFor="admin-key-input" className="text-sm font-medium">Admin API key</Label>
                    <Input
                      id="admin-key-input"
                      className="h-11 font-mono"
                      type={showKeyValue ? 'text' : 'password'}
                      value={adminKeyInput}
                      onChange={(e) => setAdminKeyInput(e.target.value)}
                      placeholder="Paste the admin API key"
                      autoComplete="off"
                      autoCapitalize="none"
                      autoCorrect="off"
                      spellCheck="false"
                    />
                  </div>
                  <div className="flex flex-wrap items-center gap-3">
                    <Button type="submit" className="h-11 px-6" disabled={validatingKey}>
                      {validatingKey ? 'Validating\u2026' : 'Save key'}
                    </Button>
                    {hasStoredKey && (
                      <Button
                        type="button"
                        variant="ghost"
                        className="h-11"
                        onClick={() => {
                          setEditingKey(false)
                          setAdminKeyInput('')
                          setShowKeyValue(false)
                        }}
                      >
                        Cancel
                      </Button>
                    )}
                    <Button type="button" variant="ghost" className="h-11" onClick={() => setShowKeyValue(v => !v)}>
                      {showKeyValue ? 'Hide' : 'Show'}
                    </Button>
                  </div>
                </form>
              )}
            </div>
          )}
        </div>

        {hasAdminAccess ? (
          <>
            <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
              {!hideTabs && (
                <TabsList
                  className="grid w-full mb-4"
                  style={{ gridTemplateColumns: `repeat(${adminTabs.length}, minmax(0, 1fr))` }}
                >
                  {adminTabs.includes('newsletters') && <TabsTrigger value="newsletters">Newsletters</TabsTrigger>}
                  {adminTabs.includes('loans') && <TabsTrigger value="loans">Loans</TabsTrigger>}
                  {adminTabs.includes('tools') && <TabsTrigger value="tools">Tools</TabsTrigger>}
                  {adminTabs.includes('settings') && <TabsTrigger value="settings">Settings</TabsTrigger>}
                </TabsList>
              )}

              <TabsContent value="newsletters" className="space-y-6">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {/* Newsletter Generation Card */}
                  <Card id="admin-runs" className="md:col-span-2">
                    <CardHeader>
                      <CardTitle className="flex items-center justify-between">
                        <span>Newsletter Generation</span>
                        {running && (
                          <Badge variant="secondary" className="flex items-center gap-1">
                            <Loader2 className="h-3 w-3 animate-spin" />
                            Running…
                          </Badge>
                        )}
                      </CardTitle>
                      <CardDescription>
                        Generate weekly newsletters for selected teams or all tracked teams
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      {/* Date Selection */}
                      <div className="flex flex-col gap-2">
                        <Label htmlFor="run-date">Target Date</Label>
                        <Input
                          id="run-date"
                          type="date"
                          value={runDate}
                          onChange={(e) => setRunDate(e.target.value)}
                          className="w-full max-w-xs"
                        />
                      </div>

                      {/* Team Selection */}
                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <Label>Select Teams</Label>
                          {selectedRunTeams.length > 0 && (
                            <div className="flex items-center gap-2">
                              <Badge variant="secondary">{selectedRunTeams.length} selected</Badge>
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => setSelectedRunTeams([])}
                                disabled={running || teamRunBusy}
                              >
                                Clear
                              </Button>
                            </div>
                          )}
                        </div>
                        <TeamMultiSelect
                          teams={runTeams}
                          value={selectedRunTeams}
                          onChange={setSelectedRunTeams}
                          placeholder="Search and select teams…"
                          disabled={running || teamRunBusy}
                        />
                        {selectedRunTeams.length === 0 && (
                          <Alert>
                            <AlertCircle className="h-4 w-4" />
                            <AlertDescription>
                              Select at least one team to generate newsletters, or use "Generate for All Teams" below
                            </AlertDescription>
                          </Alert>
                        )}
                      </div>

                      {/* Action Buttons */}
                      <div className="flex flex-col gap-2 pt-2 border-t">
                        <div className="flex items-center gap-2 flex-wrap">
                          <Button
                            onClick={async () => {
                              if (!selectedRunTeams.length) return
                              setTeamRunBusy(true)
                              setTeamRunMsg(null)
                              const d = runDate || new Date().toISOString().slice(0, 10)
                              let ok = 0, errs = 0
                              for (const tid of selectedRunTeams) {
                                try {
                                  await APIService.generateNewsletter({ team_id: tid, target_date: d, type: 'weekly' })
                                  ok++
                                } catch {
                                  errs++
                                }
                              }
                              setTeamRunMsg({ type: errs ? 'error' : 'success', text: `Generated: ${ok} ok, ${errs} errors` })
                              setTeamRunBusy(false)
                            }}
                            disabled={teamRunBusy || selectedRunTeams.length === 0 || running}
                            size="default"
                          >
                            {teamRunBusy ? (
                              <>
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                Generating…
                              </>
                            ) : (
                              <>
                                Generate for Selected Teams ({selectedRunTeams.length})
                              </>
                            )}
                          </Button>

                          <Button
                            onClick={handleRunAllClick}
                            variant="destructive"
                            disabled={running || teamRunBusy}
                            size="default"
                          >
                            {running ? (
                              <>
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                Running…
                              </>
                            ) : (
                              'Generate for All Teams'
                            )}
                          </Button>
                        </div>
                        {running && (
                          <Alert>
                            <Loader2 className="h-4 w-4 animate-spin" />
                            <AlertDescription>
                              Processing newsletter generation for all teams. This process cannot be cancelled but can be paused.
                            </AlertDescription>
                          </Alert>
                        )}
                      </div>

                      {/* Results/Status Messages */}
                      {teamRunMsg && (
                        <Alert variant={teamRunMsg.type === 'error' ? 'destructive' : 'default'}>
                          <AlertDescription>{teamRunMsg.text}</AlertDescription>
                        </Alert>
                      )}

                      {/* Run History */}
                      <div className="mt-4 space-y-2">
                        <div className="flex items-center justify-between">
                          <Label>Recent Runs</Label>
                          <Button size="sm" variant="ghost" onClick={refreshRunHistory} disabled={running}>
                            Refresh
                          </Button>
                        </div>
                        {runHistory.length === 0 ? (
                          <p className="text-sm text-muted-foreground">No recent runs.</p>
                        ) : (
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                            <div className="border rounded">
                              <div className="px-2 py-1 text-xs font-semibold bg-secondary border-b">Newsletter Runs</div>
                              <div className="max-h-48 overflow-auto">
                                <table className="w-full text-xs">
                                  <thead>
                                    <tr className="text-left">
                                      <th className="p-2">Time</th>
                                      <th className="p-2">Info</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {runHistory.filter(r => (r.kind || '').startsWith('newsletter')).slice(0, 20).map((r, i) => (
                                      <tr key={i} className="border-t">
                                        <td className="p-2 whitespace-nowrap">{r.ts?.replace('T', ' ').slice(0, 19) || ''}</td>
                                        <td className="p-2 truncate">{r.message || r.text || r.detail || ''}</td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            </div>
                            <div className="border rounded">
                              <div className="px-2 py-1 text-xs font-semibold bg-secondary border-b">Seeding Runs</div>
                              <div className="max-h-48 overflow-auto">
                                <table className="w-full text-xs">
                                  <thead>
                                    <tr className="text-left">
                                      <th className="p-2">Time</th>
                                      <th className="p-2">Type</th>
                                      <th className="p-2">Details</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {runHistory.filter(r => ['seed-top5', 'seed-team', 'seed-top5-dry'].includes(r.kind)).slice(0, 20).map((r, i) => (
                                      <tr key={i} className="border-t">
                                        <td className="p-2 whitespace-nowrap">{r.ts?.replace('T', ' ').slice(0, 19) || ''}</td>
                                        <td className="p-2 whitespace-nowrap">{r.kind}</td>
                                        <td className="p-2 truncate">
                                          {r.season ? `Szn ${r.season}` : ''} {r.window_key ? `• ${r.window_key}` : ''} {r.team_db_id ? `• team_db_id=${r.team_db_id}` : ''} {r.api_team_id ? `• api_id=${r.api_team_id}` : ''}
                                          {r.message ? ` • ${r.message}` : ''}
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            </div>
                          </div>
                        )}
                      </div>

                      {/* Pause/Resume Toggle */}
                      <div className="flex items-center gap-2 pt-2 border-t">
                        <Label className="text-sm">Runs paused:</Label>
                        <Button variant={runStatus ? 'default' : 'outline'} onClick={toggleRun} disabled={running} size="sm">
                          {runStatus ? 'Resume' : 'Pause'}
                        </Button>
                      </div>
                    </CardContent>
                  </Card>

                  {/* Subscriber Analytics Card */}
                  <Card className="md:col-span-2">
                    <CardHeader>
                      <CardTitle>Team Subscriber Analytics</CardTitle>
                      <CardDescription>
                        Track which teams have subscribers to inform newsletter generation decisions
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      {/* Search and Sort Controls */}
                      <div className="flex flex-col sm:flex-row gap-2">
                        <div className="flex-1">
                          <Input
                            placeholder="Search teams..."
                            value={subscriberSearch}
                            onChange={(e) => setSubscriberSearch(e.target.value)}
                            className="w-full"
                          />
                        </div>
                        <div className="flex gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setSubscriberSort(subscriberSort === 'desc' ? 'asc' : 'desc')}
                          >
                            Sort: {subscriberSort === 'desc' ? 'High to Low' : 'Low to High'}
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={loadSubscriberStats}
                            disabled={subscriberStatsLoading}
                          >
                            {subscriberStatsLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Refresh'}
                          </Button>
                        </div>
                      </div>

                      {/* Summary Stats */}
                      <div className="flex items-center gap-4 p-3 bg-muted rounded-lg">
                        <div className="flex items-center gap-2">
                          <Users className="h-5 w-5 text-muted-foreground" />
                          <div>
                            <p className="text-sm text-muted-foreground">Total Subscribers</p>
                            <p className="text-2xl font-bold">{subscriberStats.total_subscribers}</p>
                          </div>
                        </div>
                        <div className="h-10 w-px bg-border" />
                        <div>
                          <p className="text-sm text-muted-foreground">Teams with Subscribers</p>
                          <p className="text-2xl font-bold">{subscriberStats.teams.filter(t => t.subscriber_count > 0).length}</p>
                        </div>
                        <div className="h-10 w-px bg-border" />
                        <div>
                          <p className="text-sm text-muted-foreground">Active Newsletters</p>
                          <p className="text-2xl font-bold">{subscriberStats.teams.filter(t => t.newsletters_active).length}</p>
                        </div>
                      </div>

                      {/* Teams List */}
                      {subscriberStatsLoading ? (
                        <div className="flex items-center justify-center py-8">
                          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                        </div>
                      ) : subscriberStats.teams.length === 0 ? (
                        <div className="text-center py-8 text-muted-foreground">
                          No teams found
                        </div>
                      ) : (
                        <div className="border rounded-lg overflow-hidden">
                          <div className="max-h-96 overflow-y-auto">
                            <table className="w-full text-sm">
                              <thead className="bg-muted sticky top-0">
                                <tr className="border-b">
                                  <th className="px-4 py-3 text-left font-medium">Team</th>
                                  <th className="px-4 py-3 text-center font-medium">Subscribers</th>
                                  <th className="px-4 py-3 text-center font-medium">Active</th>
                                  <th className="px-4 py-3 text-center font-medium">Status</th>
                                  <th className="px-4 py-3 text-center font-medium">Actions</th>
                                </tr>
                              </thead>
                              <tbody>
                                {subscriberStats.teams
                                  .filter(team => !subscriberSearch || team.name.toLowerCase().includes(subscriberSearch.toLowerCase()))
                                  .map((team) => (
                                    <tr key={team.id} className="border-b hover:bg-muted/50">
                                      <td className="px-4 py-3">
                                        <div className="flex items-center gap-2">
                                          {team.logo && (
                                            <img src={team.logo} alt="" className="h-6 w-6 object-contain" />
                                          )}
                                          <span className="font-medium">{team.name}</span>
                                        </div>
                                      </td>
                                      <td className="px-4 py-3 text-center">
                                        <Badge variant="secondary">
                                          {team.active_subscriber_count} / {team.subscriber_count}
                                        </Badge>
                                      </td>
                                      <td className="px-4 py-3 text-center">
                                        {team.latest_newsletter_date ? (
                                          <span className="text-xs text-muted-foreground">
                                            {new Date(team.latest_newsletter_date).toLocaleDateString()}
                                          </span>
                                        ) : (
                                          <span className="text-xs text-muted-foreground">—</span>
                                        )}
                                      </td>
                                      <td className="px-4 py-3 text-center">
                                        {team.newsletters_active ? (
                                          <Badge variant="default" className="bg-emerald-600">Active</Badge>
                                        ) : (
                                          <Badge variant="outline">Inactive</Badge>
                                        )}
                                      </td>
                                      <td className="px-4 py-3 text-center">
                                        <Button
                                          size="sm"
                                          variant={team.newsletters_active ? "destructive" : "default"}
                                          onClick={() => handleToggleNewsletterStatus(team.id, team.newsletters_active)}
                                          disabled={toggleStatusBusy[team.id]}
                                        >
                                          {toggleStatusBusy[team.id] ? (
                                            <Loader2 className="h-3 w-3 animate-spin" />
                                          ) : team.newsletters_active ? (
                                            'Deactivate'
                                          ) : (
                                            'Activate'
                                          )}
                                        </Button>
                                      </td>
                                    </tr>
                                  ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      )}

                      <Alert>
                        <AlertCircle className="h-4 w-4" />
                        <AlertDescription>
                          Newsletter generation is resource-intensive. Activate newsletters for teams with sufficient subscriber interest.
                          Users subscribing to inactive teams will be notified that newsletters will start once there's more interest.
                        </AlertDescription>
                      </Alert>
                    </CardContent>
                  </Card>

                  {/* Data Seeding Card */}
                  <Card>
                    <CardHeader>
                      <CardTitle>Data Seeding</CardTitle>
                      <CardDescription>
                        Seed loan data from API-Football for top leagues or specific teams
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <Accordion type="single" collapsible value={seedSectionOpen ? 'seeding' : ''} onValueChange={(v) => setSeedSectionOpen(v === 'seeding')}>
                        <AccordionItem value="seeding">
                          <AccordionTrigger>Loan Data Seeding</AccordionTrigger>
                          <AccordionContent className="space-y-4 pt-4">
                            {/* Seed Top-5 */}
                            <div className="space-y-2">
                              <Label>Seed Top-5 Leagues</Label>
                              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                                <div className="flex flex-col">
                                  <span className="text-xs text-muted-foreground mb-1">Season (YYYY)</span>
                                  <Input
                                    type="text"
                                    inputMode="numeric"
                                    pattern="[0-9]*"
                                    placeholder="2025"
                                    value={seedSeason}
                                    onChange={(e) => {
                                      const y = (e.target.value || '').replace(/[^0-9]/g, '').slice(0, 4)
                                      setSeedSeason(y)
                                    }}
                                    disabled={teamRunBusy}
                                  />
                                </div>
                                <div className="flex items-end gap-2">
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    onClick={async () => {
                                      const y = parseInt((seedSeason || (runDate || '').slice(0, 4)), 10)
                                      if (!y) {
                                        setTeamRunMsg({ type: 'error', text: 'Enter a valid season year' })
                                        return
                                      }
                                      try {
                                        setTeamRunBusy(true)
                                        setTeamRunMsg(null)
                                        const res = await APIService.request('/admin/loans/seed-top5', {
                                          method: 'POST',
                                          body: JSON.stringify({ season: y, dry_run: true })
                                        }, { admin: true })
                                        const wouldCreate = (res.details || []).filter(d => d.status === 'created').length
                                        setTeamRunMsg({ type: 'success', text: `Dry-run: would create ${wouldCreate} of ${res.candidates}` })
                                        try {
                                          await refreshRunHistory()
                                        } catch (error) {
                                          console.warn('Failed to refresh history after dry-run', error)
                                        }
                                      } catch (error) {
                                        const baseError = error?.body?.error || error.message || 'Unknown error'
                                        const detail = error?.body?.detail || (error?.body?.reference ? `Reference: ${error.body.reference}` : '')
                                        const detailText = detail ? ` — ${detail}` : ''
                                        setTeamRunMsg({
                                          type: 'error',
                                          text: `Dry-run failed: ${baseError}${detailText}`
                                        })
                                      } finally {
                                        setTeamRunBusy(false)
                                      }
                                    }}
                                    disabled={teamRunBusy}
                                  >
                                    Dry-run
                                  </Button>
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    onClick={async () => {
                                      const y = parseInt((seedSeason || (runDate || '').slice(0, 4)), 10)
                                      if (!y) {
                                        setTeamRunMsg({ type: 'error', text: 'Enter a valid season year' })
                                        return
                                      }
                                      try {
                                        setTeamRunBusy(true)
                                        setTeamRunMsg({ type: 'info', text: 'Starting seed job in background...' })
                                        const res = await APIService.request('/admin/loans/seed-top5', {
                                          method: 'POST',
                                          body: JSON.stringify({ season: y, overwrite: true, background: true })
                                        }, { admin: true })

                                        if (res.job_id) {
                                          // Poll for job completion
                                          const pollJob = async () => {
                                            try {
                                              const status = await APIService.request(`/admin/jobs/${res.job_id}`, {}, { admin: true })
                                              if (status.status === 'completed') {
                                                const result = status.results || {}
                                                setTeamRunMsg({ type: 'success', text: `Seeded ${result.created || 0} players (skipped ${result.skipped || 0}) for ${result.season || y}` })
                                                setTeamRunBusy(false)
                                                await refreshLoans()
                                                try {
                                                  await refreshRunHistory()
                                                } catch (error) {
                                                  console.warn('Failed to refresh history after seed', error)
                                                }
                                              } else if (status.status === 'failed') {
                                                setTeamRunMsg({ type: 'error', text: `Seed failed: ${status.error || 'Unknown error'}` })
                                                setTeamRunBusy(false)
                                              } else {
                                                // Still running - show progress
                                                const progress = status.progress || 0
                                                const total = status.total || '?'
                                                const current = status.current_player || ''
                                                setTeamRunMsg({ type: 'info', text: `Seeding... ${progress}/${total} ${current ? `(${current})` : ''}` })
                                                setTimeout(pollJob, 3000)
                                              }
                                            } catch (error) {
                                              console.error('Failed to poll job status:', error)
                                              setTimeout(pollJob, 5000)
                                            }
                                          }
                                          pollJob()
                                        } else {
                                          // Synchronous response (shouldn't happen with background: true)
                                          setTeamRunMsg({ type: 'success', text: `Seeded ${res.created} players (skipped ${res.skipped}) for ${res.season}` })
                                          setTeamRunBusy(false)
                                          await refreshLoans()
                                        }
                                      } catch (error) {
                                        const baseError = error?.body?.error || error.message || 'Unknown error'
                                        const detail = error?.body?.detail || (error?.body?.reference ? `Reference: ${error.body.reference}` : '')
                                        const detailText = detail ? ` — ${detail}` : ''
                                        setTeamRunMsg({
                                          type: 'error',
                                          text: `Seed failed: ${baseError}${detailText}`
                                        })
                                        setTeamRunBusy(false)
                                      }
                                    }}
                                    disabled={teamRunBusy}
                                  >
                                    Seed Top-5
                                  </Button>
                                </div>
                              </div>
                            </div>

                            {/* Seed Selected Teams */}
                            <div className="space-y-2">
                              <Label>Seed Selected Teams</Label>
                              <Button
                                size="sm"
                                variant="secondary"
                                onClick={async () => {
                                  const y = parseInt((seedSeason || (runDate || '').slice(0, 4)), 10)
                                  if (!y) {
                                    setTeamRunMsg({ type: 'error', text: 'Enter a valid season year above' })
                                    return
                                  }
                                  if (!selectedRunTeams.length) {
                                    setTeamRunMsg({ type: 'error', text: 'Select at least one team' })
                                    return
                                  }
                                  setTeamRunBusy(true)
                                  setTeamRunMsg(null)
                                  let created = 0, errs = 0
                                  for (const dbId of selectedRunTeams) {
                                    try {
                                      const res = await APIService.request('/admin/loans/seed-team', {
                                        method: 'POST',
                                        body: JSON.stringify({ season: y, team_db_id: dbId, overwrite: true })
                                      }, { admin: true })
                                      created += (res.created || 0)
                                    } catch {
                                      errs++
                                    }
                                  }
                                  setTeamRunMsg({ type: errs ? 'error' : 'success', text: `Seeded ${created} players across ${selectedRunTeams.length} team(s)` })
                                  setTeamRunBusy(false)
                                  await refreshLoans()
                                  try {
                                    await refreshRunHistory()
                                  } catch (error) {
                                    console.warn('Failed to refresh history after team seed', error)
                                  }
                                }}
                                disabled={teamRunBusy || selectedRunTeams.length === 0}
                                className="w-full"
                              >
                                {teamRunBusy ? (
                                  <>
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                    Seeding…
                                  </>
                                ) : (
                                  `Seed Selected Team(s) (${selectedRunTeams.length})`
                                )}
                              </Button>
                            </div>
                          </AccordionContent>
                        </AccordionItem>
                      </Accordion>
                    </CardContent>
                  </Card>

                  {/* Confirmation Dialog for Run All */}
                  <Dialog open={confirmRunAllOpen} onOpenChange={setConfirmRunAllOpen}>
                    <DialogContent>
                      <DialogHeader>
                        <DialogTitle>Confirm Generate for All Teams</DialogTitle>
                        <DialogDescription>
                          This will generate newsletters for ALL tracked teams. This process cannot be cancelled once started.
                        </DialogDescription>
                      </DialogHeader>
                      <div className="space-y-4 py-4">
                        <Alert variant="destructive">
                          <AlertCircle className="h-4 w-4" />
                          <AlertDescription>
                            <strong>Warning:</strong> This operation will process approximately{' '}
                            <strong>{estimatedTeamCount !== null ? estimatedTeamCount : 'many'}</strong> teams.
                            This may take a significant amount of time and cannot be stopped mid-process.
                          </AlertDescription>
                        </Alert>
                        <div className="space-y-2">
                          <div className="text-sm">
                            <strong>Target Date:</strong> {runDate || new Date().toISOString().slice(0, 10)}
                          </div>
                          {estimatedTeamCount !== null && (
                            <div className="text-sm text-muted-foreground">
                              Estimated teams to process: <strong>{estimatedTeamCount}</strong>
                            </div>
                          )}
                          <div className="text-sm text-muted-foreground">
                            You can pause runs globally using the "Pause" button, but this will only stop future iterations, not the current batch.
                          </div>
                        </div>
                      </div>
                      <DialogFooter>
                        <Button variant="outline" onClick={() => setConfirmRunAllOpen(false)}>
                          Cancel
                        </Button>
                        <Button variant="destructive" onClick={runAll} disabled={running}>
                          {running ? (
                            <>
                              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                              Running…
                            </>
                          ) : (
                            'Generate for All Teams'
                          )}
                        </Button>
                      </DialogFooter>
                    </DialogContent>
                  </Dialog>
                </div>
              </TabsContent>

              <TabsContent value="loans" className="space-y-6">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div id="admin-players-loans" className="md:col-span-2">
                    <Accordion type="single" collapsible className="border rounded-lg">
                      <AccordionItem value="players-loans">
                        <AccordionTrigger className="px-4 py-3 hover:no-underline">
                          <div className="flex items-center justify-between w-full pr-4">
                            <h2 className="font-semibold text-lg">Players & Loans Manager</h2>
                            <div className="text-sm text-muted-foreground">
                              {playersHubData.items.length} player{playersHubData.items.length !== 1 ? 's' : ''}
                            </div>
                          </div>
                        </AccordionTrigger>
                        <AccordionContent className="px-4 pb-4">
                          <div className="mb-4 flex justify-end">
                            <Button size="sm" onClick={() => setShowAddPlayerForm(!showAddPlayerForm)}>
                              {showAddPlayerForm ? 'Cancel' : '+ Add Player'}
                            </Button>
                          </div>

                          {/* Add Player Form */}
                          {showAddPlayerForm && (
                            <div className="bg-gradient-to-r from-emerald-50 to-secondary border border-emerald-200 rounded-lg p-4 mb-4">
                              <h3 className="text-sm font-semibold mb-3">Create New Player</h3>
                              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                <div className="md:col-span-2">
                                  <label className="text-xs font-medium text-foreground/80 block mb-1">Player Name *</label>
                                  <input
                                    type="text"
                                    className="border rounded p-2 text-sm w-full"
                                    placeholder="Full name"
                                    value={addPlayerForm.name}
                                    onChange={(e) => setAddPlayerForm({ ...addPlayerForm, name: e.target.value })}
                                  />
                                </div>
                                <div>
                                  <div className="flex items-center justify-between mb-1">
                                    <label className="text-xs font-medium text-foreground/80">Primary Team (Parent Club) *</label>
                                    <label className="flex items-center gap-1 text-xs text-muted-foreground cursor-pointer">
                                      <input
                                        type="checkbox"
                                        checked={addPlayerForm.use_custom_primary_team}
                                        onChange={(e) => setAddPlayerForm({
                                          ...addPlayerForm,
                                          use_custom_primary_team: e.target.checked,
                                          primary_team_id: '',
                                          custom_primary_team_name: ''
                                        })}
                                      />
                                      Custom team
                                    </label>
                                  </div>
                                  {addPlayerForm.use_custom_primary_team ? (
                                    <input
                                      type="text"
                                      className="border rounded p-2 text-sm w-full"
                                      placeholder="e.g. Portsmouth, Sunderland"
                                      value={addPlayerForm.custom_primary_team_name}
                                      onChange={(e) => setAddPlayerForm({ ...addPlayerForm, custom_primary_team_name: e.target.value })}
                                    />
                                  ) : (
                                    <TeamSelect
                                      teams={runTeams}
                                      value={addPlayerForm.primary_team_id}
                                      onChange={(id) => setAddPlayerForm({ ...addPlayerForm, primary_team_id: id })}
                                      placeholder="Select primary team..."
                                    />
                                  )}
                                </div>
                                <div>
                                  <div className="flex items-center justify-between mb-1">
                                    <label className="text-xs font-medium text-foreground/80">Loan Team (Current Club) *</label>
                                    <label className="flex items-center gap-1 text-xs text-muted-foreground cursor-pointer">
                                      <input
                                        type="checkbox"
                                        checked={addPlayerForm.use_custom_loan_team}
                                        onChange={(e) => setAddPlayerForm({
                                          ...addPlayerForm,
                                          use_custom_loan_team: e.target.checked,
                                          loan_team_id: '',
                                          custom_loan_team_name: ''
                                        })}
                                      />
                                      Custom team
                                    </label>
                                  </div>
                                  {addPlayerForm.use_custom_loan_team ? (
                                    <input
                                      type="text"
                                      className="border rounded p-2 text-sm w-full"
                                      placeholder="e.g. Sheffield Wednesday, Hull City"
                                      value={addPlayerForm.custom_loan_team_name}
                                      onChange={(e) => setAddPlayerForm({ ...addPlayerForm, custom_loan_team_name: e.target.value })}
                                    />
                                  ) : (
                                    <TeamSelect
                                      teams={runTeams}
                                      value={addPlayerForm.loan_team_id}
                                      onChange={(id) => setAddPlayerForm({ ...addPlayerForm, loan_team_id: id })}
                                      placeholder="Select loan team..."
                                    />
                                  )}
                                </div>
                                <div className="md:col-span-2">
                                  <label className="text-xs font-medium text-foreground/80 block mb-1">Season / Window *</label>
                                  <select
                                    className="border rounded p-2 text-sm w-full"
                                    value={addPlayerForm.window_key}
                                    onChange={(e) => setAddPlayerForm({ ...addPlayerForm, window_key: e.target.value })}
                                  >
                                    <option value="">Select season...</option>
                                    {generateSeasonOptions().map(opt => (
                                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                                    ))}
                                  </select>
                                </div>
                                <div>
                                  <label className="text-xs font-medium text-foreground/80 block mb-1">Position</label>
                                  <select
                                    className="border rounded p-2 text-sm w-full"
                                    value={addPlayerForm.position}
                                    onChange={(e) => setAddPlayerForm({ ...addPlayerForm, position: e.target.value })}
                                  >
                                    <option value="">Select position...</option>
                                    {playerFieldOptions.positions.map(pos => (
                                      <option key={pos} value={pos}>{pos}</option>
                                    ))}
                                    <option value="__custom__">+ Add custom position</option>
                                  </select>
                                  {addPlayerForm.position === '__custom__' && (
                                    <input
                                      type="text"
                                      className="border rounded p-2 text-sm w-full mt-2"
                                      placeholder="Enter custom position"
                                      onChange={(e) => setAddPlayerForm({ ...addPlayerForm, position: e.target.value })}
                                      autoFocus
                                    />
                                  )}
                                </div>
                                <div>
                                  <label className="text-xs font-medium text-foreground/80 block mb-1">Nationality</label>
                                  <select
                                    className="border rounded p-2 text-sm w-full"
                                    value={addPlayerForm.nationality}
                                    onChange={(e) => setAddPlayerForm({ ...addPlayerForm, nationality: e.target.value })}
                                  >
                                    <option value="">Select nationality...</option>
                                    {playerFieldOptions.nationalities.map(nat => (
                                      <option key={nat} value={nat}>{nat}</option>
                                    ))}
                                    <option value="__custom__">+ Add custom nationality</option>
                                  </select>
                                  {addPlayerForm.nationality === '__custom__' && (
                                    <input
                                      type="text"
                                      className="border rounded p-2 text-sm w-full mt-2"
                                      placeholder="Enter custom nationality"
                                      onChange={(e) => setAddPlayerForm({ ...addPlayerForm, nationality: e.target.value })}
                                      autoFocus
                                    />
                                  )}
                                </div>
                                <div>
                                  <label className="text-xs font-medium text-foreground/80 block mb-1">Age</label>
                                  <input
                                    type="number"
                                    className="border rounded p-2 text-sm w-full"
                                    placeholder="Age"
                                    value={addPlayerForm.age}
                                    onChange={(e) => setAddPlayerForm({ ...addPlayerForm, age: e.target.value })}
                                  />
                                </div>
                                <div>
                                  <label className="text-xs font-medium text-foreground/80 block mb-1">Sofascore ID</label>
                                  <input
                                    type="number"
                                    className="border rounded p-2 text-sm w-full"
                                    placeholder="Optional Sofascore ID"
                                    value={addPlayerForm.sofascore_id}
                                    onChange={(e) => setAddPlayerForm({ ...addPlayerForm, sofascore_id: e.target.value })}
                                  />
                                </div>
                              </div>
                              <div className="mt-3 flex gap-2">
                                <Button size="sm" onClick={createManualPlayer}>
                                  Create Player
                                </Button>
                                <Button size="sm" variant="outline" onClick={() => {
                                  setShowAddPlayerForm(false)
                                  setAddPlayerForm({
                                    name: '',
                                    firstname: '',
                                    lastname: '',
                                    position: '',
                                    nationality: '',
                                    age: '',
                                    sofascore_id: '',
                                    primary_team_id: '',
                                    loan_team_id: '',
                                    window_key: '',
                                    use_custom_primary_team: false,
                                    custom_primary_team_name: '',
                                    use_custom_loan_team: false,
                                    custom_loan_team_name: ''
                                  })
                                }}>
                                  Cancel
                                </Button>
                              </div>
                            </div>
                          )}

                          {/* Filters Section */}
                          <div className="bg-secondary border rounded-lg p-4 mb-4">
                            <div className="flex items-center justify-between mb-3">
                              <h3 className="font-medium text-sm">Filters</h3>
                              <div className="flex gap-2">
                                <Button size="sm" variant="outline" onClick={applyPlayersHubFilters}>
                                  Apply Filters
                                </Button>
                                <Button size="sm" variant="ghost" onClick={resetPlayersHubFilters}>
                                  Reset
                                </Button>
                              </div>
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
                              <div>
                                <label className="text-xs font-medium text-foreground/80 block mb-1">Team</label>
                                <TeamSelect
                                  teams={runTeams}
                                  value={playersHubFilters.team_id}
                                  onChange={(id) => setPlayersHubFilters({ ...playersHubFilters, team_id: id })}
                                  placeholder="Filter by team..."
                                />
                              </div>
                              <div>
                                <label className="text-xs font-medium text-foreground/80 block mb-1">Player Name</label>
                                <input
                                  className="border rounded p-2 text-sm w-full"
                                  placeholder="Search by name..."
                                  value={playersHubFilters.search}
                                  onChange={e => setPlayersHubFilters({ ...playersHubFilters, search: e.target.value })}
                                  onKeyPress={(e) => e.key === 'Enter' && applyPlayersHubFilters()}
                                />
                              </div>
                              <div>
                                <label className="text-xs font-medium text-foreground/80 block mb-1">Position</label>
                                <select
                                  className="border rounded p-2 text-sm w-full"
                                  value={playersHubFilters.position || ''}
                                  onChange={e => setPlayersHubFilters({ ...playersHubFilters, position: e.target.value })}
                                >
                                  <option value="">All positions</option>
                                  {playerFieldOptions.positions.map(pos => (
                                    <option key={pos} value={pos}>{pos}</option>
                                  ))}
                                </select>
                              </div>
                              <div>
                                <label className="text-xs font-medium text-foreground/80 block mb-1">Sofascore ID</label>
                                <select
                                  className="border rounded p-2 text-sm w-full"
                                  value={playersHubFilters.has_sofascore}
                                  onChange={e => setPlayersHubFilters({ ...playersHubFilters, has_sofascore: e.target.value })}
                                >
                                  <option value="">All players</option>
                                  <option value="true">Has Sofascore ID</option>
                                  <option value="false">Missing Sofascore ID</option>
                                </select>
                              </div>
                              <div>
                                <label className="text-xs font-medium text-foreground/80 block mb-1">Status</label>
                                <select
                                  className="border rounded p-2 text-sm w-full"
                                  value={playersHubFilters.is_active || ''}
                                  onChange={e => setPlayersHubFilters({ ...playersHubFilters, is_active: e.target.value })}
                                >
                                  <option value="">All</option>
                                  <option value="true">Active only</option>
                                  <option value="false">Inactive</option>
                                </select>
                              </div>
                            </div>
                          </div>

                          {/* Bulk Actions */}
                          {selectedPlayersForBulk.length > 0 && (
                            <div className="bg-primary/5 border border-primary/20 rounded-lg p-3 mb-4">
                              <div className="flex items-center justify-between">
                                <span className="text-sm font-medium">{selectedPlayersForBulk.length} player(s) selected</span>
                                <div className="flex gap-2">
                                  <Button size="sm" onClick={() => setBulkSofascoreMode(!bulkSofascoreMode)}>
                                    {bulkSofascoreMode ? 'Cancel Bulk Edit' : 'Bulk Edit Sofascore'}
                                  </Button>
                                  {bulkSofascoreMode && (
                                    <Button size="sm" variant="default" onClick={bulkUpdateSofascoreIds}>
                                      Save Bulk Updates
                                    </Button>
                                  )}
                                  <Button size="sm" variant="ghost" onClick={() => setSelectedPlayersForBulk([])}>
                                    Clear Selection
                                  </Button>
                                </div>
                              </div>
                            </div>
                          )}

                          {/* Advanced Tools (Collapsed) */}
                          <Accordion type="single" collapsible className="mb-4">
                            <AccordionItem value="advanced" className="border rounded-lg">
                              <AccordionTrigger className="px-4 py-2 hover:no-underline">
                                <span className="text-sm font-medium text-foreground/80">🔧 Advanced Tools & Backfill Helpers</span>
                              </AccordionTrigger>
                              <AccordionContent className="px-4 pb-4">
                                <div className="space-y-3">
                                  <div>
                                    <div className="text-xs font-medium text-foreground/80 mb-2">Backfill Operations</div>
                                    <div className="flex flex-wrap gap-2">
                                      <Button size="sm" variant="outline" onClick={backfillTeamLeagues}>
                                        Backfill Team Leagues
                                      </Button>
                                      <Button size="sm" variant="outline" onClick={backfillAllSeasons}>
                                        Backfill All Seasons
                                      </Button>
                                    </div>
                                  </div>

                                  <div>
                                    <div className="text-xs font-medium text-foreground/80 mb-2">Missing Names Checker</div>
                                    <div className="flex flex-wrap gap-2 items-end">
                                      <div className="flex-1 min-w-[200px]">
                                        <label className="text-xs text-muted-foreground block mb-1">Team (optional)</label>
                                        <TeamSelect
                                          teams={runTeams}
                                          value={mnTeamDbId}
                                          onChange={setMnTeamDbId}
                                          placeholder="Select team..."
                                        />
                                      </div>
                                      <div className="w-32">
                                        <label className="text-xs text-muted-foreground block mb-1">Team API ID</label>
                                        <input
                                          className="border rounded p-2 text-sm w-full"
                                          placeholder="API ID"
                                          value={mnTeamApiId}
                                          onChange={e => setMnTeamApiId(e.target.value)}
                                        />
                                      </div>
                                      <Button size="sm" variant="outline" onClick={listMissingNames} disabled={mnBusy}>
                                        {mnBusy ? 'Checking...' : 'Find Missing Names'}
                                      </Button>
                                      <Button size="sm" onClick={backfillMissingNames} disabled={mnBusy || !missingNames?.length}>
                                        Backfill Names
                                      </Button>
                                    </div>

                                    {missingNames && missingNames.length > 0 && (
                                      <div className="mt-3 border rounded-lg overflow-hidden">
                                        <div className="bg-amber-50 px-3 py-2 text-xs font-medium text-amber-800">
                                          Found {missingNames.length} loans with missing names
                                        </div>
                                        <div className="max-h-48 overflow-auto">
                                          <table className="min-w-full text-xs">
                                            <thead className="bg-secondary sticky top-0">
                                              <tr className="text-left">
                                                <th className="p-2">Loan ID</th>
                                                <th className="p-2">Player ID</th>
                                                <th className="p-2">Name</th>
                                                <th className="p-2">Primary Team</th>
                                                <th className="p-2">Loan Team</th>
                                                <th className="p-2">Window</th>
                                              </tr>
                                            </thead>
                                            <tbody>
                                              {missingNames.map(m => (
                                                <tr key={m.id} className="border-t hover:bg-secondary">
                                                  <td className="p-2 whitespace-nowrap">{m.id}</td>
                                                  <td className="p-2 whitespace-nowrap">{m.player_id}</td>
                                                  <td className="p-2 text-muted-foreground italic">{m.player_name || '(empty)'}</td>
                                                  <td className="p-2 whitespace-nowrap">{m.primary_team_name}</td>
                                                  <td className="p-2 whitespace-nowrap">{m.loan_team_name}</td>
                                                  <td className="p-2 whitespace-nowrap">{m.window_key}</td>
                                                </tr>
                                              ))}
                                            </tbody>
                                          </table>
                                        </div>
                                      </div>
                                    )}
                                  </div>
                                </div>
                              </AccordionContent>
                            </AccordionItem>
                          </Accordion>

                          {/* Players Table */}
                          {playersHubLoading ? (
                            <div className="text-center py-8 text-muted-foreground">
                              <Loader2 className="h-6 w-6 animate-spin mx-auto mb-2" />
                              Loading players...
                            </div>
                          ) : playersHubData.items.length === 0 ? (
                            <div className="text-center py-8 text-muted-foreground border rounded-lg bg-secondary">
                              <div className="text-sm font-medium mb-1">No players found</div>
                              <div className="text-xs">Try adjusting your filters or add a new player</div>
                            </div>
                          ) : (
                            <>
                              <div className="border rounded-lg overflow-hidden mb-4">
                                <div className="overflow-x-auto">
                                  <table className="min-w-full text-sm">
                                    <thead className="bg-secondary border-b">
                                      <tr className="text-left">
                                        <th className="p-3">
                                          <input
                                            type="checkbox"
                                            checked={selectedPlayersForBulk.length === playersHubData.items.length && playersHubData.items.length > 0}
                                            onChange={toggleAllPlayersSelection}
                                          />
                                        </th>
                                        <th className="p-3 font-medium">Player</th>
                                        <th className="p-3 font-medium">Teams</th>
                                        <th className="p-3 font-medium">Season</th>
                                        <th className="p-3 font-medium">Sofascore ID</th>
                                        <th className="p-3 font-medium text-center">Status</th>
                                        <th className="p-3 font-medium text-center">Loans</th>
                                        <th className="p-3 font-medium">Actions</th>
                                      </tr>
                                    </thead>
                                    <tbody className="divide-y">
                                      {playersHubData.items.map((player) => {
                                        const isEditingName = Object.prototype.hasOwnProperty.call(inlinePlayerNameEdits, player.player_id)
                                        const draftName = isEditingName ? inlinePlayerNameEdits[player.player_id] : ''
                                        const isSavingName = !!inlinePlayerNameSaving[player.player_id]
                                        return (
                                          <tr key={player.player_id} className="hover:bg-secondary">
                                            <td className="p-3">
                                              <input
                                                type="checkbox"
                                                checked={selectedPlayersForBulk.includes(player.player_id)}
                                                onChange={() => togglePlayerSelection(player.player_id)}
                                              />
                                            </td>
                                            <td className="p-3">
                                              <div className="flex items-start gap-2">
                                                <div className="flex-1 min-w-[200px]">
                                                  {isEditingName ? (
                                                    <>
                                                      <input
                                                        type="text"
                                                        className="border rounded p-1 text-sm w-full max-w-xs"
                                                        placeholder="Player name"
                                                        value={draftName}
                                                        onChange={(e) => setInlinePlayerNameEdits((prev) => ({ ...prev, [player.player_id]: e.target.value }))}
                                                        disabled={isSavingName}
                                                      />
                                                      <div className="mt-2 flex gap-2">
                                                        <Button
                                                          size="sm"
                                                          onClick={() => saveInlinePlayerNameEdit(player.player_id)}
                                                          disabled={isSavingName}
                                                        >
                                                          {isSavingName && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Save
                                                        </Button>
                                                        <Button
                                                          size="sm"
                                                          variant="ghost"
                                                          onClick={() => cancelInlinePlayerNameEdit(player.player_id)}
                                                          disabled={isSavingName}
                                                        >
                                                          Cancel
                                                        </Button>
                                                      </div>
                                                    </>
                                                  ) : (
                                                    <div className="flex items-center gap-2">
                                                      <div className="font-medium">{player.player_name}</div>
                                                      <Button
                                                        size="sm"
                                                        variant="ghost"
                                                        onClick={() => startInlinePlayerNameEdit(player)}
                                                      >
                                                        Rename
                                                      </Button>
                                                    </div>
                                                  )}
                                                  <div className="text-xs text-muted-foreground mt-1">ID: {player.player_id}</div>
                                                  {player.position && (
                                                    <div className="text-xs text-muted-foreground">{player.position}</div>
                                                  )}
                                                </div>
                                                {player.player_id < 0 && (
                                                  <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-emerald-50 text-emerald-800" title="Manual Player">
                                                    M
                                                  </span>
                                                )}
                                              </div>
                                            </td>
                                            <td className="p-3">
                                              <div className="space-y-2">
                                                <div>
                                                  <div className="text-xs text-muted-foreground mb-1">Parent Club</div>
                                                  <div className="text-sm font-medium mb-1">{player.primary_team_name}</div>
                                                  <TeamSelect
                                                    teams={runTeams}
                                                    value={player.primary_team_id}
                                                    onChange={(id) => moveLoanDb({ id: player.loan_id }, 'primary', id)}
                                                    placeholder="Change parent..."
                                                    className="text-xs"
                                                  />
                                                </div>
                                                <div>
                                                  <div className="text-xs text-muted-foreground mb-1">Loan Club</div>
                                                  <div className="text-sm font-medium mb-1">{player.loan_team_name}</div>
                                                  <TeamSelect
                                                    teams={runTeams}
                                                    value={player.loan_team_id}
                                                    onChange={(id) => moveLoanDb({ id: player.loan_id }, 'loan', id)}
                                                    placeholder="Change loan..."
                                                    className="text-xs"
                                                  />
                                                </div>
                                              </div>
                                            </td>
                                            <td className="p-3">
                                              <div className="text-sm">
                                                {player.loan_season || player.window_key || <span className="text-muted-foreground/70">No season</span>}
                                              </div>
                                            </td>
                                            <td className="p-3">
                                              {editingPlayerSofascore[player.player_id] !== undefined || bulkSofascoreMode && selectedPlayersForBulk.includes(player.player_id) ? (
                                                <div className="flex gap-2 items-center">
                                                  <input
                                                    type="number"
                                                    className="border rounded p-1 text-sm w-32"
                                                    placeholder="Sofascore ID"
                                                    value={editingPlayerSofascore[player.player_id] ?? player.sofascore_id ?? ''}
                                                    onChange={(e) => setEditingPlayerSofascore({
                                                      ...editingPlayerSofascore,
                                                      [player.player_id]: e.target.value
                                                    })}
                                                  />
                                                  {!bulkSofascoreMode && (
                                                    <>
                                                      <Button
                                                        size="sm"
                                                        variant="outline"
                                                        onClick={() => updatePlayerSofascoreId(player.player_id, editingPlayerSofascore[player.player_id])}
                                                      >
                                                        Save
                                                      </Button>
                                                      <Button
                                                        size="sm"
                                                        variant="ghost"
                                                        onClick={() => setEditingPlayerSofascore((prev) => {
                                                          const next = { ...prev }
                                                          delete next[player.player_id]
                                                          return next
                                                        })}
                                                      >
                                                        Cancel
                                                      </Button>
                                                    </>
                                                  )}
                                                </div>
                                              ) : (
                                                <div className="flex gap-2 items-center">
                                                  {player.sofascore_id ? (
                                                    <a
                                                      href={`https://www.sofascore.com/player/_/${player.sofascore_id}`}
                                                      target="_blank"
                                                      rel="noopener noreferrer"
                                                      className="text-primary hover:underline text-sm"
                                                    >
                                                      {player.sofascore_id}
                                                    </a>
                                                  ) : (
                                                    <span className="text-muted-foreground/70 text-sm">—</span>
                                                  )}
                                                  <Button
                                                    size="sm"
                                                    variant="outline"
                                                    onClick={() => setEditingPlayerSofascore({
                                                      ...editingPlayerSofascore,
                                                      [player.player_id]: player.sofascore_id || ''
                                                    })}
                                                  >
                                                    Edit
                                                  </Button>
                                                </div>
                                              )}
                                            </td>
                                            <td className="p-3 text-center">
                                              {player.has_sofascore_id ? (
                                                <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-emerald-50 text-emerald-800">
                                                  ✓ Has ID
                                                </span>
                                              ) : (
                                                <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-amber-50 text-amber-800">
                                                  ⚠ Missing
                                                </span>
                                              )}
                                            </td>
                                            <td className="p-3 text-center">
                                              <span className="text-sm font-medium">{player.loan_count}</span>
                                            </td>
                                            <td className="p-3">
                                              <div className="flex gap-1">
                                                <Button
                                                  size="sm"
                                                  variant="outline"
                                                  onClick={() => openEditPlayerDialog(player.player_id)}
                                                  title="Edit player details"
                                                >
                                                  Edit
                                                </Button>
                                                <Button
                                                  size="sm"
                                                  variant="destructive"
                                                  onClick={() => deletePlayer(player.player_id, player.player_name, player.loan_count)}
                                                  title="Delete player"
                                                >
                                                  Delete
                                                </Button>
                                              </div>
                                            </td>
                                          </tr>
                                        )
                                      })}
                                    </tbody>
                                  </table>
                                </div>
                              </div>

                              {/* Pagination */}
                              {playersHubData.total_pages > 1 && (
                                <div className="flex items-center justify-between border-t border-border pt-3">
                                  <span className="text-sm text-muted-foreground">
                                    Page {playersHubData.page} of {playersHubData.total_pages}
                                  </span>
                                  <div className="flex gap-2">
                                    <Button
                                      size="sm"
                                      variant="outline"
                                      onClick={() => setPlayersHubPage(Math.max(1, playersHubPage - 1))}
                                      disabled={playersHubPage === 1 || playersHubLoading}
                                    >
                                      Previous
                                    </Button>
                                    <Button
                                      size="sm"
                                      variant="outline"
                                      onClick={() => setPlayersHubPage(Math.min(playersHubData.total_pages, playersHubPage + 1))}
                                      disabled={playersHubPage === playersHubData.total_pages || playersHubLoading}
                                    >
                                      Next
                                    </Button>
                                  </div>
                                </div>
                              )}
                            </>
                          )}
                        </AccordionContent>
                      </AccordionItem>
                    </Accordion>
                  </div>
                  <div id="admin-supplemental-loans" className="border rounded p-4 md:col-span-2">
                    <h2 className="font-semibold mb-3">Manual Player Entries</h2>
                    <p className="text-sm text-muted-foreground mb-4">
                      Add players who aren't tracked by the API-Football service. Use this for players at teams outside the API's coverage,
                      or for players missing from the automated data feeds. These entries won't have automatic stats updates.
                    </p>
                    <div className="space-y-4">
                      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                        <div className="space-y-2">
                          <div className="font-medium">Filters</div>
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                            <div className="flex flex-col">
                              <span className="text-xs text-muted-foreground">Player name</span>
                              <input className="border rounded p-2 text-sm w-full" placeholder="e.g., Smith" value={supplementalFilters.player_name} onChange={e => setSupplementalFilters({ ...supplementalFilters, player_name: e.target.value })} />
                            </div>
                            <div className="flex flex-col">
                              <span className="text-xs text-muted-foreground">Season (YYYY)</span>
                              <input type="number" inputMode="numeric" pattern="[0-9]*" className="border rounded p-2 text-sm w-full" placeholder="2025" value={supplementalFilters.season} onChange={e => setSupplementalFilters({ ...supplementalFilters, season: e.target.value })} />
                            </div>
                          </div>
                          <Button size="sm" variant="outline" className="w-full" onClick={refreshSupplementalLoans}>Apply Filters</Button>
                        </div>
                        <div className="space-y-2 lg:col-span-2">
                          <div className="font-medium">Add Manual Player</div>
                          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-2">
                            <input className="border rounded p-2 text-sm" placeholder="Player name" value={supplementalForm.player_name} onChange={e => setSupplementalForm({ ...supplementalForm, player_name: e.target.value })} />
                            <input className="border rounded p-2 text-sm" placeholder="Parent team name" value={supplementalForm.parent_team_name} onChange={e => setSupplementalForm({ ...supplementalForm, parent_team_name: e.target.value })} />
                            <input className="border rounded p-2 text-sm" placeholder="Loan team name" value={supplementalForm.loan_team_name} onChange={e => setSupplementalForm({ ...supplementalForm, loan_team_name: e.target.value })} />
                            <input className="border rounded p-2 text-sm" placeholder="Season (YYYY)" value={supplementalForm.season_year} onChange={e => setSupplementalForm({ ...supplementalForm, season_year: e.target.value })} />
                          </div>
                          <Button size="sm" onClick={createSupplementalLoan} disabled={!supplementalForm.player_name || !supplementalForm.parent_team_name || !supplementalForm.loan_team_name || !supplementalForm.season_year}>Add Manual Player</Button>
                        </div>
                      </div>
                      <div className="mt-4">
                        {supplementalLoans.length === 0 ? (
                          <div className="text-sm text-muted-foreground">No manual players found. Click "Apply Filters" to load or add a new one above.</div>
                        ) : (
                          <div className="overflow-x-auto">
                            <table className="min-w-full text-sm border">
                              <thead className="bg-secondary">
                                <tr className="text-left border-b">
                                  <th className="p-2">Player</th>
                                  <th className="p-2">Parent Team</th>
                                  <th className="p-2">Loan Team</th>
                                  <th className="p-2">Season</th>
                                  <th className="p-2">Actions</th>
                                </tr>
                              </thead>
                              <tbody>
                                {supplementalLoans.map((sl) => (
                                  <tr key={sl.id} className="border-b">
                                    <td className="p-2 whitespace-nowrap">
                                      <div className="font-medium">{sl.player_name}</div>
                                      <div className="text-muted-foreground text-xs">ID: {sl.id}</div>
                                    </td>
                                    <td className="p-2">{sl.parent_team_name}</td>
                                    <td className="p-2">{sl.loan_team_name}</td>
                                    <td className="p-2">{sl.season_year}</td>
                                    <td className="p-2">
                                      <Button size="sm" variant="destructive" onClick={() => deleteSupplementalLoan(sl)}>Delete</Button>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="newsletters" className="space-y-6">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div id="admin-newsletters" className="border rounded p-4 md:col-span-2">
                    <h2 className="font-semibold mb-3">Newsletters Manager</h2>
                    <div className="space-y-3">
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                        <div className="md:col-span-1 border rounded p-2">
                          <div className="text-xs font-semibold mb-1">Issue date (primary)</div>
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                            <input type="date" className="border rounded p-2 text-sm" value={nlFilters.issue_start} onChange={e => setNlFilters({ ...nlFilters, issue_start: e.target.value })} />
                            <input type="date" className="border rounded p-2 text-sm" value={nlFilters.issue_end} onChange={e => setNlFilters({ ...nlFilters, issue_end: e.target.value })} />
                          </div>
                        </div>
                        <div className="md:col-span-1 border rounded p-2">
                          <div className="text-xs font-semibold mb-1">Created date</div>
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                            <input type="date" className="border rounded p-2 text-sm" value={nlFilters.created_start} onChange={e => setNlFilters({ ...nlFilters, created_start: e.target.value })} />
                            <input type="date" className="border rounded p-2 text-sm" value={nlFilters.created_end} onChange={e => setNlFilters({ ...nlFilters, created_end: e.target.value })} />
                          </div>
                        </div>
                        <div className="md:col-span-1 border rounded p-2">
                          <div className="text-xs font-semibold mb-1">Week range (optional)</div>
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                            <input type="date" className="border rounded p-2 text-sm" value={nlFilters.week_start} onChange={e => setNlFilters({ ...nlFilters, week_start: e.target.value })} />
                            <input type="date" className="border rounded p-2 text-sm" value={nlFilters.week_end} onChange={e => setNlFilters({ ...nlFilters, week_end: e.target.value })} />
                          </div>
                        </div>
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        <label className="text-sm flex items-center gap-1">
                          <span>Published only</span>
                          <input type="checkbox" checked={nlFilters.published_only === 'true'} onChange={e => setNlFilters({ ...nlFilters, published_only: e.target.checked ? 'true' : '' })} />
                        </label>
                        <div className="ml-auto flex gap-2">
                          <Button size="sm" variant="outline" onClick={refreshNewsletters}>Apply filters</Button>
                          <Button size="sm" variant="ghost" onClick={resetNewsletterFilters}>Reset</Button>
                        </div>
                      </div>
                    </div>
                    <div className="mt-4">
                      {newslettersAdmin.length === 0 ? (
                        <div className="text-sm text-muted-foreground">No newsletters.</div>
                      ) : (
                        <>
                          <div className="flex flex-wrap items-center gap-2 mb-2">
                            <label className="flex items-center gap-2 text-xs text-muted-foreground">
                              <input
                                type="checkbox"
                                checked={allFilteredSelected}
                                onChange={(e) => handleToggleAllFiltered(e.target.checked)}
                              />
                              <span>Select all filtered</span>
                            </label>
                            <span className="text-xs text-muted-foreground">Total {totalFilteredCount}</span>
                            {allFilteredSelected && (
                              <span className="text-xs text-muted-foreground">Excluding {selectedNewsletterIds.length}</span>
                            )}
                            <span className="text-xs text-muted-foreground">Selected {selectedNewsletterCount}</span>
                            <Button
                              size="sm"
                              onClick={sendAdminPreviewSelected}
                              disabled={allFilteredSelected || selectedNewsletterCount === 0 || sendSelectedBusy || bulkDeleteBusy}
                              title={allFilteredSelected ? 'Disable “Select all filtered” to send previews.' : undefined}
                            >
                              {sendSelectedBusy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Send admin preview
                            </Button>
                            <Button
                              size="sm"
                              onClick={() => bulkPublishSelected(true)}
                              disabled={selectedNewsletterCount === 0 || bulkPublishBusy || bulkDeleteBusy}
                            >
                              Publish selected
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => bulkPublishSelected(false)}
                              disabled={selectedNewsletterCount === 0 || bulkPublishBusy || bulkDeleteBusy}
                            >
                              Unpublish selected
                            </Button>
                            <Button
                              size="sm"
                              variant="destructive"
                              onClick={deleteSelectedNewsletters}
                              disabled={selectedNewsletterCount === 0 || bulkDeleteBusy}
                            >
                              {bulkDeleteBusy ? (
                                <span className="inline-flex items-center gap-2">
                                  <Loader2 className="h-4 w-4 animate-spin" />
                                  Deleting…
                                </span>
                              ) : (
                                'Delete selected'
                              )}
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={clearNewsletterSelection}
                              disabled={selectedNewsletterCount === 0 || bulkPublishBusy || bulkDeleteBusy}
                            >
                              Clear selection
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => openReviewModal('manual')}
                              disabled={newslettersAdmin.length === 0}
                            >
                              Review queue
                            </Button>
                            <Button
                              size="sm"
                              variant="secondary"
                              onClick={() => openReviewModal('auto')}
                              disabled={newslettersAdmin.length === 0}
                            >
                              Review & publish filtered
                            </Button>
                          </div>
                          <div className="overflow-x-auto">
                            <table className="min-w-full text-sm">
                              <thead>
                                <tr className="text-left border-b">
                                  <th className="p-2 w-10">
                                    <input
                                      ref={pageSelectRef}
                                      type="checkbox"
                                      checked={allPageSelected}
                                      onChange={(e) => togglePageSelection(e.target.checked)}
                                      aria-label="Select newsletters on this page"
                                    />
                                  </th>
                                  <th className="p-2">ID</th>
                                  <th className="p-2">Team</th>
                                  <th className="p-2">Title</th>
                                  <th className="p-2">Week</th>
                                  <th className="p-2">Published</th>
                                  <th className="p-2">Actions</th>
                                </tr>
                              </thead>
                              <tbody>
                                {paginatedNewslettersAdmin.map(n => (
                                  <tr key={n.id} className="border-b">
                                    <td className="p-2 align-top">
                                      <input
                                        type="checkbox"
                                        checked={allFilteredSelected ? !selectedNewsletterIdsSet.has(n.id) : selectedNewsletterIdsSet.has(n.id)}
                                        onChange={() => toggleNewsletterSelection(n.id)}
                                        aria-label={`Select newsletter ${n.id}`}
                                      />
                                    </td>
                                    <td className="p-2 align-top text-sm text-muted-foreground">#{n.id}</td>
                                    <td className="p-2 whitespace-nowrap">{n.team_name}</td>
                                    <td className="p-2">{n.title}</td>
                                    <td className="p-2">{n.week_start_date ? `${n.week_start_date} → ${n.week_end_date}` : ''}</td>
                                    <td className="p-2">{n.published ? `Yes (${n.published_date?.slice(0, 10) || ''})` : 'No'}</td>
                                    <td className="p-2">
                                      <div className="flex flex-wrap items-center gap-2">
                                        <Button
                                          size="sm"
                                          onClick={() => sendAdminPreview([n.id])}
                                          disabled={sendPreviewBusyIds.includes(n.id) || sendSelectedBusy || bulkDeleteBusy}
                                        >
                                          {(sendPreviewBusyIds.includes(n.id) || sendSelectedBusy) && (
                                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                          )}
                                          Send preview
                                        </Button>
                                        <Button size="sm" variant="outline" onClick={() => startEditNewsletter(n)}>View/Edit</Button>
                                        <Button size="sm" variant="ghost" asChild>
                                          <Link to={`/admin/newsletters/${n.id}`} className="text-primary hover:underline">
                                            Open detail
                                          </Link>
                                        </Button>
                                        <Button
                                          size="sm"
                                          variant="destructive"
                                          type="button"
                                          onClick={(e) => {
                                            e.preventDefault()
                                            e.stopPropagation()
                                            deleteNewsletters([n.id])
                                          }}
                                          disabled={deleteBusyIds.includes(n.id) || bulkDeleteBusy}
                                        >
                                          {(deleteBusyIds.includes(n.id) || bulkDeleteBusy) && (
                                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                          )}
                                          Delete
                                        </Button>
                                      </div>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4 mt-4 text-sm text-muted-foreground">
                            <span>
                              Page {adminNewsPage} of {adminTotalPages}
                              {adminPageStart > 0 ? ` • Showing ${adminPageStart}–${adminPageEnd} of ${newslettersAdmin.length}` : ''}
                            </span>
                            <div className="flex gap-2">
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => setAdminNewsPage((page) => Math.max(1, page - 1))}
                                disabled={adminNewsPage === 1}
                              >
                                Previous
                              </Button>
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => setAdminNewsPage((page) => Math.min(adminTotalPages, page + 1))}
                                disabled={adminNewsPage === adminTotalPages || newslettersAdmin.length === 0}
                              >
                                Next
                              </Button>
                            </div>
                          </div>
                        </>
                      )}
                    </div>
                    <Dialog open={reviewModalOpen} onOpenChange={(open) => { if (!open) closeReviewModal() }}>
                      <DialogContent
                        className="w-full max-w-none p-0 lg:p-6"
                        style={{ ...reviewModalSizing, overflow: 'auto' }}
                      >
                        <div className="flex h-full flex-col gap-4 p-4 lg:p-0">
                          <DialogHeader className="px-0">
                            <div className="flex items-center justify-between gap-3">
                              <div>
                                <DialogTitle>{reviewMode === 'auto' ? 'Review & publish filtered newsletters' : 'Review newsletters'}</DialogTitle>
                                <DialogDescription>{reviewProgressLabel}</DialogDescription>
                              </div>
                              {reviewMode === 'auto' ? (
                                <Badge variant="secondary">Auto publish</Badge>
                              ) : (
                                <Badge variant="secondary">Manual</Badge>
                              )}
                            </div>
                          </DialogHeader>
                          <div className="flex-1 overflow-auto">
                            {reviewFinalizeBusy ? (
                              <div className="flex h-full flex-col items-center justify-center gap-3 text-sm text-muted-foreground">
                                <Loader2 className="h-6 w-6 animate-spin" />
                                Finalizing bulk actions…
                              </div>
                            ) : (
                              <div className="grid h-full grid-cols-1 gap-4 lg:grid-cols-5">
                                <div className="flex h-full flex-col gap-3 rounded-md border bg-secondary p-4 lg:col-span-2">
                                  <div className="space-y-1 overflow-y-auto">
                                    <div className="text-sm font-semibold text-foreground">{currentReviewItem?.title || 'Untitled newsletter'}</div>
                                    <div className="text-xs text-muted-foreground">Team: {reviewDetail?.team_name || currentReviewItem?.team_name || '—'}</div>
                                    <div className="text-xs text-muted-foreground">Issue date: {reviewDetail?.issue_date || currentReviewItem?.issue_date || '—'}</div>
                                    <div className="text-xs text-muted-foreground">Week: {reviewDetail?.week_start_date && reviewDetail?.week_end_date ? `${reviewDetail.week_start_date} → ${reviewDetail.week_end_date}` : (currentReviewItem?.week_start_date ? `${currentReviewItem.week_start_date} → ${currentReviewItem.week_end_date}` : '—')}</div>
                                    <div className="text-xs text-muted-foreground">Published: {reviewDetail?.published ? `Yes (${reviewDetail?.published_date?.slice(0, 10) || ''})` : 'No'}</div>
                                    {reviewMode === 'auto' && (
                                      <div className="text-xs text-muted-foreground">Queued skips: {reviewBatchExclude.length} • Queued deletes: {reviewBatchDelete.length}</div>
                                    )}
                                    <div className="text-xs text-muted-foreground">
                                      Keyboard: Arrow keys or j/k to navigate, space to {reviewMode === 'auto' ? 'approve & move next' : 'publish'}.
                                    </div>
                                  </div>
                                </div>
                                <div className="flex h-full flex-col gap-3 lg:col-span-3">
                                  <Tabs value={reviewPreviewFormat} onValueChange={changeReviewFormat} className="w-full">
                                    <TabsList className="w-fit">
                                      <TabsTrigger value="web">Web preview</TabsTrigger>
                                      <TabsTrigger value="email">Email preview</TabsTrigger>
                                    </TabsList>
                                  </Tabs>
                                  <div className="flex-1 overflow-auto rounded-md border bg-card p-4">
                                    {reviewLoadingDetail ? (
                                      <div className="flex h-full items-center justify-center gap-2 text-sm text-muted-foreground">
                                        <Loader2 className="h-4 w-4 animate-spin" />
                                        Loading newsletter…
                                      </div>
                                    ) : reviewPreviewFormat === 'email' ? (
                                      reviewRenderedContent.email ? (
                                        <div className="prose max-w-none" dangerouslySetInnerHTML={{ __html: reviewRenderedContent.email }} />
                                      ) : reviewRenderedContent.emailError ? (
                                        <div className="text-sm text-rose-600">{reviewRenderedContent.emailError}</div>
                                      ) : (
                                        <div className="text-xs text-muted-foreground">Email preview not loaded yet.</div>
                                      )
                                    ) : reviewRenderedContent.web ? (
                                      <div className="prose max-w-none" dangerouslySetInnerHTML={{ __html: reviewRenderedContent.web }} />
                                    ) : reviewRenderedContent.webError ? (
                                      <div className="text-sm text-rose-600">{reviewRenderedContent.webError}</div>
                                    ) : (
                                      <div className="text-xs text-muted-foreground">Preview not available.</div>
                                    )}
                                  </div>
                                </div>
                              </div>
                            )}
                          </div>
                          <DialogFooter className="flex flex-wrap items-center justify-between gap-3 px-0">
                            <div className="text-xs text-muted-foreground">
                              {currentReviewItem ? `#${currentReviewItem.id} • ${currentReviewItem.team_name || 'Unknown team'}` : 'Queue complete'}
                            </div>
                            <div className="flex flex-wrap gap-2">
                              {reviewMode === 'auto' ? (
                                <>
                                  <Button onClick={handleApproveAndNext} disabled={reviewFinalizeBusy || reviewLoadingDetail || !currentReviewItem}>
                                    Approve & Next
                                  </Button>
                                  <Button variant="outline" onClick={handleSkipReview} disabled={reviewFinalizeBusy || reviewLoadingDetail || !currentReviewItem}>
                                    Skip
                                  </Button>
                                  <Button variant="destructive" onClick={handleDeleteReview} disabled={reviewFinalizeBusy || reviewLoadingDetail || !currentReviewItem}>
                                    Delete
                                  </Button>
                                  <Button variant="ghost" onClick={finalizeAutoReview} disabled={reviewFinalizeBusy}>
                                    Finish review
                                  </Button>
                                </>
                              ) : (
                                <>
                                  <Button onClick={handlePublishReview} disabled={reviewLoadingDetail || !currentReviewItem}>
                                    Publish
                                  </Button>
                                  <Button variant="outline" onClick={goToNextReview} disabled={!currentReviewItem}>
                                    Next
                                  </Button>
                                  <Button variant="destructive" onClick={handleDeleteReview} disabled={reviewLoadingDetail || !currentReviewItem}>
                                    Delete
                                  </Button>
                                </>
                              )}
                              <Button variant="ghost" onClick={closeReviewModal} disabled={reviewFinalizeBusy}>
                                Close
                              </Button>
                            </div>
                          </DialogFooter>
                        </div>
                      </DialogContent>
                    </Dialog>
                    {editingNl && (
                      <div className="mt-4 border-t pt-4">
                        <div className="flex items-center justify-between mb-4">
                          <div className="font-medium">Editing: {editingNl.title}</div>
                          <div className="flex gap-2">
                            <Button
                              size="sm"
                              variant={enhancedEditorMode === 'visual' ? 'default' : 'outline'}
                              onClick={() => setEnhancedEditorMode('visual')}
                            >
                              Visual Editor
                            </Button>
                            <Button
                              size="sm"
                              variant={enhancedEditorMode === 'json' ? 'default' : 'outline'}
                              onClick={() => setEnhancedEditorMode('json')}
                            >
                              JSON Editor
                            </Button>
                          </div>
                        </div>

                        {enhancedEditorMode === 'visual' ? (
                          <div className="space-y-4">
                            {/* Metadata Section */}
                            <div className="bg-gradient-to-r from-secondary to-background p-4 rounded-lg border border-primary/20">
                              <h3 className="text-sm font-semibold mb-3 text-foreground">Newsletter Metadata</h3>
                              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                <div>
                                  <label className="text-xs text-muted-foreground mb-1 block">Title</label>
                                  <input
                                    className="border rounded p-2 text-sm w-full"
                                    value={editingNl.title || ''}
                                    onChange={e => setEditingNl({ ...editingNl, title: e.target.value })}
                                  />
                                </div>
                                <div>
                                  <label className="text-xs text-muted-foreground mb-1 block">Issue Date</label>
                                  <input
                                    type="date"
                                    className="border rounded p-2 text-sm w-full"
                                    value={editingNl.issue_date?.slice(0, 10) || ''}
                                    onChange={e => setEditingNl({ ...editingNl, issue_date: e.target.value })}
                                  />
                                </div>
                                <div>
                                  <label className="text-xs text-muted-foreground mb-1 block">Week Start</label>
                                  <input
                                    type="date"
                                    className="border rounded p-2 text-sm w-full"
                                    value={editingNl.week_start_date?.slice(0, 10) || ''}
                                    onChange={e => setEditingNl({ ...editingNl, week_start_date: e.target.value })}
                                  />
                                </div>
                                <div>
                                  <label className="text-xs text-muted-foreground mb-1 block">Week End</label>
                                  <input
                                    type="date"
                                    className="border rounded p-2 text-sm w-full"
                                    value={editingNl.week_end_date?.slice(0, 10) || ''}
                                    onChange={e => setEditingNl({ ...editingNl, week_end_date: e.target.value })}
                                  />
                                </div>
                                <div className="flex items-center gap-2">
                                  <input
                                    type="checkbox"
                                    id="published-checkbox"
                                    checked={!!editingNl.published}
                                    onChange={e => setEditingNl({ ...editingNl, published: e.target.checked })}
                                  />
                                  <label htmlFor="published-checkbox" className="text-sm font-medium">Published</label>
                                </div>
                              </div>
                            </div>

                            {/* Player Cards by Section */}
                            {(() => {
                              try {
                                const content = typeof editingNl.content === 'string' ? JSON.parse(editingNl.content) : (editingNl.content || {})
                                const sections = content?.sections || []
                                const filteredSections = sections.filter(s =>
                                  (s?.title || '').trim().toLowerCase() !== 'what the internet is saying'
                                )

                                return (
                                  <div className="space-y-4">
                                    {/* Newsletter Summary */}
                                    {content.summary && (
                                      <div className="bg-amber-50 p-4 rounded-lg border border-amber-200">
                                        <div className="text-sm font-semibold mb-2 text-foreground">Newsletter Summary</div>
                                        <textarea
                                          className="w-full border rounded p-2 text-sm"
                                          rows="3"
                                          value={content.summary}
                                          onChange={(e) => {
                                            content.summary = e.target.value
                                            setEditingNl({ ...editingNl, content: JSON.stringify(content, null, 2) })
                                          }}
                                        />
                                      </div>
                                    )}

                                    {/* Highlights */}
                                    {content.highlights && Array.isArray(content.highlights) && (
                                      <div className="bg-amber-50 p-4 rounded-lg border border-amber-200">
                                        <div className="text-sm font-semibold mb-2 text-foreground">Key Highlights</div>
                                        <div className="space-y-2">
                                          {content.highlights.map((h, idx) => (
                                            <div key={idx} className="flex gap-2">
                                              <input
                                                className="flex-1 border rounded p-2 text-sm"
                                                value={h}
                                                onChange={(e) => {
                                                  content.highlights[idx] = e.target.value
                                                  setEditingNl({ ...editingNl, content: JSON.stringify(content, null, 2) })
                                                }}
                                              />
                                              <Button
                                                size="sm"
                                                variant="ghost"
                                                onClick={() => {
                                                  content.highlights.splice(idx, 1)
                                                  setEditingNl({ ...editingNl, content: JSON.stringify(content, null, 2) })
                                                }}
                                              >
                                                ✕
                                              </Button>
                                            </div>
                                          ))}
                                        </div>
                                      </div>
                                    )}

                                    {/* Player Sections */}
                                    {filteredSections.map((section, sectionIdx) => {
                                      const originalSectionIdx = sections.findIndex(s => s === section)
                                      return (
                                        <div key={sectionIdx} className="bg-card border-2 border-border rounded-lg overflow-hidden">
                                          <div className="bg-gradient-to-r from-secondary to-background px-4 py-3 border-b border-border">
                                            <div className="flex items-center justify-between">
                                              <h3 className="font-semibold text-foreground">{section.title || 'Untitled Section'}</h3>
                                              <div className="text-xs text-muted-foreground">{section.items?.length || 0} players</div>
                                            </div>
                                          </div>
                                          <div className="p-4 space-y-3">
                                            {section.items && section.items.length > 0 ? (
                                              section.items.map((item, itemIdx) => {
                                                const isEditing = editingPlayerCard?.sectionIndex === originalSectionIdx && editingPlayerCard?.itemIndex === itemIdx
                                                const playerYoutubeLink = nlYoutubeLinks.find(
                                                  link => link.player_name === item.player_name ||
                                                    (link.player_id && item.player_id && link.player_id === item.player_id)
                                                )

                                                return (
                                                  <div key={itemIdx} className={`border rounded-lg p-3 ${isEditing ? 'border-primary bg-primary/5' : 'border-border bg-secondary hover:bg-card'} transition-colors`}>
                                                    {isEditing ? (
                                                      <div className="space-y-3">
                                                        <div className="grid grid-cols-2 gap-2">
                                                          <div>
                                                            <label className="text-xs font-medium text-foreground/80">Player Name</label>
                                                            <input
                                                              className="w-full border rounded p-2 text-sm mt-1"
                                                              value={editingPlayerCard.data.player_name || ''}
                                                              onChange={(e) => setEditingPlayerCard({
                                                                ...editingPlayerCard,
                                                                data: { ...editingPlayerCard.data, player_name: e.target.value }
                                                              })}
                                                            />
                                                          </div>
                                                          <div>
                                                            <label className="text-xs font-medium text-foreground/80">Loan Team</label>
                                                            <input
                                                              className="w-full border rounded p-2 text-sm mt-1"
                                                              value={editingPlayerCard.data.loan_team || ''}
                                                              onChange={(e) => setEditingPlayerCard({
                                                                ...editingPlayerCard,
                                                                data: { ...editingPlayerCard.data, loan_team: e.target.value }
                                                              })}
                                                            />
                                                          </div>
                                                        </div>
                                                        <div className="grid grid-cols-3 gap-2">
                                                          <div>
                                                            <label className="text-xs font-medium text-foreground/80">Goals</label>
                                                            <input
                                                              type="number"
                                                              className="w-full border rounded p-2 text-sm mt-1"
                                                              value={editingPlayerCard.data.stats?.goals || 0}
                                                              onChange={(e) => setEditingPlayerCard({
                                                                ...editingPlayerCard,
                                                                data: {
                                                                  ...editingPlayerCard.data,
                                                                  stats: { ...(editingPlayerCard.data.stats || {}), goals: parseInt(e.target.value) || 0 }
                                                                }
                                                              })}
                                                            />
                                                          </div>
                                                          <div>
                                                            <label className="text-xs font-medium text-foreground/80">Assists</label>
                                                            <input
                                                              type="number"
                                                              className="w-full border rounded p-2 text-sm mt-1"
                                                              value={editingPlayerCard.data.stats?.assists || 0}
                                                              onChange={(e) => setEditingPlayerCard({
                                                                ...editingPlayerCard,
                                                                data: {
                                                                  ...editingPlayerCard.data,
                                                                  stats: { ...(editingPlayerCard.data.stats || {}), assists: parseInt(e.target.value) || 0 }
                                                                }
                                                              })}
                                                            />
                                                          </div>
                                                          <div>
                                                            <label className="text-xs font-medium text-foreground/80">Minutes</label>
                                                            <input
                                                              type="number"
                                                              className="w-full border rounded p-2 text-sm mt-1"
                                                              value={editingPlayerCard.data.stats?.minutes || 0}
                                                              onChange={(e) => setEditingPlayerCard({
                                                                ...editingPlayerCard,
                                                                data: {
                                                                  ...editingPlayerCard.data,
                                                                  stats: { ...(editingPlayerCard.data.stats || {}), minutes: parseInt(e.target.value) || 0 }
                                                                }
                                                              })}
                                                            />
                                                          </div>
                                                        </div>
                                                        <div>
                                                          <label className="text-xs font-medium text-foreground/80">Week Summary</label>
                                                          <textarea
                                                            className="w-full border rounded p-2 text-sm mt-1"
                                                            rows="3"
                                                            value={editingPlayerCard.data.week_summary || ''}
                                                            onChange={(e) => setEditingPlayerCard({
                                                              ...editingPlayerCard,
                                                              data: { ...editingPlayerCard.data, week_summary: e.target.value }
                                                            })}
                                                          />
                                                        </div>
                                                        <div className="flex gap-2 pt-2">
                                                          <Button
                                                            size="sm"
                                                            onClick={() => updatePlayerInNewsletter(originalSectionIdx, itemIdx, editingPlayerCard.data)}
                                                          >
                                                            Save Changes
                                                          </Button>
                                                          <Button
                                                            size="sm"
                                                            variant="outline"
                                                            onClick={() => setEditingPlayerCard(null)}
                                                          >
                                                            Cancel
                                                          </Button>
                                                        </div>
                                                      </div>
                                                    ) : (
                                                      <>
                                                        <div className="flex items-start justify-between mb-2">
                                                          <div className="flex-1">
                                                            <div className="flex items-center gap-2 flex-wrap">
                                                              <span className="font-semibold text-foreground">{item.player_name}</span>
                                                              {item.loan_team && (
                                                                <span className="bg-primary/10 text-primary px-2 py-0.5 rounded text-xs font-medium">
                                                                  → {item.loan_team}
                                                                </span>
                                                              )}
                                                              {item.stats && (
                                                                <div className="flex gap-1">
                                                                  {item.stats.goals > 0 && (
                                                                    <span className="bg-emerald-50 text-emerald-800 px-2 py-0.5 rounded text-xs font-medium">
                                                                      {item.stats.goals}G
                                                                    </span>
                                                                  )}
                                                                  {item.stats.assists > 0 && (
                                                                    <span className="bg-purple-100 text-purple-800 px-2 py-0.5 rounded text-xs font-medium">
                                                                      {item.stats.assists}A
                                                                    </span>
                                                                  )}
                                                                  {item.stats.minutes > 0 && (
                                                                    <span className="bg-primary/10 text-primary px-2 py-0.5 rounded text-xs font-medium">
                                                                      {item.stats.minutes}'
                                                                    </span>
                                                                  )}
                                                                </div>
                                                              )}
                                                              {playerYoutubeLink && (
                                                                <a
                                                                  href={playerYoutubeLink.youtube_link}
                                                                  target="_blank"
                                                                  rel="noopener noreferrer"
                                                                  className="bg-rose-50 text-rose-800 px-2 py-0.5 rounded text-xs font-medium hover:bg-rose-200"
                                                                >
                                                                  🎬 Highlights
                                                                </a>
                                                              )}
                                                            </div>
                                                            {item.week_summary && (
                                                              <p className="text-sm text-foreground/80 mt-2 leading-relaxed">{item.week_summary}</p>
                                                            )}
                                                          </div>
                                                          <div className="flex gap-1 ml-2">
                                                            <Button
                                                              size="sm"
                                                              variant="ghost"
                                                              onClick={() => setEditingPlayerCard({
                                                                sectionIndex: originalSectionIdx,
                                                                itemIndex: itemIdx,
                                                                data: { ...item }
                                                              })}
                                                              title="Edit player"
                                                            >
                                                              ✏️
                                                            </Button>
                                                            <Button
                                                              size="sm"
                                                              variant="ghost"
                                                              onClick={() => movePlayerInNewsletter(originalSectionIdx, itemIdx, originalSectionIdx, 'up')}
                                                              disabled={itemIdx === 0}
                                                              title="Move up"
                                                            >
                                                              ↑
                                                            </Button>
                                                            <Button
                                                              size="sm"
                                                              variant="ghost"
                                                              onClick={() => movePlayerInNewsletter(originalSectionIdx, itemIdx, originalSectionIdx, 'down')}
                                                              disabled={itemIdx === section.items.length - 1}
                                                              title="Move down"
                                                            >
                                                              ↓
                                                            </Button>
                                                            <Button
                                                              size="sm"
                                                              variant="ghost"
                                                              onClick={() => deletePlayerFromNewsletter(originalSectionIdx, itemIdx)}
                                                              title="Remove player"
                                                            >
                                                              🗑️
                                                            </Button>
                                                          </div>
                                                        </div>
                                                      </>
                                                    )}
                                                  </div>
                                                )
                                              })
                                            ) : (
                                              <div className="text-center py-4 text-sm text-muted-foreground">
                                                No players in this section
                                              </div>
                                            )}
                                          </div>
                                        </div>
                                      )
                                    })}
                                  </div>
                                )
                              } catch (_error) {
                                return (
                                  <div className="bg-rose-50 border border-rose-200 rounded p-4 text-sm text-rose-700">
                                    Unable to parse newsletter content. Switch to JSON Editor to fix.
                                  </div>
                                )
                              }
                            })()}

                            {/* YouTube Links Section */}
                            <div className="border rounded-lg p-4 bg-gradient-to-r from-red-50 to-pink-50">
                              <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
                                🎬 YouTube Links for Players
                              </h3>
                              <div className="mb-3 space-y-2">
                                <div className="text-xs text-muted-foreground">Add YouTube highlight links to players in this newsletter</div>
                                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                                  <select
                                    className="border rounded p-2 text-sm"
                                    value={nlYoutubeLinkForm.player_name}
                                    onChange={(e) => {
                                      const selectedPlayer = extractPlayersFromNewsletter(editingNl).find(p => p.player_name === e.target.value)
                                      setNlYoutubeLinkForm({
                                        player_name: e.target.value,
                                        youtube_link: nlYoutubeLinkForm.youtube_link,
                                        player_id: selectedPlayer?.player_id || null
                                      })
                                    }}
                                  >
                                    <option value="">Select player...</option>
                                    {extractPlayersFromNewsletter(editingNl).map((player, idx) => (
                                      <option key={idx} value={player.player_name}>
                                        {player.player_name} ({player.loan_team})
                                      </option>
                                    ))}
                                  </select>
                                  <input
                                    className="border rounded p-2 text-sm"
                                    placeholder="YouTube URL"
                                    value={nlYoutubeLinkForm.youtube_link}
                                    onChange={(e) => setNlYoutubeLinkForm({ ...nlYoutubeLinkForm, youtube_link: e.target.value })}
                                  />
                                  <Button size="sm" onClick={createNewsletterYoutubeLink}>Add Link</Button>
                                </div>
                              </div>
                              <div className="space-y-2">
                                {nlYoutubeLinks.length === 0 ? (
                                  <div className="text-xs text-muted-foreground">No YouTube links added yet</div>
                                ) : (
                                  nlYoutubeLinks.map((link) => (
                                    <div key={link.id} className="bg-card border rounded p-2 flex items-center gap-2">
                                      <div className="flex-1">
                                        <div className="text-sm font-medium">{link.player_name}</div>
                                        {editingNlYoutubeLink?.id === link.id ? (
                                          <input
                                            className="border rounded p-1 text-xs w-full mt-1"
                                            value={editingNlYoutubeLink.youtube_link}
                                            onChange={(e) => setEditingNlYoutubeLink({ ...editingNlYoutubeLink, youtube_link: e.target.value })}
                                          />
                                        ) : (
                                          <a href={link.youtube_link} target="_blank" rel="noopener noreferrer" className="text-xs text-primary hover:underline truncate block">
                                            {link.youtube_link}
                                          </a>
                                        )}
                                      </div>
                                      <div className="flex gap-1">
                                        {editingNlYoutubeLink?.id === link.id ? (
                                          <>
                                            <Button size="sm" variant="outline" onClick={() => updateNewsletterYoutubeLink(link.id)}>Save</Button>
                                            <Button size="sm" variant="ghost" onClick={() => setEditingNlYoutubeLink(null)}>Cancel</Button>
                                          </>
                                        ) : (
                                          <>
                                            <Button size="sm" variant="outline" onClick={() => setEditingNlYoutubeLink(link)}>Edit</Button>
                                            <Button size="sm" variant="destructive" onClick={() => deleteNewsletterYoutubeLink(link.id)}>Delete</Button>
                                          </>
                                        )}
                                      </div>
                                    </div>
                                  ))
                                )}
                              </div>
                            </div>

                            {/* Commentary Section */}
                            <div className="border rounded-lg p-4 bg-gradient-to-r from-purple-50 to-indigo-50">
                              <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
                                ✍️ Author Commentary
                              </h3>
                              <CommentaryManager
                                newsletterId={editingNl.id}
                                players={extractPlayersFromNewsletter(editingNl)}
                                apiService={APIService}
                              />
                            </div>

                            {/* Preview Section */}
                            <div className="border rounded-lg overflow-hidden">
                              <div className="bg-secondary px-4 py-2 border-b flex items-center justify-between">
                                <span className="text-sm font-semibold">Live Preview</span>
                                <div className="flex items-center gap-2">
                                  <Button size="sm" variant={previewFormat === 'web' ? 'default' : 'outline'} onClick={() => setPreviewFormat('web')}>Web</Button>
                                  <Button size="sm" variant={previewFormat === 'email' ? 'default' : 'outline'} onClick={() => setPreviewFormat('email')}>Email</Button>
                                  <Button size="sm" variant="ghost" onClick={refreshPreview}>Reload</Button>
                                </div>
                              </div>
                              <div className="bg-card max-h-[520px] overflow-auto p-4">
                                {previewError ? (
                                  <div className="p-3 text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded">
                                    {previewError}
                                  </div>
                                ) : previewHtml ? (
                                  <div dangerouslySetInnerHTML={{ __html: previewHtml }} />
                                ) : (
                                  <div className="p-3 text-sm text-muted-foreground">No preview loaded yet. Click "Reload" to generate.</div>
                                )}
                              </div>
                            </div>
                          </div>
                        ) : (
                          /* JSON Editor Mode */
                          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                            <div className="flex flex-col gap-2">
                              <div className="text-sm font-medium">Content JSON</div>
                              <textarea
                                className="border rounded p-2 text-sm font-mono"
                                rows="24"
                                value={(() => {
                                  try {
                                    return typeof editingNl.content === 'string' ? editingNl.content : JSON.stringify(editingNl.content || {}, null, 2)
                                  } catch {
                                    return String(editingNl.content || '')
                                  }
                                })()}
                                onChange={e => setEditingNl({ ...editingNl, content: e.target.value })}
                              />
                            </div>
                            <div className="flex flex-col gap-2">
                              <div className="text-sm font-medium">Preview</div>
                              <div className="border rounded bg-card p-4 max-h-[600px] overflow-auto">
                                {(() => {
                                  try {
                                    const obj = (() => { try { return typeof editingNl.content === 'string' ? JSON.parse(editingNl.content) : (editingNl.content || {}) } catch { return {} } })()
                                    const previewSections = Array.isArray(obj.sections)
                                      ? obj.sections.filter((section) => ((section?.title || '').trim().toLowerCase()) !== 'what the internet is saying')
                                      : []
                                    return (
                                      <div className="space-y-4">
                                        <div className="bg-gradient-to-r from-secondary to-background p-4 rounded border-l-4 border-primary/20">
                                          <div className="text-xl font-bold text-foreground mb-1">{obj.title || editingNl.title}</div>
                                          {obj.range && (
                                            <div className="text-xs text-muted-foreground">Week: {obj.range[0]} - {obj.range[1]}</div>
                                          )}
                                          {obj.summary && (
                                            <div className="text-foreground/80 leading-relaxed mt-2">{obj.summary}</div>
                                          )}
                                        </div>
                                        {obj.highlights && Array.isArray(obj.highlights) && obj.highlights.length > 0 && (
                                          <div className="bg-amber-50 p-3 rounded border-l-4 border-amber-400">
                                            <div className="text-sm font-semibold text-foreground mb-2">Key Highlights</div>
                                            <ul className="list-disc ml-5 space-y-1">
                                              {obj.highlights.map((h, i) => (<li key={i} className="text-sm text-foreground/80">{h}</li>))}
                                            </ul>
                                          </div>
                                        )}
                                        {previewSections.length > 0 && (
                                          <div className="space-y-3">
                                            {previewSections.map((sec, si) => (
                                              <div key={si} className="bg-card border rounded">
                                                {sec.title && (
                                                  <div className="bg-secondary px-3 py-2 border-b text-sm font-semibold">{sec.title}</div>
                                                )}
                                                <div className="p-3 space-y-2">
                                                  {sec.items && sec.items.map((it, ii) => (
                                                    <div key={ii} className="border-l-4 border-primary/20 pl-3 py-1">
                                                      <div className="flex flex-wrap items-center gap-2">
                                                        {it.player_name && (<span className="font-semibold text-foreground">{it.player_name}</span>)}
                                                        {it.loan_team && (<span className="bg-primary/10 text-primary px-2 py-0.5 rounded text-xs">→ {it.loan_team}</span>)}
                                                        {it.stats && (
                                                          <div className="flex gap-1 text-xs">
                                                            {it.stats.goals > 0 && (<span className="bg-emerald-50 text-emerald-800 px-1 rounded">{it.stats.goals}G</span>)}
                                                            {it.stats.assists > 0 && (<span className="bg-purple-100 text-purple-800 px-1 rounded">{it.stats.assists}A</span>)}
                                                            {it.stats.minutes > 0 && (<span className="bg-primary/10 text-primary px-1 rounded">{it.stats.minutes}'</span>)}
                                                          </div>
                                                        )}
                                                      </div>
                                                      {it.week_summary && (<div className="text-sm text-foreground/80">{it.week_summary}</div>)}
                                                    </div>
                                                  ))}
                                                </div>
                                              </div>
                                            ))}
                                          </div>
                                        )}
                                      </div>
                                    )
                                  } catch {
                                    return <div className="text-sm text-muted-foreground">Unable to render preview. Check JSON syntax.</div>
                                  }
                                })()}
                              </div>
                            </div>
                          </div>
                        )}

                        <div className="mt-4 flex gap-2 border-t pt-4">
                          <Button size="sm" onClick={saveNewsletter}>Save Newsletter</Button>
                          <Button size="sm" variant="outline" onClick={() => { setEditingNl(null); setEditingPlayerCard(null); setEnhancedEditorMode('visual') }}>Cancel</Button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </TabsContent>

              {adminTabs.includes('tools') && (
                <TabsContent value="tools" className="space-y-6">
                  <div className="flex items-center justify-between gap-2 mb-4">
                    <h2 className="text-2xl font-semibold">Diagnostic Tools</h2>
                    <Button variant="outline" size="sm" onClick={loadSandboxTasks} disabled={sandboxLoading}>
                      {sandboxLoading ? 'Refreshing…' : 'Refresh tasks'}
                    </Button>
                  </div>

                  {sandboxError && (
                    <Alert variant="destructive">
                      <AlertDescription>{sandboxError}</AlertDescription>
                    </Alert>
                  )}

                  {sandboxLoading && !sandboxTasks.length ? (
                    <div className="rounded-lg border bg-card p-6 text-sm text-muted-foreground">
                      Loading sandbox tasks…
                    </div>
                  ) : null}

                  {!sandboxLoading && !sandboxTasks.length && !sandboxError ? (
                    <div className="rounded-lg border bg-card p-6 text-sm text-muted-foreground">
                      No sandbox tasks are currently registered.
                    </div>
                  ) : null}

                  <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                    {sandboxTasks.map((task) => {
                      const params = task?.parameters || []
                      const values = sandboxFormValues[task.task_id] || {}
                      const outcome = sandboxResults[task.task_id]
                      const isRunning = runningTaskId === task.task_id
                      const isCollapsed = (sandboxCollapsedTasks && Object.prototype.hasOwnProperty.call(sandboxCollapsedTasks, task.task_id))
                        ? !!sandboxCollapsedTasks[task.task_id]
                        : true
                      const ToggleIcon = isCollapsed ? ChevronRight : ChevronDown

                      return (
                        <Card key={task.task_id} className="rounded-xl border shadow-sm">
                          <CardHeader className={sandboxCardHeaderClasses('shadow-sm')}>
                            <div className="space-y-1">
                              <CardTitle className="text-lg">{task.label}</CardTitle>
                              <CardDescription>{task.description}</CardDescription>
                            </div>
                            <div className="flex items-center gap-2">
                              {outcome?.status === 'ok' ? (
                                <span className="text-xs font-medium text-emerald-600">Success</span>
                              ) : null}
                              {outcome?.status === 'error' ? (
                                <span
                                  className="max-w-[12rem] truncate text-xs font-medium text-rose-600"
                                  title={outcome.message}
                                >
                                  {outcome.message}
                                </span>
                              ) : null}
                              <button
                                type="button"
                                onClick={() => toggleSandboxTaskCollapsed(task.task_id)}
                                aria-expanded={!isCollapsed}
                                className="inline-flex items-center gap-1 rounded-md border border-border bg-secondary px-2 py-1 text-xs font-medium text-foreground/80 transition hover:bg-muted"
                              >
                                <ToggleIcon className="h-4 w-4" />
                                {isCollapsed ? 'Expand' : 'Collapse'}
                              </button>
                            </div>
                          </CardHeader>
                          {!isCollapsed && (
                            <CardContent className="px-4 py-4 space-y-4">
                              <form
                                className="space-y-4"
                                onSubmit={(event) => {
                                  event.preventDefault()
                                  runSandboxTask(task)
                                }}
                              >
                                {params.length > 0 ? (
                                  <div className="grid gap-3">
                                    {params.map((param) => {
                                      const selectOptions = Array.isArray(param.options) ? param.options : []
                                      const hasSelect = param.type === 'select' && selectOptions.length > 0
                                      const currentValue = values[param.name] ?? ''
                                      const selectValue = hasSelect ? String(currentValue ?? '') : ''
                                      const selectLookup = hasSelect
                                        ? new Map(selectOptions.map((option, index) => {
                                          const optValue = option?.value ?? option?.label ?? index
                                          return [String(optValue), option]
                                        }))
                                        : null

                                      return (
                                        <label key={param.name} className="flex flex-col gap-2 text-sm font-medium text-foreground/80">
                                          <span>{param.label}</span>
                                          {param.type === 'checkbox' ? (
                                            <div className="flex items-center gap-2 text-sm font-normal">
                                              <input
                                                type="checkbox"
                                                checked={!!values[param.name]}
                                                onChange={handleSandboxInputChange(task.task_id, param.name, param.type)}
                                              />
                                              {param.help ? <span className="text-muted-foreground">{param.help}</span> : null}
                                            </div>
                                          ) : hasSelect ? (
                                            <Select
                                              value={selectValue}
                                              onValueChange={(newValue) => {
                                                if (!selectLookup) {
                                                  handleSandboxSelectChange(task.task_id, param, newValue ? { value: newValue } : null, params)
                                                  return
                                                }
                                                const option = selectLookup.get(newValue)
                                                handleSandboxSelectChange(
                                                  task.task_id,
                                                  param,
                                                  option || (newValue ? { value: newValue } : null),
                                                  params
                                                )
                                              }}
                                            >
                                              <SelectTrigger>
                                                <SelectValue placeholder={param.placeholder || 'Select option…'} />
                                              </SelectTrigger>
                                              <SelectContent>
                                                {selectOptions.map((option, index) => {
                                                  const optionValue = String(option?.value ?? option?.label ?? index)
                                                  const optionLabel = option?.label ?? option?.value ?? optionValue
                                                  return (
                                                    <SelectItem key={`${optionValue}-${index}`} value={optionValue}>
                                                      {optionLabel}
                                                    </SelectItem>
                                                  )
                                                })}
                                              </SelectContent>
                                            </Select>
                                          ) : (
                                            <Input
                                              type={param.type || 'text'}
                                              value={values[param.name] ?? ''}
                                              placeholder={param.placeholder || ''}
                                              onChange={handleSandboxInputChange(task.task_id, param.name, param.type)}
                                            />
                                          )}
                                          {param.type !== 'checkbox' && param.help ? (
                                            <span className="text-xs font-normal text-muted-foreground">{param.help}</span>
                                          ) : null}
                                        </label>
                                      )
                                    })}
                                  </div>
                                ) : (
                                  <p className="text-sm text-muted-foreground">No parameters required.</p>
                                )}
                                <div className="flex items-center gap-3">
                                  <Button type="submit" size="sm" disabled={isRunning}>
                                    {isRunning ? 'Running…' : 'Run task'}
                                  </Button>
                                  {outcome?.status === 'ok' && (
                                    <span className="text-sm text-emerald-600">Success</span>
                                  )}
                                  {outcome?.status === 'error' && (
                                    <span className="text-sm text-rose-600">{outcome.message}</span>
                                  )}
                                </div>
                                {task.task_id !== 'list-missing-sofascore-ids' && outcome?.status === 'ok' && outcome.result && (
                                  <pre className="mt-3 max-h-64 overflow-auto rounded-md bg-foreground p-3 text-xs text-card">
                                    {JSON.stringify(outcome.result, null, 2)}
                                  </pre>
                                )}
                                {outcome?.status === 'error' && outcome.detail && (
                                  <pre className="mt-3 max-h-64 overflow-auto rounded-md bg-rose-900/80 p-3 text-xs text-rose-100">
                                    {typeof outcome.detail === 'string'
                                      ? outcome.detail
                                      : JSON.stringify(outcome.detail, null, 2)}
                                  </pre>
                                )}
                              </form>
                              {task.task_id === 'list-missing-sofascore-ids' && (
                                <div className="border-t px-4 py-4 space-y-4">
                                  {sofascoreStatus && (
                                    <Alert variant={sofascoreStatus.type === 'error' ? 'destructive' : 'default'}>
                                      <AlertDescription>{sofascoreStatus.message}</AlertDescription>
                                    </Alert>
                                  )}
                                  {sofascorePlayers.length === 0 ? (
                                    <p className="text-sm text-muted-foreground">
                                      Run the task to load players missing Sofascore ids.
                                    </p>
                                  ) : (
                                    <div className="overflow-auto">
                                      <table className="min-w-full text-sm">
                                        <thead>
                                          <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
                                            <th className="pb-2 pr-4">Player</th>
                                            <th className="pb-2 pr-4">Parent Club</th>
                                            <th className="pb-2 pr-4">Loan Club</th>
                                            <th className="pb-2 pr-4">Sofascore ID</th>
                                            <th className="pb-2 pr-4">Actions</th>
                                          </tr>
                                        </thead>
                                        <tbody>
                                          {sofascorePlayers.map((player, index) => {
                                            const rowKey = player?.__row_key || sofascoreRowKey(player, index)
                                            const isSupplemental = Boolean(player?.is_supplemental)
                                            const apiLabel = player?.player_id
                                              ? `API #${player.player_id}`
                                              : isSupplemental && player?.supplemental_id
                                                ? `Supp #${player.supplemental_id}`
                                                : '—'
                                            const value = sofascoreInputs[rowKey] ?? (player?.sofascore_id ? String(player.sofascore_id) : '')
                                            return (
                                              <tr key={rowKey} className="border-t border-border last:border-b">
                                                <td className="py-2 pr-4 align-top">
                                                  <div className="font-medium text-foreground">{player?.player_name || (player?.player_id ? `Player #${player.player_id}` : 'Supplemental player')}</div>
                                                  <div className="text-xs text-muted-foreground">{apiLabel}</div>
                                                </td>
                                                <td className="py-2 pr-4 align-top text-muted-foreground">{player?.primary_team || '—'}</td>
                                                <td className="py-2 pr-4 align-top text-muted-foreground">{player?.loan_team || '—'}</td>
                                                <td className="py-2 pr-4 align-top">
                                                  <Input
                                                    aria-label={`Sofascore id for ${player?.player_name || apiLabel}`}
                                                    value={value}
                                                    placeholder="e.g. 1101989"
                                                    onChange={(event) => {
                                                      const next = event.target.value
                                                      setSofascoreInputs((prev) => ({ ...prev, [rowKey]: next }))
                                                    }}
                                                    className="w-36"
                                                  />
                                                </td>
                                                <td className="py-2 pr-4 align-top">
                                                  <div className="flex flex-wrap gap-2">
                                                    <Button
                                                      size="sm"
                                                      disabled={sofascoreUpdatingKey === rowKey || !(value && value.trim())}
                                                      onClick={() => handleSofascoreAssign(player, (value || '').trim())}
                                                    >
                                                      {sofascoreUpdatingKey === rowKey ? 'Saving…' : 'Save'}
                                                    </Button>
                                                    <Button
                                                      size="sm"
                                                      variant="outline"
                                                      disabled={sofascoreUpdatingKey === rowKey}
                                                      onClick={() => handleSofascoreAssign(player, '')}
                                                    >
                                                      Clear
                                                    </Button>
                                                    {isSupplemental && (
                                                      <Button
                                                        size="sm"
                                                        variant="destructive"
                                                        disabled={sofascoreUpdatingKey === rowKey}
                                                        onClick={() => handleSupplementalDelete(player)}
                                                      >
                                                        Delete
                                                      </Button>
                                                    )}
                                                  </div>
                                                </td>
                                              </tr>
                                            )
                                          })}
                                        </tbody>
                                      </table>
                                    </div>
                                  )}
                                </div>
                              )}
                            </CardContent>
                          )}
                        </Card>
                      )
                    })}
                  </div>
                </TabsContent>
              )}

              <TabsContent value="settings" className="space-y-6">
                <div className="border rounded p-4">
                  <h2 className="font-semibold mb-3">Newsletter Settings</h2>
                  <div className="space-y-2">
                    {[
                      ['brave_soft_rank', 'Soft Rank (quality-first ordering)'],
                      ['brave_site_boost', 'Site Boost (local/club sources)'],
                      ['brave_cup_synonyms', 'Cup Synonyms (EFL/FA/League)'],
                      ['search_strict_range', 'Strict Date Window (drop undated)'],
                    ].map(([k, label]) => (
                      <label key={k} className="flex items-center gap-2">
                        <input type="checkbox" checked={!!settings[k]} onChange={e => setSettings({ ...settings, [k]: e.target.checked })} />
                        <span>{label}</span>
                      </label>
                    ))}
                  </div>
                  <div className="mt-2">
                    <Button onClick={saveSettings}>Save Settings</Button>
                  </div>
                </div>
                <div className="border rounded p-4">
                  <h2 className="font-semibold mb-3">Pending Player Flags</h2>
                  {flags.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No pending flags.</p>
                  ) : (
                    <div className="space-y-3">
                      {flags.map(f => {
                        const editor = flagEditors[f.id]
                        const loanOptions = editor?.loans || []
                        const teamOptions = buildTeamOptionsForLoan(loanOptions)
                        const selectedLoan = loanOptions.find((l) => l.id === editor?.selectedLoanId)
                        return (
                          <div key={f.id} className="border rounded p-3">
                            <div className="text-sm font-semibold">Flag #{f.id}</div>
                            <div className="mt-1 grid gap-1 text-sm text-foreground/80">
                              <div>Player API: {f.player_api_id}</div>
                              <div>Primary Team API: {f.primary_team_api_id}</div>
                              {f.loan_team_api_id && <div>Loan Team API: {f.loan_team_api_id}</div>}
                              {f.season && <div>Season: {f.season}</div>}
                              <div className="text-foreground">Reason: {f.reason}</div>
                            </div>
                            <div className="mt-2 flex flex-wrap gap-2">
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => (editor ? closeFlagEditor(f.id) : openFlagEditor(f))}
                                disabled={editor?.saving}
                              >
                                {editor ? 'Hide editor' : 'Edit loan assignment'}
                              </Button>
                              <Button size="sm" onClick={() => resolveFlag(f.id, false)}>Resolve</Button>
                              <Button size="sm" variant="outline" onClick={() => resolveFlag(f.id, true)}>Resolve + Deactivate Loan</Button>
                            </div>
                            {editor && (
                              <div className="mt-3 space-y-3 rounded border border-dashed bg-card/70 p-3 text-sm">
                                {editor.loading ? (
                                  <div className="flex items-center gap-2 text-muted-foreground">
                                    <Loader2 className="h-4 w-4 animate-spin" /> Loading loan details…
                                  </div>
                                ) : editor.error ? (
                                  <div className="rounded border border-rose-200 bg-rose-50 p-2 text-rose-700">{editor.error}</div>
                                ) : (
                                  <>
                                    {loanOptions.length > 1 && (
                                      <div className="grid gap-1">
                                        <Label className="text-xs uppercase tracking-wide text-muted-foreground">Loan record</Label>
                                        <Select
                                          value={String(editor.selectedLoanId)}
                                          onValueChange={(value) => selectFlagLoanRecord(f.id, value)}
                                        >
                                          <SelectTrigger>
                                            <SelectValue />
                                          </SelectTrigger>
                                          <SelectContent>
                                            {loanOptions.map((loan) => (
                                              <SelectItem key={loan.id} value={String(loan.id)}>
                                                {loan.primary_team_name} → {loan.loan_team_name} {loan.is_active ? '(active)' : '(inactive)'}
                                              </SelectItem>
                                            ))}
                                          </SelectContent>
                                        </Select>
                                      </div>
                                    )}
                                    {selectedLoan && (
                                      <div className="rounded bg-secondary p-2 text-xs text-muted-foreground">
                                        Current assignment: {selectedLoan.primary_team_name} → {selectedLoan.loan_team_name}
                                      </div>
                                    )}
                                    <div className="grid gap-3 sm:grid-cols-2">
                                      <div className="space-y-1">
                                        <Label className="text-xs uppercase tracking-wide text-muted-foreground">Primary team</Label>
                                        <TeamSelect
                                          teams={teamOptions}
                                          value={editor.primaryTeamId ?? null}
                                          onChange={(id) => setFlagPrimaryTeam(f.id, id)}
                                          placeholder="Select primary team…"
                                        />
                                      </div>
                                      <div className="space-y-1">
                                        <Label className="text-xs uppercase tracking-wide text-muted-foreground">Loan team</Label>
                                        <TeamSelect
                                          teams={teamOptions}
                                          value={editor.loanTeamId ?? null}
                                          onChange={(id) => setFlagLoanTeam(f.id, id)}
                                          placeholder="Select loan team…"
                                        />
                                      </div>
                                    </div>
                                    <div className="flex flex-wrap gap-2">
                                      <Button
                                        size="sm"
                                        onClick={() => saveFlagLoanChanges(f)}
                                        disabled={editor.saving}
                                      >
                                        {editor.saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Save loan changes
                                      </Button>
                                      <Button
                                        size="sm"
                                        variant="ghost"
                                        onClick={() => closeFlagEditor(f.id)}
                                        disabled={editor.saving}
                                      >
                                        Cancel
                                      </Button>
                                    </div>
                                  </>
                                )}
                              </div>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>
              </TabsContent>
            </Tabs>
          </>
        ) : (
          <div className="rounded-lg border border-dashed bg-muted/40 p-6 text-sm text-muted-foreground space-y-3">
            <p>Admin tools are locked. Sign in with an approved admin email and store the API key above.</p>
            <div className="flex flex-wrap gap-2">
              {!hasAdminToken && (
                <Button size="sm" onClick={openLoginModal}>
                  <LogIn className="mr-1 h-4 w-4" /> Sign in as admin
                </Button>
              )}
              {!hasStoredKey && (
                <Button size="sm" variant="outline" onClick={startEditingKey}>
                  <KeyRound className="mr-1 h-4 w-4" /> Add API key
                </Button>
              )}
            </div>
          </div>
        )}

        {/* Edit Player Dialog */}
        {editingPlayerDialog && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50" onClick={() => setEditingPlayerDialog(null)}>
            <div className="bg-card rounded-lg p-6 max-w-2xl w-full max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
              <h2 className="text-xl font-semibold mb-4">Edit Player</h2>

              <div className="space-y-4">
                {/* Player Name */}
                <div>
                  <label className="text-sm font-medium text-foreground/80 block mb-1">Player Name *</label>
                  <input
                    type="text"
                    className="border rounded p-2 text-sm w-full"
                    value={editPlayerForm.name}
                    onChange={(e) => setEditPlayerForm({ ...editPlayerForm, name: e.target.value })}
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  {/* Position */}
                  <div>
                    <label className="text-sm font-medium text-foreground/80 block mb-1">Position</label>
                    <select
                      className="border rounded p-2 text-sm w-full"
                      value={editPlayerForm.position}
                      onChange={(e) => setEditPlayerForm({ ...editPlayerForm, position: e.target.value })}
                    >
                      <option value="">Select position...</option>
                      {playerFieldOptions.positions.map(pos => (
                        <option key={pos} value={pos}>{pos}</option>
                      ))}
                    </select>
                  </div>

                  {/* Nationality */}
                  <div>
                    <label className="text-sm font-medium text-foreground/80 block mb-1">Nationality</label>
                    <select
                      className="border rounded p-2 text-sm w-full"
                      value={editPlayerForm.nationality}
                      onChange={(e) => setEditPlayerForm({ ...editPlayerForm, nationality: e.target.value })}
                    >
                      <option value="">Select nationality...</option>
                      {playerFieldOptions.nationalities.map(nat => (
                        <option key={nat} value={nat}>{nat}</option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  {/* Age */}
                  <div>
                    <label className="text-sm font-medium text-foreground/80 block mb-1">Age</label>
                    <input
                      type="number"
                      className="border rounded p-2 text-sm w-full"
                      value={editPlayerForm.age}
                      onChange={(e) => setEditPlayerForm({ ...editPlayerForm, age: e.target.value })}
                    />
                  </div>

                  {/* Sofascore ID */}
                  <div>
                    <label className="text-sm font-medium text-foreground/80 block mb-1">Sofascore ID</label>
                    <input
                      type="number"
                      className="border rounded p-2 text-sm w-full"
                      value={editPlayerForm.sofascore_id}
                      onChange={(e) => setEditPlayerForm({ ...editPlayerForm, sofascore_id: e.target.value })}
                    />
                  </div>
                </div>

                {/* Primary Team */}
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-sm font-medium text-foreground/80">Primary Team (Parent Club) *</label>
                    <label className="flex items-center gap-1 text-xs text-muted-foreground cursor-pointer">
                      <input
                        type="checkbox"
                        checked={editPlayerForm.use_custom_primary_team}
                        onChange={(e) => setEditPlayerForm({
                          ...editPlayerForm,
                          use_custom_primary_team: e.target.checked,
                          primary_team_id: '',
                          custom_primary_team_name: ''
                        })}
                      />
                      Custom team
                    </label>
                  </div>
                  {editPlayerForm.use_custom_primary_team ? (
                    <input
                      type="text"
                      className="border rounded p-2 text-sm w-full"
                      placeholder="e.g. Portsmouth, Sunderland"
                      value={editPlayerForm.custom_primary_team_name}
                      onChange={(e) => setEditPlayerForm({ ...editPlayerForm, custom_primary_team_name: e.target.value })}
                    />
                  ) : (
                    <TeamSelect
                      teams={runTeams}
                      value={editPlayerForm.primary_team_id}
                      onChange={(id) => setEditPlayerForm({ ...editPlayerForm, primary_team_id: id })}
                      placeholder="Select primary team..."
                    />
                  )}
                </div>

                {/* Loan Team */}
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-sm font-medium text-foreground/80">Loan Team (Current Club) *</label>
                    <label className="flex items-center gap-1 text-xs text-muted-foreground cursor-pointer">
                      <input
                        type="checkbox"
                        checked={editPlayerForm.use_custom_loan_team}
                        onChange={(e) => setEditPlayerForm({
                          ...editPlayerForm,
                          use_custom_loan_team: e.target.checked,
                          loan_team_id: '',
                          custom_loan_team_name: ''
                        })}
                      />
                      Custom team
                    </label>
                  </div>
                  {editPlayerForm.use_custom_loan_team ? (
                    <input
                      type="text"
                      className="border rounded p-2 text-sm w-full"
                      placeholder="e.g. Sheffield Wednesday, Hull City"
                      value={editPlayerForm.custom_loan_team_name}
                      onChange={(e) => setEditPlayerForm({ ...editPlayerForm, custom_loan_team_name: e.target.value })}
                    />
                  ) : (
                    <TeamSelect
                      teams={runTeams}
                      value={editPlayerForm.loan_team_id}
                      onChange={(id) => setEditPlayerForm({ ...editPlayerForm, loan_team_id: id })}
                      placeholder="Select loan team..."
                    />
                  )}
                </div>

                {/* Season/Window */}
                <div>
                  <label className="text-sm font-medium text-foreground/80 block mb-1">Season / Window</label>
                  <select
                    className="border rounded p-2 text-sm w-full"
                    value={editPlayerForm.window_key}
                    onChange={(e) => setEditPlayerForm({ ...editPlayerForm, window_key: e.target.value })}
                  >
                    <option value="">Select season...</option>
                    {generateSeasonOptions().map(opt => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Actions */}
              <div className="mt-6 flex gap-3 justify-end">
                <Button variant="outline" onClick={() => setEditingPlayerDialog(null)}>
                  Cancel
                </Button>
                <Button onClick={savePlayerEdit}>
                  Save Changes
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Confirmation Dialogs */}

      {/* Delete Supplemental Loan Confirmation */}
      <Dialog open={!!deleteSupplementalLoanConfirm} onOpenChange={() => setDeleteSupplementalLoanConfirm(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Supplemental Loan?</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete the supplemental loan for <strong>{deleteSupplementalLoanConfirm?.player_name}</strong>?
              This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteSupplementalLoanConfirm(null)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={confirmDeleteSupplementalLoan}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Newsletter Confirmation */}
      <Dialog open={!!deleteNewsletterConfirm} onOpenChange={() => setDeleteNewsletterConfirm(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Newsletter?</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete {deleteNewsletterConfirm?.label}?
              This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteNewsletterConfirm(null)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={confirmDeleteNewsletter}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Player from Newsletter Confirmation */}
      <Dialog open={!!deletePlayerFromNlConfirm} onOpenChange={() => setDeletePlayerFromNlConfirm(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remove Player?</DialogTitle>
            <DialogDescription>
              Are you sure you want to remove this player from the newsletter?
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeletePlayerFromNlConfirm(null)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={confirmDeletePlayerFromNewsletter}>
              Remove
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Player Confirmation */}
      <Dialog open={!!deletePlayerConfirm} onOpenChange={() => setDeletePlayerConfirm(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Player?</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete <strong>"{deletePlayerConfirm?.playerName}"</strong>?
              <br /><br />
              {deletePlayerConfirm?.warningMessage}
              <br /><br />
              This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeletePlayerConfirm(null)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={confirmDeletePlayer}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
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

function AdminSandboxPage() {
  const [tasks, setTasks] = useState([])
  const [collapsedTasks, setCollapsedTasks] = useState({})
  const [formValues, setFormValues] = useState({})
  const [results, setResults] = useState({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [runningTaskId, setRunningTaskId] = useState(null)
  const [sofascorePlayers, setSofascorePlayers] = useState([])
  const [sofascoreInputs, setSofascoreInputs] = useState({})
  const [sofascoreUpdatingKey, setSofascoreUpdatingKey] = useState(null)
  const [sofascoreStatus, setSofascoreStatus] = useState(null)
  const navigate = useNavigate()
  const { token, hasApiKey } = useAuth()

  useEffect(() => {
    if (token && APIService.userToken !== token) {
      APIService.setUserToken(token)
    }
  }, [token])

  const buildDefaults = useCallback((taskList) => {
    const defaults = {}
    for (const task of taskList) {
      const params = task?.parameters || []
      defaults[task.task_id] = params.reduce((acc, param) => {
        if (param.type === 'checkbox') {
          acc[param.name] = false
        } else {
          acc[param.name] = ''
        }
        return acc
      }, {})
    }
    return defaults
  }, [])

  const ensureAdminSession = useCallback(() => {
    const storedToken = APIService.userToken || (typeof localStorage !== 'undefined' ? localStorage.getItem('academy_watch_user_token') : null)
    if (storedToken && !APIService.userToken) {
      APIService.setUserToken(storedToken)
    }
    if (!storedToken) {
      const err = new Error('Admin login required. Sign in with an admin email to continue.')
      err.code = 'missing_token'
      throw err
    }
    const storedKey = APIService.adminKey || (typeof localStorage !== 'undefined' ? localStorage.getItem('academy_watch_admin_key') : null)
    if (storedKey && !APIService.adminKey) {
      APIService.setAdminKey(storedKey)
    }
    if (!storedKey) {
      const err = new Error('Admin API key required. Add your key in the admin dashboard.')
      err.code = 'missing_key'
      throw err
    }
  }, [])

  const loadTasks = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      ensureAdminSession()

      let payload
      try {
        payload = await APIService.adminSandboxTasks()
      } catch (err) {
        if (err?.status === 401) {
          await APIService.refreshProfile()
          ensureAdminSession()
          payload = await APIService.adminSandboxTasks()
        } else {
          throw err
        }
      }
      const taskList = Array.isArray(payload?.tasks) ? payload.tasks : []
      setTasks(taskList)
      setCollapsedTasks((prev) => mergeCollapseState(prev, taskList))
      setFormValues((prev) => ({ ...buildDefaults(taskList), ...prev }))
    } catch (err) {
      setError(err?.message || 'Failed to load sandbox tasks')
    } finally {
      setLoading(false)
    }
  }, [buildDefaults, ensureAdminSession])

  useEffect(() => {
    if (!token) {
      setLoading(false)
      setError('Admin login required. Sign in with an admin email to continue.')
      return
    }
    if (!hasApiKey) {
      setLoading(false)
      setError('Admin API key required. Add your key in the admin dashboard.')
      return
    }
    loadTasks()
  }, [token, hasApiKey, loadTasks])

  const toggleTaskCollapsed = useCallback((taskId) => {
    setCollapsedTasks((prev) => toggleCollapseState(prev, taskId))
  }, [])

  const handleInputChange = useCallback((taskId, fieldName, fieldType) => (event) => {
    const value = fieldType === 'checkbox' ? event.target.checked : event.target.value
    setFormValues((prev) => ({
      ...prev,
      [taskId]: {
        ...(prev[taskId] || {}),
        [fieldName]: value,
      },
    }))
  }, [])

  const handleSelectChange = useCallback((taskId, param, option, params) => {
    setFormValues((prev) => {
      const updates = buildSelectUpdates(param, option, params)
      if (!updates || Object.keys(updates).length === 0) {
        return prev
      }
      const nextTaskValues = { ...(prev[taskId] || {}) }
      for (const [key, value] of Object.entries(updates)) {
        nextTaskValues[key] = value
      }
      return { ...prev, [taskId]: nextTaskValues }
    })
  }, [])

  const buildPayload = useCallback((task) => {
    const params = task?.parameters || []
    const currentValues = formValues[task.task_id] || {}
    const payload = {}
    for (const param of params) {
      const rawValue = currentValues[param.name]
      if (param.type === 'checkbox') {
        payload[param.name] = !!rawValue
        continue
      }
      if (rawValue === '' || typeof rawValue === 'undefined' || rawValue === null) {
        continue
      }
      if (param.type === 'number') {
        const numeric = Number(rawValue)
        if (!Number.isNaN(numeric)) {
          payload[param.name] = numeric
        }
      } else {
        payload[param.name] = rawValue
      }
    }
    return payload
  }, [formValues])

  const runTask = useCallback(async (task) => {
    if (!task?.task_id) return
    setRunningTaskId(task.task_id)
    try {
      const payload = buildPayload(task)
      ensureAdminSession()
      let result
      try {
        result = await APIService.adminSandboxRun(task.task_id, payload)
      } catch (err) {
        if (err?.status === 401) {
          await APIService.refreshProfile()
          ensureAdminSession()
          result = await APIService.adminSandboxRun(task.task_id, payload)
        } else {
          throw err
        }
      }
      if (task.task_id === 'list-missing-sofascore-ids') {
        const players = Array.isArray(result?.payload?.players) ? result.payload.players : []
        const enriched = players.map((player, index) => ({
          ...player,
          __row_key: sofascoreRowKey(player, index),
        }))
        const inputDefaults = {}
        for (const player of enriched) {
          const rowKey = player.__row_key
          inputDefaults[rowKey] = player?.sofascore_id ? String(player.sofascore_id) : ''
        }
        setSofascorePlayers(enriched)
        setSofascoreInputs(inputDefaults)
        setSofascoreStatus(null)
        setSofascoreUpdatingKey(null)
      }
      if (task.task_id === 'update-player-sofascore-id') {
        setSofascoreStatus({ type: 'success', message: result?.summary || 'Sofascore id updated.' })
      }
      setResults((prev) => ({
        ...prev,
        [task.task_id]: { status: 'ok', result },
      }))
    } catch (err) {
      if (task?.task_id === 'update-player-sofascore-id') {
        setSofascoreStatus({ type: 'error', message: err?.message || 'Failed to update Sofascore id.' })
      }
      setResults((prev) => ({
        ...prev,
        [task.task_id]: {
          status: 'error',
          message: err?.message || 'Task execution failed',
          detail: err?.body,
        },
      }))
    } finally {
      setRunningTaskId(null)
    }
  }, [buildPayload, ensureAdminSession])

  const handleSofascoreAssign = useCallback(async (row, inputValue) => {
    const payload = buildSofascoreUpdatePayload(row, typeof inputValue === 'string' ? inputValue.trim() : inputValue)
    if (!payload) {
      setSofascoreStatus({ type: 'error', message: 'Unable to update Sofascore id for this row.' })
      return
    }

    const rowKey = row?.__row_key || sofascoreRowKey(row)
    setSofascoreStatus(null)
    setSofascoreUpdatingKey(rowKey)
    try {
      ensureAdminSession()
      const result = await APIService.adminSandboxRun('update-player-sofascore-id', payload)
      setSofascoreStatus({ type: 'success', message: result?.summary || 'Sofascore id updated.' })
      setSofascorePlayers((prev) => prev.filter((item) => (item.__row_key || sofascoreRowKey(item)) !== rowKey))
      setSofascoreInputs((prev) => {
        const next = { ...prev }
        delete next[rowKey]
        return next
      })
    } catch (err) {
      setSofascoreStatus({ type: 'error', message: err?.message || 'Failed to update Sofascore id.' })
    } finally {
      setSofascoreUpdatingKey(null)
    }
  }, [ensureAdminSession])

  const handleSupplementalDelete = useCallback(async (row) => {
    if (!row?.supplemental_id) return
    const rowKey = row?.__row_key || sofascoreRowKey(row)
    setSofascoreStatus(null)
    setSofascoreUpdatingKey(rowKey)
    try {
      ensureAdminSession()
      const result = await APIService.adminSandboxRun('delete-supplemental-loan', {
        supplemental_id: row.supplemental_id,
        confirm: true,
      })
      setSofascoreStatus({ type: 'success', message: result?.summary || 'Supplemental row deleted.' })
      setSofascorePlayers((prev) => prev.filter((item) => (item.__row_key || sofascoreRowKey(item)) !== rowKey))
      setSofascoreInputs((prev) => {
        const next = { ...prev }
        delete next[rowKey]
        return next
      })
    } catch (err) {
      setSofascoreStatus({ type: 'error', message: err?.message || 'Failed to delete supplemental loan.' })
    } finally {
      setSofascoreUpdatingKey(null)
    }
  }, [ensureAdminSession])

  return (
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-6">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => navigate('/admin')}>
            ← Back to admin dashboard
          </Button>
          <h1 className="text-2xl font-semibold">Admin Sandbox</h1>
        </div>
        <Button variant="outline" size="sm" onClick={loadTasks} disabled={loading}>
          {loading ? 'Refreshing…' : 'Refresh tasks'}
        </Button>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {loading && !tasks.length ? (
        <div className="rounded-lg border bg-card p-6 text-sm text-muted-foreground">
          Loading sandbox tasks…
        </div>
      ) : null}

      {!loading && !tasks.length && !error ? (
        <div className="rounded-lg border bg-card p-6 text-sm text-muted-foreground">
          No sandbox tasks are currently registered.
        </div>
      ) : null}

      <div className="grid gap-4">
        {tasks.map((task) => {
          const params = task?.parameters || []
          const values = formValues[task.task_id] || {}
          const outcome = results[task.task_id]
          const isRunning = runningTaskId === task.task_id
          const isCollapsed = (collapsedTasks && Object.prototype.hasOwnProperty.call(collapsedTasks, task.task_id))
            ? !!collapsedTasks[task.task_id]
            : true
          const ToggleIcon = isCollapsed ? ChevronRight : ChevronDown

          return (
            <div key={task.task_id} className="rounded-xl border bg-card shadow-sm">
              <div className={sandboxCardHeaderClasses('shadow-sm')}>
                <div className="space-y-1">
                  <h2 className="text-lg font-semibold">{task.label}</h2>
                  <p className="text-sm text-muted-foreground">{task.description}</p>
                </div>
                <div className="flex items-center gap-2">
                  {outcome?.status === 'ok' ? (
                    <span className="text-xs font-medium text-emerald-600">Success</span>
                  ) : null}
                  {outcome?.status === 'error' ? (
                    <span
                      className="max-w-[12rem] truncate text-xs font-medium text-rose-600"
                      title={outcome.message}
                    >
                      {outcome.message}
                    </span>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => toggleTaskCollapsed(task.task_id)}
                    aria-expanded={!isCollapsed}
                    className="inline-flex items-center gap-1 rounded-md border border-border bg-secondary px-2 py-1 text-xs font-medium text-foreground/80 transition hover:bg-muted"
                  >
                    <ToggleIcon className="h-4 w-4" />
                    {isCollapsed ? 'Expand' : 'Collapse'}
                  </button>
                </div>
              </div>
              {!isCollapsed && (
                <>
                  <form
                    className="px-4 py-4 space-y-4"
                    onSubmit={(event) => {
                      event.preventDefault()
                      runTask(task)
                    }}
                  >
                    {params.length > 0 ? (
                      <div className="grid gap-3 md:grid-cols-2">
                        {params.map((param) => {
                          const selectOptions = Array.isArray(param.options) ? param.options : []
                          const hasSelect = param.type === 'select' && selectOptions.length > 0
                          const currentValue = values[param.name] ?? ''
                          const selectValue = hasSelect ? String(currentValue ?? '') : ''
                          const selectLookup = hasSelect
                            ? new Map(selectOptions.map((option, index) => {
                              const optValue = option?.value ?? option?.label ?? index
                              return [String(optValue), option]
                            }))
                            : null

                          return (
                            <label key={param.name} className="flex flex-col gap-2 text-sm font-medium text-foreground/80">
                              <span>{param.label}</span>
                              {param.type === 'checkbox' ? (
                                <div className="flex items-center gap-2 text-sm font-normal">
                                  <input
                                    type="checkbox"
                                    checked={!!values[param.name]}
                                    onChange={handleInputChange(task.task_id, param.name, param.type)}
                                  />
                                  {param.help ? <span className="text-muted-foreground">{param.help}</span> : null}
                                </div>
                              ) : hasSelect ? (
                                <Select
                                  value={selectValue}
                                  onValueChange={(newValue) => {
                                    if (!selectLookup) {
                                      handleSelectChange(task.task_id, param, newValue ? { value: newValue } : null, params)
                                      return
                                    }
                                    const option = selectLookup.get(newValue)
                                    handleSelectChange(
                                      task.task_id,
                                      param,
                                      option || (newValue ? { value: newValue } : null),
                                      params
                                    )
                                  }}
                                >
                                  <SelectTrigger>
                                    <SelectValue placeholder={param.placeholder || 'Select option…'} />
                                  </SelectTrigger>
                                  <SelectContent>
                                    {selectOptions.map((option, index) => {
                                      const optionValue = String(option?.value ?? option?.label ?? index)
                                      const optionLabel = option?.label ?? option?.value ?? optionValue
                                      return (
                                        <SelectItem key={`${optionValue}-${index}`} value={optionValue}>
                                          {optionLabel}
                                        </SelectItem>
                                      )
                                    })}
                                  </SelectContent>
                                </Select>
                              ) : (
                                <Input
                                  type={param.type || 'text'}
                                  value={values[param.name] ?? ''}
                                  placeholder={param.placeholder || ''}
                                  onChange={handleInputChange(task.task_id, param.name, param.type)}
                                />
                              )}
                              {param.type !== 'checkbox' && param.help ? (
                                <span className="text-xs font-normal text-muted-foreground">{param.help}</span>
                              ) : null}
                            </label>
                          )
                        })}
                      </div>
                    ) : (
                      <p className="text-sm text-muted-foreground">No parameters required.</p>
                    )}
                    <div className="flex items-center gap-3">
                      <Button type="submit" size="sm" disabled={isRunning}>
                        {isRunning ? 'Running…' : 'Run task'}
                      </Button>
                      {outcome?.status === 'ok' && (
                        <span className="text-sm text-emerald-600">Success</span>
                      )}
                      {outcome?.status === 'error' && (
                        <span className="text-sm text-rose-600">{outcome.message}</span>
                      )}
                    </div>
                    {task.task_id !== 'list-missing-sofascore-ids' && outcome?.status === 'ok' && outcome.result && (
                      <pre className="mt-3 max-h-64 overflow-auto rounded-md bg-foreground p-3 text-xs text-card">
                        {JSON.stringify(outcome.result, null, 2)}
                      </pre>
                    )}
                    {outcome?.status === 'error' && outcome.detail && (
                      <pre className="mt-3 max-h-64 overflow-auto rounded-md bg-rose-900/80 p-3 text-xs text-rose-100">
                        {typeof outcome.detail === 'string'
                          ? outcome.detail
                          : JSON.stringify(outcome.detail, null, 2)}
                      </pre>
                    )}
                  </form>
                  {task.task_id === 'list-missing-sofascore-ids' && (
                    <div className="border-t px-4 py-4 space-y-4">
                      {sofascoreStatus && (
                        <Alert variant={sofascoreStatus.type === 'error' ? 'destructive' : 'default'}>
                          <AlertDescription>{sofascoreStatus.message}</AlertDescription>
                        </Alert>
                      )}
                      {sofascorePlayers.length === 0 ? (
                        <p className="text-sm text-muted-foreground">
                          Run the task to load players missing Sofascore ids.
                        </p>
                      ) : (
                        <div className="overflow-auto">
                          <table className="min-w-full text-sm">
                            <thead>
                              <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
                                <th className="pb-2 pr-4">Player</th>
                                <th className="pb-2 pr-4">Parent Club</th>
                                <th className="pb-2 pr-4">Loan Club</th>
                                <th className="pb-2 pr-4">Sofascore ID</th>
                                <th className="pb-2 pr-4">Actions</th>
                              </tr>
                            </thead>
                            <tbody>
                              {sofascorePlayers.map((player, index) => {
                                const rowKey = player?.__row_key || sofascoreRowKey(player, index)
                                const isSupplemental = Boolean(player?.is_supplemental)
                                const apiLabel = player?.player_id
                                  ? `API #${player.player_id}`
                                  : isSupplemental && player?.supplemental_id
                                    ? `Supp #${player.supplemental_id}`
                                    : '—'
                                const value = sofascoreInputs[rowKey] ?? (player?.sofascore_id ? String(player.sofascore_id) : '')
                                return (
                                  <tr key={rowKey} className="border-t border-border last:border-b">
                                    <td className="py-2 pr-4 align-top">
                                      <div className="font-medium text-foreground">{player?.player_name || (player?.player_id ? `Player #${player.player_id}` : 'Supplemental player')}</div>
                                      <div className="text-xs text-muted-foreground">{apiLabel}</div>
                                    </td>
                                    <td className="py-2 pr-4 align-top text-muted-foreground">{player?.primary_team || '—'}</td>
                                    <td className="py-2 pr-4 align-top text-muted-foreground">{player?.loan_team || '—'}</td>
                                    <td className="py-2 pr-4 align-top">
                                      <Input
                                        aria-label={`Sofascore id for ${player?.player_name || apiLabel}`}
                                        value={value}
                                        placeholder="e.g. 1101989"
                                        onChange={(event) => {
                                          const next = event.target.value
                                          setSofascoreInputs((prev) => ({ ...prev, [rowKey]: next }))
                                        }}
                                        className="w-36"
                                      />
                                    </td>
                                    <td className="py-2 pr-4 align-top">
                                      <div className="flex flex-wrap gap-2">
                                        <Button
                                          size="sm"
                                          disabled={sofascoreUpdatingKey === rowKey || !(value && value.trim())}
                                          onClick={() => handleSofascoreAssign(player, (value || '').trim())}
                                        >
                                          {sofascoreUpdatingKey === rowKey ? 'Saving…' : 'Save'}
                                        </Button>
                                        <Button
                                          size="sm"
                                          variant="outline"
                                          disabled={sofascoreUpdatingKey === rowKey}
                                          onClick={() => handleSofascoreAssign(player, '')}
                                        >
                                          Clear
                                        </Button>
                                        {isSupplemental && (
                                          <Button
                                            size="sm"
                                            variant="destructive"
                                            disabled={sofascoreUpdatingKey === rowKey}
                                            onClick={() => handleSupplementalDelete(player)}
                                          >
                                            Delete
                                          </Button>
                                        )}
                                      </div>
                                    </td>
                                  </tr>
                                )
                              })}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  )}
                </>
              )}
            </div>
          )
        })}
      </div>
    </div>
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
      { path: '/teams', label: 'Teams', icon: Users },
      { path: '/dream-team', label: 'Dream XI', icon: Trophy },
      { path: '/newsletters', label: 'Newsletters', icon: FileText },
      { path: '/journalists', label: 'Journalists', icon: UserPlus },
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
  { key: 'Premier League', label: 'Premier League', color: LEAGUE_COLORS['Premier League'] },
  { key: 'La Liga', label: 'La Liga', color: LEAGUE_COLORS['La Liga'] },
  { key: 'Serie A', label: 'Serie A', color: LEAGUE_COLORS['Serie A'] },
  { key: 'Bundesliga', label: 'Bundesliga', color: LEAGUE_COLORS['Bundesliga'] },
  { key: 'Ligue 1', label: 'Ligue 1', color: LEAGUE_COLORS['Ligue 1'] },
  { key: 'champions-league', label: 'Champions League', color: LEAGUE_COLORS['Champions League'] },
]

const CL_CURRENT_SEASON = new Date().getFullYear() - (new Date().getMonth() < 7 ? 1 : 0)
const CL_SEASONS = Array.from({ length: 4 }, (_, i) => CL_CURRENT_SEASON - i)
const formatClSeason = (s) => `${s}/${(s + 1).toString().slice(-2)}`

function TeamsPage() {
  const [teams, setTeams] = useState([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('all')
  const [message, setMessage] = useState(null)
  const [teamSearch, setTeamSearch] = useState('')
  const [activeTab, setActiveTab] = useState('all')

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

  // For domestic tabs, filter base set by active tab
  const domesticBaseTeams = useMemo(() => {
    if (isCL) return []
    if (activeTab === 'all') return teams
    return teams.filter(t => t.league_name === activeTab)
  }, [teams, activeTab, isCL])

  const filteredTeams = useMemo(() => {
    const source = isCL ? clTeams : domesticBaseTeams
    if (!searchQuery) return null
    return source
      .filter(team => team.name.toLowerCase().includes(searchQuery))
      .sort((a, b) => {
        const aStarts = a.name.toLowerCase().startsWith(searchQuery) ? 0 : 1
        const bStarts = b.name.toLowerCase().startsWith(searchQuery) ? 0 : 1
        return aStarts - bStarts || a.name.localeCompare(b.name)
      })
  }, [domesticBaseTeams, clTeams, isCL, searchQuery])

  const isSearching = searchQuery.length > 0

  // Group teams by league (used when not searching, domestic tabs only)
  const teamsByLeague = useMemo(() => domesticBaseTeams.reduce((acc, team) => {
    const league = team.league_name || 'Other'
    if (!acc[league]) acc[league] = []
    acc[league].push(team)
    return acc
  }, {}), [domesticBaseTeams])

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
              <h1 className="text-2xl font-semibold text-foreground">European Teams</h1>
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

          {(isCL ? clLoading : loading) ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground/70" />
            </div>
          ) : isSearching ? (
            <div className="space-y-3">
              <div className="flex items-center justify-between px-1">
                <p className="text-sm text-muted-foreground">
                  {filteredTeams.length === 0
                    ? 'No teams found'
                    : `${filteredTeams.length} team${filteredTeams.length !== 1 ? 's' : ''} found`
                  }
                </p>
                <Button variant="ghost" size="sm" className="text-xs" onClick={() => setTeamSearch('')}>
                  Clear
                </Button>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
                {filteredTeams.map((team) => isCL ? renderClTeamCard(team) : renderTeamCard(team))}
              </div>
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
            <div className="space-y-8">
              {Object.entries(teamsByLeague).map(([league, leagueTeams]) => (
                <div key={league}>
                  <div className="flex items-center gap-3 mb-3 pl-1">
                    <div className="w-1 h-5 rounded-full" style={{ backgroundColor: LEAGUE_COLORS[league] || '#9ca3af' }} />
                    <h2 className="text-sm font-semibold text-foreground">{league}</h2>
                    <span className="text-xs text-muted-foreground/70">{leagueTeams.length}</span>
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
                    {leagueTeams.map((team) => renderTeamCard(team))}
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
    <div className="max-w-[1400px] mx-auto py-6 px-4 sm:px-6 lg:px-8">
      <div className="flex flex-col lg:flex-row gap-6">
        {/* Main Content */}
        <div className="flex-1 min-w-0 max-w-4xl py-6 sm:px-0 overflow-hidden">
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

        {/* Sponsor Sidebar - visible on larger screens */}
        <SponsorSidebar className="hidden lg:block" />
      </div>

      {/* Mobile Sponsor Strip - visible on smaller screens */}
      <div className="lg:hidden pb-6">
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
      <Route path="/academy" element={<CohortBrowser />} />
      <Route path="/academy/cohorts/:cohortId" element={<CohortDetail />} />
      <Route path="/academy/analytics" element={<CohortAnalytics />} />
      <Route path="/admin" element={<AdminLayout />}>
        <Route index element={<Navigate to="/admin/dashboard" replace />} />
        <Route path="dashboard" element={<AdminDashboard />} />
        <Route path="newsletters" element={<AdminNewsletters />} />
        <Route path="users" element={<AdminUsers />} />
        <Route path="players" element={<AdminPlayers />} />
        <Route path="teams" element={<AdminTeams />} />
        <Route path="teams/:teamId/formation" element={<AdminFormation />} />
        <Route path="sponsors" element={<AdminSponsors />} />
        <Route path="curation" element={<AdminCuration />} />
        <Route path="flags" element={<AdminFlags />} />
        <Route path="academy" element={<AdminAcademy />} />
        <Route path="cohorts" element={<AdminCohorts />} />
        <Route path="settings" element={<AdminSettings />} />
        <Route path="tools" element={<AdminTools />} />
        <Route path="sandbox" element={<AdminSandbox />} />
      </Route>
      <Route
        path="/admin/old"
        element={(
          <RequireAdmin>
            <AdminPage includeSandbox />
          </RequireAdmin>
        )}
      />
      <Route
        path="/admin/newsletters/:newsletterId"
        element={(
          <RequireAdmin>
            <AdminNewsletterDetailPage />
          </RequireAdmin>
        )}
      />
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
