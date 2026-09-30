import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowRight, MapPin, ShieldAlert, UserPlus } from 'lucide-react'
import { APIService } from '@/lib/api'
import { ContentReportDialog } from '@/components/ContentReportDialog'
import { PlayerReachControls } from '@/components/PlayerReachControls'
import { ShowcaseSection } from '@/components/ShowcaseSection'
import { ProvenanceChip } from '@/components/SelfReportedBadge'
import { useAuth } from '@/context/AuthContext'
import { Button } from '@/components/ui/button'
import { SectionHeading, StatFigure } from '@/components/public/Floodlight'
import { Skeleton } from '@/components/ui/skeleton'
import { formatSeasonLabel } from '@/lib/seasons'
import { track } from '@/lib/track'

function initialsOf(name) {
  return String(name || '').trim().split(/\s+/).slice(0, 2).map((part) => part[0] || '').join('').toUpperCase() || '·'
}

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

function LocalSeasonStats({ stats, position }) {
  if (!stats) return null
  const goalkeeper = /(^|[^a-z])(g|gk|goalkeeper|keeper)(?=$|[^a-z])/.test(
    String(position || '').trim().toLowerCase(),
  )
  const hasTotals = [
    stats.appearances,
    stats.minutes,
    stats.goals,
    stats.assists,
    stats.saves,
    stats.goals_conceded,
  ].some((value) => Number(value || 0) > 0)
  if (!hasTotals && !stats.provenance) return null

  const totals = goalkeeper
    ? [
        ['Appearances', stats.appearances ?? 0],
        ['Minutes', stats.minutes ?? 0],
        ['Saves', stats.saves ?? 0],
        ['Conceded', stats.goals_conceded ?? 0],
      ]
    : [
        ['Appearances', stats.appearances ?? 0],
        ['Minutes', stats.minutes ?? 0],
        ['Goals', stats.goals ?? 0],
        ['Assists', stats.assists ?? 0],
      ]

  return (
    <section aria-labelledby="local-player-season-totals">
      <SectionHeading
        id="local-player-season-totals"
        title={`${formatSeasonLabel(stats.season)} Totals`}
      >
        <ProvenanceChip provenance={stats.provenance} />
      </SectionHeading>
      <div className="grid grid-cols-2 sm:grid-cols-4">
        {totals.map(([label, value]) => (
          <StatFigure key={label} label={label}>
            {label === 'Minutes' ? Number(value).toLocaleString() : value}
          </StatFigure>
        ))}
      </div>
    </section>
  )
}

function LocalPlayerProfile({ numericPlayerId, onPublicConfirmed, onRetry }) {
  const [player, setPlayer] = useState(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)
  const [error, setError] = useState(null)
  const [seasonStats, setSeasonStats] = useState(null)
  const signedPlayerApiId = `-${String(numericPlayerId)}`
  const canonicalPlayerApiId = player?.api_player_id == null
    ? null
    : String(player.api_player_id)
  const matchPlayerApiId = canonicalPlayerApiId ?? signedPlayerApiId

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

  useEffect(() => {
    if (!player) return undefined
    let cancelled = false
    APIService.getPublicPlayerSeasonStats(matchPlayerApiId)
      .then((response) => {
        if (!cancelled) setSeasonStats(response || null)
      })
      .catch(() => {
        if (!cancelled) setSeasonStats(null)
    })
    return () => { cancelled = true }
  }, [matchPlayerApiId, player])

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
    : null
  const details = [
    player.birth_year != null ? `Born ${player.birth_year}` : null,
    player.position || null,
    player.club_name ? `Club: ${player.club_name}` : null,
    !player.city ? player.country || null : null,
  ].filter(Boolean)

  return (
    <div className="min-h-screen bg-chalk">
      <header className="dark bg-night text-chalk">
        <div className="floodlight-container flex flex-col gap-8 py-12 sm:py-16 md:flex-row md:items-center md:gap-14">
          <div className="relative flex h-32 w-32 shrink-0 items-center justify-center sm:h-44 sm:w-44" aria-hidden="true">
            <span className="absolute inset-0 rounded-full border border-dashed border-gold/60" />
            <span className="display flex h-[86%] w-[86%] items-center justify-center rounded-full bg-club text-[52px] text-gold sm:text-[72px]">
              {initialsOf(player.display_name)}
            </span>
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="eyebrow flex flex-wrap items-center gap-x-5 gap-y-1">
                <span className="text-gold">Community player</span>
                {player.status === 'pending' ? (
                  <span className="text-warn">Pending review</span>
                ) : null}
              </div>
              {/* Web-only local:<canonical id> subject_id; backend accepts free text (≤200 chars), disambiguating the two ID spaces. */}
              <ContentReportDialog subjectId={`local:${player.id}`} />
            </div>
            <h1 className="display mt-3 break-words text-[48px] leading-[.92] [overflow-wrap:anywhere] sm:text-[80px] lg:text-[104px]">
              {player.display_name}
            </h1>
            {details.length > 0 || location ? (
              <div className="mt-4 flex flex-wrap items-center gap-x-2 gap-y-1 text-base text-chalk/80 sm:text-[17px]">
                {[...details, location].filter(Boolean).map((detail, index) => (
                  <span key={detail} className="inline-flex items-center gap-2">
                    {index > 0 ? <span aria-hidden="true" className="text-muted-dark">·</span> : null}
                    {detail === location ? <MapPin className="h-4 w-4 text-muted-dark" /> : null}
                    {detail}
                  </span>
                ))}
              </div>
            ) : null}
            {canonicalPlayerApiId != null ? (
              <PlayerReachControls
                key={canonicalPlayerApiId}
                signedId={canonicalPlayerApiId}
                onPublicConfirmed={onPublicConfirmed}
              />
            ) : null}
          </div>
        </div>
      </header>

      <div className="floodlight-container space-y-14 py-12 sm:py-16">
        <p className="flex items-start gap-3 border-y border-border py-4 text-[15px] leading-relaxed text-ink">
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-gold-text" aria-hidden="true" />
          <span>Community profile — self-reported. Not an official Academy Watch tracked player.</span>
        </p>

        <ShowcaseSection
          local
          playerApiId={String(numericPlayerId)}
          canonicalPlayerApiId={canonicalPlayerApiId}
          playerName={player.display_name}
          playerPosition={player.position}
          onSeasonStatsChange={setSeasonStats}
        />

        <LocalSeasonStats stats={seasonStats} position={player.position} />
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
