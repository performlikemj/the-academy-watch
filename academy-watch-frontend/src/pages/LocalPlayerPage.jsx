import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { ArrowRight, ShieldAlert, UserPlus } from 'lucide-react'
import { APIService } from '@/lib/api'
import { ContentReportDialog } from '@/components/ContentReportDialog'
import { PlayerReachControls } from '@/components/PlayerReachControls'
import { ShowcaseSection } from '@/components/ShowcaseSection'
import { PlayerHero } from '@/components/player-card/PlayerHero'
import { MatchLines, PlayerFacts, PlayerSeason } from '@/components/player-card/PlayerSeason'
import { usePlayerReadView, useScopedShowcase, useSeasonTotalsRead } from '@/components/player-card/usePlayerReadView'
import { useAuth } from '@/context/AuthContext'
import { useDataMode } from '@/hooks/useDataMode'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { calendarSeason, isGoalkeeperPosition, readProblem, roleLabel, seasonKicker, seasonView } from '@/lib/player-card'
import { formatSeasonLabel } from '@/lib/seasons'
import { track } from '@/lib/track'

function LoadingState() {
  return (
    <div aria-busy="true">
      <p className="sr-only" role="status" aria-live="polite">Loading player profile…</p>
      <div className="dark bg-night">
        <div className="floodlight-container space-y-4 py-16">
          <Skeleton className="h-4 w-36" />
          <Skeleton className="h-14 w-96 max-w-full" />
          <Skeleton className="h-5 w-72 max-w-full" />
        </div>
      </div>
      <div className="floodlight-container space-y-5 py-12">
        <Skeleton className="h-20 w-full rounded-[10px]" />
        <Skeleton className="h-80 w-full rounded-[10px]" />
      </div>
    </div>
  )
}

function MissingState() {
  return (
    <div className="floodlight-container flex min-h-[65vh] flex-col items-start justify-center py-20">
      <p className="eyebrow">Player profile</p>
      <h1 className="display mt-4 max-w-3xl text-[40px] sm:text-[60px]">
        This profile doesn&apos;t exist or isn&apos;t public yet
      </h1>
      <p className="mt-4 max-w-lg leading-relaxed text-muted-foreground">
        It may still be waiting for review, or the profile link may be incorrect.
      </p>
      <Link
        to="/local-players/new"
        className="mt-8 inline-flex h-11 items-center gap-2 rounded-full border border-ink px-5 text-sm font-medium transition-colors hover:bg-chalk-2"
      >
        <UserPlus className="h-4 w-4" />
        Create a player profile
        <ArrowRight className="h-3.5 w-3.5" />
      </Link>
    </div>
  )
}

