import '@/styles/floodlight-player.css'
// --- p2-b2 begin ---
import { PlayerApplications } from '@/components/applications/PlayerApplications'
// --- p2-b2 end ---
import { useApprovedPlayerState } from '@/hooks/useApprovedPlayer'
import { useOpportunities } from '@/pages/opportunities/useOpportunities'
import { useDataMode } from '@/hooks/useDataMode'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, Globe2, Loader2, Search, ShieldCheck, UserPlus } from 'lucide-react'
import { APIService } from '@/lib/api'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

const SEARCH_DEBOUNCE_MS = 300

function getPlayerApiId(player) {
  return player?.player_api_id ?? player?.player_id
}

function getPlayerName(player) {
  return player?.player_name || player?.name || 'Player profile'
}

function PlayerSearchResult({ player }) {
  const playerApiId = getPlayerApiId(player)
  const playerName = getPlayerName(player)
  const clubName = player.loan_team_name || player.primary_team_name || player.owner_team_name
  const details = [player.position, clubName, player.nationality].filter(Boolean)

  if (!playerApiId) return null

  return (
    <li>
      <Link
        to={`/players/${playerApiId}`}
        className="group rule-row flex items-center gap-3 no-underline hover:bg-chalk-2 hover:no-underline"
      >
        <Avatar className="h-11 w-11 shrink-0 border border-border/70 bg-secondary">
          <AvatarImage src={player.player_photo || player.photo} alt="" />
          <AvatarFallback className="text-xs font-semibold text-muted-foreground">
            {playerName.slice(0, 2).toUpperCase()}
          </AvatarFallback>
        </Avatar>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-semibold text-foreground transition-colors group-hover:text-primary sm:text-base">
            {playerName}
          </span>
          <span className="mt-0.5 block truncate text-xs text-muted-foreground sm:text-sm">
            {details.length > 0 ? details.join(' · ') : 'Tracked player profile'}
          </span>
        </span>
        <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary" />
      </Link>
    </li>
  )
}

