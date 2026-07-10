import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { MiniProgressBar } from '@/components/MiniProgressBar'
import { STATUS_BADGE_CLASSES } from '@/lib/theme-constants'
import { ShareMenu } from '@/components/share/ShareMenu'
import {
  ArrowLeft,
  ArrowRight,
  User,
  Users,
  Flag,
  Star,
  BadgeCheck,
  Clock,
  ShieldCheck,
} from 'lucide-react'

// Translucent chip that reads on the claret hero (light) and on the
// claret-tinted dark surface (dark) alike.
const HERO_CHIP =
  'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ' +
  'border-primary-foreground/25 bg-primary-foreground/15 text-primary-foreground ' +
  'dark:border-primary/30 dark:bg-primary/15 dark:text-foreground'

// Icon action button styled for the hero band.
// 44px — Apple HIG minimum touch target, ready for the native iOS wrapper.
const HERO_ICON_BTN =
  'inline-flex h-11 w-11 items-center justify-center rounded-full border transition-colors ' +
  'border-primary-foreground/25 bg-primary-foreground/10 text-primary-foreground ' +
  'hover:bg-primary-foreground/20 focus-visible:outline-none focus-visible:ring-2 ' +
  'focus-visible:ring-primary-foreground/60 focus-visible:ring-offset-2 focus-visible:ring-offset-transparent ' +
  'dark:border-primary/30 dark:bg-primary/10 dark:text-foreground dark:hover:bg-primary/20 dark:focus-visible:ring-primary/60'

/** Build the hero key-stat strip, rendering only stats that actually exist. */
function buildHeroStats({ position, seasonTotals, academyStats }) {
  const gk = position === 'Goalkeeper'
  let apps, minutes, goals, assists, saves, conceded, rating

  if (seasonTotals?.appearances > 0) {
    apps = seasonTotals.appearances
    minutes = seasonTotals.minutes
    goals = seasonTotals.goals
    assists = seasonTotals.assists
    saves = seasonTotals.saves
    conceded = seasonTotals.goalsConceded
    rating = seasonTotals.avgRating
  } else if (academyStats?.appearances > 0) {
    apps = academyStats.appearances
    minutes = academyStats.minutes
    goals = academyStats.goals
    assists = academyStats.assists
    rating = academyStats.rating
  } else {
    return []
  }

  const out = [{ label: 'Apps', value: apps }]
  if (minutes > 0) {
    out.push({ label: 'Minutes', value: minutes.toLocaleString() })
  }
  if (gk && saves != null) {
    out.push({ label: 'Saves', value: saves })
    out.push({ label: 'Conceded', value: conceded ?? 0 })
  } else {
    out.push({ label: 'Goals', value: goals ?? 0 })
    out.push({ label: 'Assists', value: assists ?? 0 })
  }
  if (rating != null && rating !== '-') {
    // Marked wide so an odd tile count still lands balanced on the 2-col mobile grid.
    out.push({ label: 'Avg Rating', value: rating, wide: true })
  }
  return out
}

/** The claim CTA, one of four viewer-relative states. */
function ClaimAffordance({ claimState, onClaim }) {
  if (!claimState) return null
  const { isOwner, isPending, canClaim, claimedByOther } = claimState

  if (isOwner) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-300/60 bg-emerald-50 px-3 py-1.5 text-sm font-medium text-emerald-800">
        <BadgeCheck className="h-4 w-4" />
        Your profile
      </span>
    )
  }
  if (isPending) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-300/60 bg-amber-50 px-3 py-1.5 text-sm font-medium text-amber-800">
        <Clock className="h-4 w-4" />
        Claim pending review
      </span>
    )
  }
  if (canClaim) {
    return (
      <Button
        onClick={onClaim}
        className="h-11 gap-1.5 bg-primary-foreground px-5 text-primary shadow-sm hover:bg-primary-foreground/90 dark:bg-primary dark:text-primary-foreground dark:hover:bg-primary/90"
      >
        <BadgeCheck className="h-4 w-4" />
        Is this you? Claim your profile
      </Button>
    )
  }
  if (claimedByOther) {
    return (
      <span
        className={HERO_CHIP}
        title="This profile has been claimed"
      >
        <ShieldCheck className="h-3.5 w-3.5" />
        Claimed profile
      </span>
    )
  }
  return null
}

/**
 * Identity-first hero band for a player profile. Full-width claret gradient
 * (theme tokens, intentional in light and dark). Owns no data fetching —
 * everything arrives via props from PlayerPage so there is a single source
 * of truth for stats, watchlist and claim state.
 */