function LocalPlayerProfile({ numericPlayerId, onPublicConfirmed, onRetry }) {
  const [searchParams, setSearchParams] = useSearchParams()
  const seasonParam = searchParams.get('season')
  // The URL holds the ONE picked season: it drives the totals request, the
  // heading, the lines and the picker. No pick = the server's default season.
  const season = /^\d{4}$/.test(seasonParam || '') ? Number(seasonParam) : undefined
  const [player, setPlayer] = useState(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)
  const [error, setError] = useState(null)
  const [seasonStatsRevision, setSeasonStatsRevision] = useState(0)
  // Held per player AND viewer (this component is also re-keyed on the token,
  // so nothing of a previous viewer survives a logout or account switch).
  const [showcase, setShowcase] = useScopedShowcase({ playerApiId: String(numericPlayerId), local: true })
  const { api_football_frozen: frozen } = useDataMode()
  const signedPlayerApiId = `-${String(numericPlayerId)}`
  const canonicalPlayerApiId = player?.api_player_id == null
    ? null
    : String(player.api_player_id)
  const matchPlayerApiId = canonicalPlayerApiId ?? signedPlayerApiId
  const read = usePlayerReadView({
    // Nothing is requested until the profile itself has loaded as visible
    // (the canonical id is only known then). The showcase comes from
    // ShowcaseSection, which loads it once for the page.
    matchPlayerApiId: player ? matchPlayerApiId : null,
    showcase,
    revision: seasonStatsRevision,
  })
  // Season totals are their own read: loading, failure (with retry) and the
  // last good answer are tracked per player + viewer + season.
  const seasonRead = useSeasonTotalsRead({
    playerApiId: matchPlayerApiId,
    season,
    revision: seasonStatsRevision,
    enabled: Boolean(player),
  })
  const seasonStats = seasonRead.stats

  useEffect(() => {
    let cancelled = false
    APIService.getLocalPlayer(numericPlayerId)
      .then((response) => {
        if (cancelled) return
        if (!response?.player) {
          setNotFound(true)
          return
        }
        setPlayer(response.player)
      })
      .catch((requestError) => {
        if (cancelled) return
        if (requestError.status === 404) {
          setNotFound(true)
        } else {
          setError(requestError.body?.error || requestError.message || 'Failed to load this profile')
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => { cancelled = true }
  }, [numericPlayerId])

  if (loading) return <LoadingState />
  if (notFound) return <MissingState />

  if (error || !player) {
    return (
      <div className="floodlight-container flex min-h-[65vh] flex-col items-start justify-center py-20">
        <p className="eyebrow text-danger">Something went wrong</p>
        <h1 className="display mt-4 text-[40px] sm:text-[56px]">We couldn&apos;t load this profile</h1>
        <p className="mt-3 text-muted-foreground">{error || 'Try again in a moment.'}</p>
        <Button variant="outline" className="mt-8" onClick={onRetry}>
          Try again
        </Button>
      </div>
    )
  }

  const location = player.city
    ? [player.city, player.country].filter(Boolean).join(', ')
    : !player.city ? player.country || null : null
  const clubName = read.confirmedBy || player.club_name || null
  const line = [
    player.position || null,
    clubName,
    player.birth_year != null ? `Born ${player.birth_year}` : null,
    location,
  ].filter(Boolean).join(' · ') || null

  // Totals are the provider's when it really has them, otherwise exactly the
  // merged match lines for the season shown. The two are never added together.
  const view = seasonView({ picked: season, stats: seasonStats, seasons: read.seasons })
  const { season: viewSeason, provider, lines: seasonLines, totals: seasonLineTotals } = view
  const seasonProblem = readProblem({
    linesError: read.linesError,
    linesStale: read.hasLines,
    totalsError: seasonRead.totalsError,
    totalsStale: seasonRead.hasTotals,
    showing: Boolean(provider) || seasonLines.length > 0,
  })
  const retrySeason = () => {
    if (read.linesError) read.retry()
    if (seasonRead.totalsError) seasonRead.retry()
  }
  const pickSeason = (next) => {
    setSearchParams((previous) => {
      const params = new URLSearchParams(previous)
      params.set('season', String(next))
      return params
    }, { replace: true })
  }
  const goalkeeper = isGoalkeeperPosition(player.position)
  const seasonChoices = [...new Set([...read.seasons.map((entry) => entry.season), viewSeason])]
    .filter((value) => Number.isInteger(value))
    .sort((a, b) => b - a)

  return (
    <div className="min-h-screen bg-chalk">
      <div className="floodlight-container max-w-[1232px] space-y-12 pb-24 pt-5">
        <PlayerHero
          name={player.display_name}
          photos={read.photos}
          clubName={clubName}
          role={roleLabel(read.profile?.positions, player.position)}
          confirmedBy={read.confirmedBy}
          quote={read.bio}
          line={line}
          eyebrow={(
            <>
              <span>Community player</span>
              {player.status === 'pending' ? <span className="text-warn">Pending review</span> : null}
            </>
          )}
          bar={(
            <div className="ml-auto">
              {/* Web-only local:<canonical id> subject_id; backend accepts free text (≤200 chars), disambiguating the two ID spaces. */}
              <ContentReportDialog subjectId={`local:${player.id}`} className="min-h-11 min-w-11" />
            </div>
          )}
        >
          {canonicalPlayerApiId != null ? (
            <PlayerReachControls
              key={canonicalPlayerApiId}
              signedId={canonicalPlayerApiId}
              onPublicConfirmed={onPublicConfirmed}
            />
          ) : null}
        </PlayerHero>

        <PlayerFacts facts={read.facts} />

        <p className="flex items-start gap-3 border-y border-border py-4 text-[15px] leading-relaxed text-ink">
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-gold-text" aria-hidden="true" />
          <span>Community profile — self-reported. Not an official Academy Watch tracked player.</span>
        </p>

        <PlayerSeason
          season={viewSeason}
          lines={seasonLines}
          totals={seasonLineTotals}
          provider={provider}
          minutesKnown={seasonStats?.stats_coverage !== 'limited'}
          goalkeeper={goalkeeper}
          frozen={frozen}
          playerName={player.display_name}
          loading={read.linesLoading || seasonRead.totalsLoading}
          problem={seasonProblem}
          onRetry={retrySeason}
          truncated={read.truncated}
          kicker={seasonKicker(viewSeason, calendarSeason())}
          control={seasonChoices.length > 1 ? (
            <label className="pc-season-pick">
              Season
              <select value={viewSeason ?? ''} onChange={(event) => pickSeason(Number(event.target.value))}>
                {seasonChoices.map((value) => <option key={value} value={value}>{formatSeasonLabel(value)}</option>)}
              </select>
            </label>
          ) : null}
        />
        <MatchLines lines={seasonLines} goalkeeper={goalkeeper} />

        <ShowcaseSection
          local
          readSectionsElsewhere
          onShowcaseChange={setShowcase}
          playerApiId={String(numericPlayerId)}
          canonicalPlayerApiId={canonicalPlayerApiId}
          playerName={player.display_name}
          playerPosition={player.position}
          onSeasonStatsChange={() => {
            // A game from another year can change this season's totals too when moved.
            // Reload the displayed totals rather than adopting the edited game's season.
            setSeasonStatsRevision((revision) => revision + 1)
          }}
        />
      </div>
    </div>
  )
}

export function LocalPlayerPage() {
  const { localPlayerId } = useParams()
  const { token } = useAuth()
  const [attempt, setAttempt] = useState(0)
  const emittedProfileViewIdsRef = useRef(new Set())
  const numericPlayerId = Number(localPlayerId)
  const validPlayerId = Number.isInteger(numericPlayerId) && numericPlayerId > 0

  const handlePublicConfirmed = useCallback((signedId) => {
    const numericId = Number(signedId)
    if (!Number.isInteger(numericId) || numericId === 0 || emittedProfileViewIdsRef.current.has(numericId)) return
    emittedProfileViewIdsRef.current.add(numericId)
    track('profile_view', { player_api_id: numericId })
  }, [])

  if (!validPlayerId) return <MissingState />

  return (
    <LocalPlayerProfile
      key={`${numericPlayerId}-${attempt}-${token || 'public'}`}
      numericPlayerId={numericPlayerId}
      onPublicConfirmed={handlePublicConfirmed}
      onRetry={() => setAttempt((value) => value + 1)}
    />
  )
}

export default LocalPlayerPage