export function PlayerOnboarding() {
  const flags = useOpportunities()
  const { claims: profiles, loading: profilesLoading, error: profilesError, retry: retryProfiles } = useApprovedPlayerState(flags)
  const applicationsError = flags.error || profilesError
  const checkingProfiles = profilesLoading && !applicationsError
  const { api_football_frozen: frozen } = useDataMode()
  const [query, setQuery] = useState('')
  const [searchState, setSearchState] = useState({
    query: '',
    status: 'idle',
    results: [],
    error: null,
  })

  useEffect(() => {
    const trimmedQuery = query.trim()
    if (trimmedQuery.length < 2) return undefined

    const timer = window.setTimeout(() => {
      setSearchState({ query: trimmedQuery, status: 'loading', results: [], error: null })
    }, SEARCH_DEBOUNCE_MS)
    return () => window.clearTimeout(timer)
  }, [query])

  useEffect(() => {
    if (searchState.status !== 'loading' || searchState.query.length < 2) return undefined

    let cancelled = false
    const requestedQuery = searchState.query

    APIService.getScoutPlayers({ search: requestedQuery, per_page: 20, sort: 'name' })
      .then((data) => {
        if (cancelled) return
        setSearchState((current) => current.query === requestedQuery
          ? { query: requestedQuery, status: 'success', results: Array.isArray(data?.players) ? data.players : [], error: null }
          : current)
      })
      .catch(() => {
        if (cancelled) return
        setSearchState((current) => current.query === requestedQuery
          ? { query: requestedQuery, status: 'error', results: [], error: 'We could not search player profiles. Please try again.' }
          : current)
      })

    return () => { cancelled = true }
  }, [searchState.query, searchState.status])

  const trimmedQuery = query.trim()
  const activeSearch = trimmedQuery.length >= 2 && searchState.query === trimmedQuery
  const results = activeSearch ? searchState.results : []
  const loading = activeSearch && searchState.status === 'loading'
  const error = activeSearch ? searchState.error : null
  const showHint = trimmedQuery.length > 0 && trimmedQuery.length < 2
  const showNoResults = activeSearch && searchState.status === 'success' && results.length === 0

  const discovery = <>
    <Card className="mt-12 max-w-3xl overflow-hidden border-0 border-t border-hairline shadow-none sm:mt-14">
      <CardHeader className="border-b border-border/60 bg-card">
        <CardTitle>Find your profile</CardTitle>
        <CardDescription>Search by your name. Enter at least two characters.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 bg-secondary/25 py-5 sm:py-6">
        <div className="space-y-2">
          <Label htmlFor="player-onboarding-search">Player name</Label>
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              id="player-onboarding-search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search tracked players"
              className="h-11 bg-background pl-9 pr-10"
              autoComplete="off"
              aria-describedby={showHint ? 'player-search-hint' : undefined}
            />
            {loading ? (
              <Loader2 className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-primary" aria-hidden="true" />
            ) : null}
          </div>
          {showHint ? (
            <p id="player-search-hint" className="text-xs text-muted-foreground">Type one more character to search.</p>
          ) : null}
        </div>

        <div aria-live="polite" aria-busy={loading}>
          {error ? <p className="rounded-lg border border-danger/30 p-3 text-sm text-danger" role="alert">{error}</p> : null}
          {showNoResults ? (
            <p className="rounded-lg border border-dashed border-border bg-background/70 px-4 py-7 text-center text-sm text-muted-foreground">
              No tracked player matches “{searchState.query}”. Try a shorter name or use one of the options below.
            </p>
          ) : null}
          {results.length > 0 ? (
            <ul className="space-y-2">
              {results.map((player) => (
                <PlayerSearchResult key={getPlayerApiId(player)} player={player} />
              ))}
            </ul>
          ) : null}
        </div>
      </CardContent>
    </Card>

    <section className="mt-14 max-w-3xl" aria-labelledby="player-next-steps">
      <div className="mb-4">
        <p className="eyebrow">Next steps</p>
        <h2 id="player-next-steps" className="display mt-3 text-4xl">Can&apos;t find yourself?</h2>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        {!frozen && (<Card className="border-0 border-t border-hairline shadow-none">
          <CardHeader>
            <span className="mb-1 inline-flex h-10 w-10 items-center justify-center rounded-full bg-chalk-2 text-muted-foreground">
              <Globe2 className="h-5 w-5" />
            </span>
            <CardTitle className="text-lg">Search worldwide</CardTitle>
            <CardDescription>Look beyond the currently tracked Academy Watch profiles.</CardDescription>
          </CardHeader>
          <CardContent>
            <Button variant="outline" asChild className="w-full justify-between bg-background">
              <Link to="/scout/lists">
                Search worldwide
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
          </CardContent>
        </Card>)}
        <Card className="border-0 border-t border-hairline shadow-none">
          <CardHeader>
            <span className="mb-1 inline-flex h-10 w-10 items-center justify-center rounded-full bg-chalk-2 text-muted-foreground">
              <UserPlus className="h-5 w-5" />
            </span>
            <CardTitle className="text-lg">Create your profile</CardTitle>
            <CardDescription>Add a self-reported profile when official coverage does not include you.</CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild className="w-full justify-between">
              <Link to="/local-players/new">
                Create your profile
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    </section>
  </>

  return (
    <div className="fl-player-onboarding min-h-screen bg-chalk">
      <div className="floodlight-container py-12 sm:py-20">
        {checkingProfiles ? <p role="status">Checking your profiles…</p> : !applicationsError && profiles.length > 0 ? <header className="max-w-3xl">
          <p className="eyebrow">Player home</p><h1 className="display mt-4 text-[56px] sm:text-[80px]">Your next step.</h1>
          <p className="mt-6 text-muted">Your profile, applications and replies, together.</p>
          <div className="mt-8 flex flex-wrap gap-3">{profiles.map(profile => <Link key={profile.claim_id} className="inline-flex min-w-0 max-w-full rounded-xl bg-ink px-6 py-3 text-chalk" to={profile.profile_path || `/players/${profile.signed_player_id}`}><span className="min-w-0 [overflow-wrap:anywhere]">{profile.name} · My profile →</span></Link>)}<a className="inline-flex rounded-full border border-ink px-6 py-3" href="#my-applications">My applications ↓</a></div>
        </header> : <header className="max-w-3xl">
          <span className="inline-flex h-12 w-12 items-center justify-center rounded-full border border-hairline text-muted-foreground">
            <ShieldCheck className="h-6 w-6" />
          </span>
          <p className="eyebrow mt-6">Player identity</p>
          <h1 className="display mt-4 text-[56px] sm:text-[80px]">Are you a player?</h1>
          <p className="mt-6 max-w-2xl text-sm leading-relaxed text-muted-foreground sm:text-base">
            Find your tracked profile, then open it and choose “This is me” to start your claim. Direct player claims are for adults aged 18 or older.
          </p>
        </header>}
        {!checkingProfiles && !applicationsError && profiles.length === 0 && discovery}
      </div>
      {/* --- p2-b2 begin --- */}
      {applicationsError ? <section className="floodlight-container pb-8" aria-label="Applications unavailable">
        <p role="alert">{applicationsError}</p>
        <Button className="mt-4" disabled={flags.retrying || profilesLoading} onClick={flags.error ? flags.retry : retryProfiles}>Retry applications</Button>
      </section> : !checkingProfiles && <PlayerApplications />}
      {!checkingProfiles && (applicationsError || profiles.length > 0) && <div className="floodlight-container pb-16">{discovery}</div>}
      {/* --- p2-b2 end --- */}
    </div>
  )
}

export default PlayerOnboarding