export function ProfileHero({
  playerApiId,
  playerName,
  profile,
  position,
  seasonTotals,
  academyStats,
  currentClub,
  isWatched,
  onToggleWatch,
  onFlag,
  onBack,
  onParentClubClick,
  claimState,
  onClaim,
}) {
  const heroStats = buildHeroStats({ position, seasonTotals, academyStats })
  const academyApps =
    academyStats?.appearances > 0 && seasonTotals?.appearances > 0
      ? academyStats.appearances
      : null

  // Slim sticky bar fades in once the hero is scrolled past.
  const [showBar, setShowBar] = useState(false)
  useEffect(() => {
    const onScroll = () => setShowBar(window.scrollY > 220)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <>
      {/* Slim sticky bar — keeps back / share / watch reachable after scroll.
          inert while hidden so its controls can't take keyboard focus. */}
      <div
        inert={!showBar}
        className={`fixed inset-x-0 top-0 z-30 border-b border-border bg-card/95 pt-[env(safe-area-inset-top)] backdrop-blur transition-all duration-200 ${
          showBar ? 'translate-y-0 opacity-100' : 'pointer-events-none -translate-y-full opacity-0'
        }`}
      >
        <div className="mx-auto flex max-w-5xl items-center gap-3 px-4 py-2 sm:px-6">
          <Button variant="ghost" size="sm" onClick={onBack} className="shrink-0">
            <ArrowLeft className="mr-1.5 h-4 w-4" />
            Back
          </Button>
          <span className="min-w-0 flex-1 truncate text-sm font-semibold text-foreground">
            {playerName}
          </span>
          <Button
            variant="ghost"
            size="icon"
            onClick={onToggleWatch}
            className={isWatched ? 'text-amber-500' : 'text-muted-foreground'}
            aria-label={isWatched ? 'Remove from watchlist' : 'Watch this player'}
          >
            <Star className={`h-4 w-4 ${isWatched ? 'fill-amber-400 text-amber-500' : ''}`} />
          </Button>
          <ShareMenu
            playerId={playerApiId}
            playerName={playerName}
            profile={profile}
            seasonTotals={seasonTotals}
            position={position}
            variant="ghost"
          />
        </div>
      </div>

      <header className="relative overflow-hidden bg-gradient-to-br from-primary via-primary to-primary/85 text-primary-foreground dark:from-primary/15 dark:via-primary/10 dark:to-background dark:text-foreground">
        {/* Soft decorative wash — token-based, no external assets */}
        <div
          aria-hidden
          className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-primary-foreground/10 blur-3xl dark:bg-primary/10"
        />
        <div className="relative mx-auto max-w-5xl px-4 pb-6 pt-4 sm:px-6 sm:pb-8">
          {/* Top row: back + quick actions */}
          <div className="mb-4 flex items-center justify-between">
            <button
              onClick={onBack}
              className="-ml-2 inline-flex min-h-11 items-center gap-1.5 rounded-md px-2 py-2 text-sm font-medium text-primary-foreground/90 transition-colors hover:text-primary-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-foreground/60 dark:text-foreground/80 dark:hover:text-foreground dark:focus-visible:ring-primary/60"
            >
              <ArrowLeft className="h-4 w-4" />
              Back
            </button>
            <div className="flex items-center gap-2">
              <button
                onClick={onToggleWatch}
                className={HERO_ICON_BTN}
                title={isWatched ? 'Remove from watchlist' : 'Watch this player'}
                aria-label={isWatched ? 'Remove from watchlist' : 'Watch this player'}
                aria-pressed={isWatched}
              >
                <Star className={`h-4 w-4 ${isWatched ? 'fill-amber-400 text-amber-400' : ''}`} />
              </button>
              <button
                onClick={onFlag}
                className={HERO_ICON_BTN}
                title="Report incorrect data"
                aria-label="Report incorrect data"
              >
                <Flag className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Identity block */}
          <div className="flex flex-col gap-5 sm:flex-row sm:items-start">
            {/* Photo */}
            <div className="shrink-0">
              {profile?.photo ? (
                <img
                  src={profile.photo}
                  alt={playerName}
                  width={128}
                  height={128}
                  className="h-24 w-24 rounded-2xl object-cover shadow-lg ring-4 ring-primary-foreground/30 sm:h-32 sm:w-32 dark:ring-primary/40"
                />
              ) : (
                <div className="flex h-24 w-24 items-center justify-center rounded-2xl bg-primary-foreground/15 shadow-lg ring-4 ring-primary-foreground/30 sm:h-32 sm:w-32 dark:bg-primary/15 dark:ring-primary/40">
                  <span className="text-3xl font-bold sm:text-4xl">
                    {playerName?.trim()?.charAt(0)?.toUpperCase() || <User className="h-10 w-10" />}
                  </span>
                </div>
              )}
            </div>

            {/* Name, badges, journey */}
            <div className="min-w-0 flex-1">
              <h1 className="text-3xl font-extrabold leading-tight tracking-tight text-balance sm:text-4xl">
                {playerName}
              </h1>

              <div className="mt-3 flex flex-wrap items-center gap-2">
                {position && <span className={HERO_CHIP}>{position}</span>}
                {profile?.age && <span className={HERO_CHIP}>{profile.age} yrs</span>}
                {profile?.nationality && <span className={HERO_CHIP}>{profile.nationality}</span>}
                {profile?.status && (
                  <span
                    className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${
                      STATUS_BADGE_CLASSES[profile.status] || 'bg-secondary text-muted-foreground'
                    }`}
                  >
                    {profile.status.replace('_', ' ')}
                    {profile.status === 'on_loan' && profile.owner_team_name
                      ? ` · from ${profile.owner_team_name}`
                      : ''}
                    {profile.sale_fee ? ` · ${profile.sale_fee}` : ''}
                  </span>
                )}
                {academyApps && (
                  <span className={HERO_CHIP}>Academy: {academyApps} apps</span>
                )}
              </div>

              {/* Academy crest → current club journey affordance */}
              {profile?.parent_team_name && (
                <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
                  <button
                    onClick={onParentClubClick}
                    className="group inline-flex items-center gap-1.5 rounded-md text-primary-foreground/90 transition-colors hover:text-primary-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-foreground/60 dark:text-foreground/80 dark:hover:text-foreground dark:focus-visible:ring-primary/60"
                    aria-label={`Browse other ${profile.parent_team_name} academy players`}
                  >
                    {profile.parent_team_logo && (
                      <img
                        src={profile.parent_team_logo}
                        alt=""
                        width={20}
                        height={20}
                        className="h-5 w-5 rounded-full bg-white/80 object-cover"
                      />
                    )}
                    <span className="font-medium group-hover:underline">
                      {profile.parent_team_name} Academy
                    </span>
                    <Users className="h-3.5 w-3.5 opacity-70" />
                  </button>
                  {currentClub?.team_name && currentClub.team_name !== profile.parent_team_name && (
                    <>
                      <ArrowRight className="h-4 w-4 text-primary-foreground/60 dark:text-foreground/50" />
                      <span className="inline-flex items-center gap-1.5 font-medium text-primary-foreground/90 dark:text-foreground/80">
                        {currentClub.team_logo && (
                          <img
                            src={currentClub.team_logo}
                            alt=""
                            width={20}
                            height={20}
                            className="h-5 w-5 rounded-full bg-white/80 object-cover"
                          />
                        )}
                        {currentClub.team_name}
                      </span>
                    </>
                  )}
                </div>
              )}

              {/* Career-stops mini progression */}
              <MiniProgressBar />
            </div>
          </div>

          {/* Key-stat strip — only stats that exist */}
          {heroStats.length > 0 && (
            <div className="mt-6 grid grid-cols-2 gap-2 sm:mt-7 sm:flex sm:flex-wrap sm:gap-3">
              {heroStats.map((s) => (
                <div
                  key={s.label}
                  className={`rounded-xl border border-primary-foreground/15 bg-primary-foreground/10 px-4 py-3 text-center sm:min-w-[104px] sm:flex-1 dark:border-primary/20 dark:bg-primary/10 ${
                    s.wide && heroStats.length % 2 === 1 ? 'col-span-2 sm:col-auto' : ''
                  }`}
                >
                  <div className="text-2xl font-bold tabular-nums sm:text-3xl">{s.value}</div>
                  <div className="mt-0.5 text-[11px] font-medium uppercase tracking-wider text-primary-foreground/70 dark:text-muted-foreground">
                    {s.label}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Actions: Share · Claim */}
          <div className="mt-6 flex flex-wrap items-center gap-3">
            <ShareMenu
              playerId={playerApiId}
              playerName={playerName}
              profile={profile}
              seasonTotals={seasonTotals}
              position={position}
              variant="hero"
            />
            <ClaimAffordance claimState={claimState} onClaim={onClaim} />
          </div>
        </div>
      </header>
    </>
  )
}

export default ProfileHero
