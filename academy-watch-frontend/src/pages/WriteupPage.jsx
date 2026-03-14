import { useEffect, useState, useMemo } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar'
import {
  Loader2, ArrowLeft, ArrowRight, Lock, Calendar, Trophy,
  Clock, Target, Users, Shield, Footprints, AlertTriangle,
  Sparkles, ExternalLink
} from 'lucide-react'
import { APIService } from '@/lib/api'
import { cn } from '@/lib/utils'
import ClapIcon from '@/components/ClapIcon.jsx'
import { BlockRenderer } from '@/components/BlockRenderer'
import { formatTextToHtml } from '@/lib/formatText'
import { CommentSection } from '@/components/CommentSection'

// Stat display helper
function StatItem({ icon: Icon, label, value, highlight = false }) {
  if (value === null || value === undefined) return null
  return (
    <div className={cn(
      'flex items-center gap-2 px-3 py-2 rounded-lg',
      highlight ? 'bg-emerald-50 text-emerald-700' : 'bg-secondary text-foreground/80'
    )}>
      <Icon className="h-4 w-4 flex-shrink-0" />
      <span className="text-sm font-medium">{label}</span>
      <span className={cn(
        'ml-auto font-bold',
        highlight ? 'text-emerald-800' : 'text-foreground'
      )}>
        {value}
      </span>
    </div>
  )
}

// Fixture card component
function FixtureCard({ fixture }) {
  const { home_team, away_team, stats, date, competition, is_home } = fixture
  const playerTeam = is_home ? home_team : away_team
  const opponentTeam = is_home ? away_team : home_team

  // Determine result
  const playerScore = is_home ? home_team.score : away_team.score
  const opponentScore = is_home ? away_team.score : home_team.score
  let result = 'draw'
  if (playerScore > opponentScore) result = 'win'
  else if (playerScore < opponentScore) result = 'loss'

  const resultColors = {
    win: 'bg-emerald-500',
    loss: 'bg-rose-500',
    draw: 'bg-stone-400'
  }

  const formattedDate = date ? new Date(date).toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric'
  }) : ''

  return (
    <Card className="overflow-hidden">
      {/* Match Header */}
      <div className="bg-gradient-to-r from-foreground to-foreground/90 text-primary-foreground p-4">
        <div className="flex items-center justify-between mb-3">
          <Badge variant="secondary" className="bg-white/20 text-primary-foreground border-none text-xs">
            {competition || 'Match'}
          </Badge>
          <span className="text-xs text-muted-foreground/50">{formattedDate}</span>
        </div>

        {/* Score Display */}
        <div className="flex items-center justify-center gap-2 sm:gap-4">
          <div className="flex items-center gap-2 flex-1 justify-end min-w-0">
            {home_team.logo && (
              <img src={home_team.logo} alt={home_team.name} width={32} height={32} className="h-6 w-6 sm:h-8 sm:w-8 object-contain flex-shrink-0" />
            )}
            <span className={cn(
              'font-semibold text-xs sm:text-sm truncate',
              is_home && 'text-primary-foreground',
              !is_home && 'text-primary-foreground/60'
            )}>
              {home_team.name}
            </span>
          </div>

          <div className="flex items-center gap-1.5 sm:gap-2 px-2 sm:px-4 flex-shrink-0">
            <span className="text-xl sm:text-2xl font-bold tabular-nums">{home_team.score ?? '-'}</span>
            <span className="text-primary-foreground/50">-</span>
            <span className="text-xl sm:text-2xl font-bold tabular-nums">{away_team.score ?? '-'}</span>
          </div>

          <div className="flex items-center gap-2 flex-1 min-w-0">
            <span className={cn(
              'font-semibold text-xs sm:text-sm truncate',
              !is_home && 'text-primary-foreground',
              is_home && 'text-primary-foreground/60'
            )}>
              {away_team.name}
            </span>
            {away_team.logo && (
              <img src={away_team.logo} alt={away_team.name} width={32} height={32} className="h-6 w-6 sm:h-8 sm:w-8 object-contain flex-shrink-0" />
            )}
          </div>
        </div>

        {/* Result indicator */}
        <div className="flex justify-center mt-3">
          <Badge className={cn(resultColors[result], 'text-primary-foreground border-none')}>
            {result === 'win' ? 'Victory' : result === 'loss' ? 'Defeat' : 'Draw'}
          </Badge>
        </div>
      </div>

      {/* Player Stats */}
      <CardContent className="p-4 space-y-4">
        {/* Key Stats Row */}
        <div className="grid grid-cols-3 gap-2 text-center">
          <div className="p-3 bg-secondary rounded-lg">
            <div className="text-2xl font-bold text-foreground">{stats.minutes || 0}'</div>
            <div className="text-xs text-muted-foreground uppercase tracking-wide">Minutes</div>
          </div>
          <div className={cn(
            'p-3 rounded-lg',
            stats.goals > 0 ? 'bg-emerald-50' : 'bg-secondary'
          )}>
            <div className={cn(
              'text-2xl font-bold',
              stats.goals > 0 ? 'text-emerald-600' : 'text-foreground'
            )}>
              {stats.goals || 0}
            </div>
            <div className="text-xs text-muted-foreground uppercase tracking-wide">Goals</div>
          </div>
          <div className={cn(
            'p-3 rounded-lg',
            stats.assists > 0 ? 'bg-amber-50' : 'bg-secondary'
          )}>
            <div className={cn(
              'text-2xl font-bold',
              stats.assists > 0 ? 'text-amber-600' : 'text-foreground'
            )}>
              {stats.assists || 0}
            </div>
            <div className="text-xs text-muted-foreground uppercase tracking-wide">Assists</div>
          </div>
        </div>

        {/* Rating if available */}
        {stats.rating && (
          <div className="flex items-center justify-center">
            <Badge
              variant="outline"
              className={cn(
                'text-lg font-bold px-4 py-1',
                stats.rating >= 7.5 ? 'border-emerald-500 text-emerald-700 bg-emerald-50' :
                  stats.rating >= 6.5 ? 'border-amber-500 text-amber-700 bg-amber-50' :
                    stats.rating >= 5.5 ? 'border-border text-foreground/80 bg-secondary' :
                      'border-rose-500 text-rose-700 bg-rose-50'
              )}
            >
              {stats.rating.toFixed(1)} Rating
            </Badge>
          </div>
        )}

        {/* Detailed Stats Grid */}
        <div className="grid grid-cols-2 gap-2">
          {stats.shots?.total != null && (
            <StatItem
              icon={Target}
              label="Shots"
              value={`${stats.shots.on_target ?? 0}/${stats.shots.total}`}
            />
          )}
          {stats.passes?.total != null && (
            <StatItem
              icon={Footprints}
              label="Passes"
              value={`${stats.passes.total} (${stats.passes.accuracy || '-'})`}
            />
          )}
          {stats.passes?.key != null && stats.passes.key > 0 && (
            <StatItem
              icon={Sparkles}
              label="Key Passes"
              value={stats.passes.key}
              highlight
            />
          )}
          {stats.tackles?.total != null && (
            <StatItem
              icon={Shield}
              label="Tackles"
              value={stats.tackles.total}
            />
          )}
          {stats.duels?.total != null && (
            <StatItem
              icon={Users}
              label="Duels Won"
              value={`${stats.duels.won ?? 0}/${stats.duels.total}`}
            />
          )}
          {stats.dribbles?.attempts != null && stats.dribbles.attempts > 0 && (
            <StatItem
              icon={Footprints}
              label="Dribbles"
              value={`${stats.dribbles.success ?? 0}/${stats.dribbles.attempts}`}
            />
          )}
          {/* Goalkeeper stats */}
          {stats.saves != null && stats.saves > 0 && (
            <StatItem
              icon={Shield}
              label="Saves"
              value={stats.saves}
              highlight
            />
          )}
        </div>

        {/* Cards */}
        {(stats.yellows > 0 || stats.reds > 0) && (
          <div className="flex items-center gap-2 justify-center pt-2 border-t">
            {stats.yellows > 0 && (
              <Badge variant="outline" className="bg-yellow-50 text-yellow-700 border-yellow-300">
                <div className="h-3 w-2 bg-yellow-400 rounded-sm mr-1.5" />
                {stats.yellows} Yellow
              </Badge>
            )}
            {stats.reds > 0 && (
              <Badge variant="outline" className="bg-red-50 text-red-700 border-red-300">
                <div className="h-3 w-2 bg-red-500 rounded-sm mr-1.5" />
                {stats.reds} Red
              </Badge>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export function WriteupPage() {
  const { commentaryId } = useParams()
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [applauseCount, setApplauseCount] = useState(0)
  const [hasApplauded, setHasApplauded] = useState(false)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        const res = await APIService.getCommentary(commentaryId)
        if (!cancelled) {
          setData(res)
          setApplauseCount(res.applause_count || 0)
        }
      } catch (err) {
        if (!cancelled) setError(err.message || 'Failed to load writeup')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [commentaryId])

  const handleApplause = async () => {
    if (hasApplauded) return
    setApplauseCount(prev => prev + 1)
    setHasApplauded(true)
    try {
      await APIService.applaudCommentary(commentaryId)
    } catch {
      setApplauseCount(prev => prev - 1)
      setHasApplauded(false)
    }
  }

  if (loading) {
    return (
      <div className="min-h-[60vh] flex flex-col items-center justify-center px-4">
        <Loader2 className="h-8 w-8 animate-spin text-violet-500 mb-3" />
        <p className="text-muted-foreground">Loading analysis...</p>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="max-w-lg mx-auto py-12 px-4 text-center space-y-4">
        <AlertTriangle className="h-12 w-12 text-amber-500 mx-auto mb-4" />
        <h2 className="text-xl font-semibold text-foreground">Analysis unavailable</h2>
        <p className="text-muted-foreground">{error || 'We could not find this analysis.'}</p>
        <Button variant="ghost" onClick={() => navigate(-1)}>
          <ArrowLeft className="mr-2 h-4 w-4" /> Go back
        </Button>
      </div>
    )
  }

  const team = data.team
  const player = data.player
  const author = data.author
  const isLocked = data.is_locked
  const weekFixtures = data.week_fixtures || []

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="bg-card border-b sticky top-0 z-10">
        <div className="max-w-3xl mx-auto px-4 py-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate(-1)}
            className="-ml-2"
          >
            <ArrowLeft className="mr-2 h-4 w-4" /> Back
          </Button>
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">

        {/* Article Header Card */}
        <Card className="overflow-hidden">
          {/* Hero section with team/player */}
          <div className="bg-gradient-to-br from-foreground via-foreground/90 to-foreground text-primary-foreground p-6">
            <div className="flex items-start gap-4">
              {player?.photo_url ? (
                data.player_id ? (
                  <Link to={`/players/${data.player_id}`}>
                    <img
                      src={player.photo_url}
                      alt={player.name}
                      className="h-20 w-20 rounded-full object-cover border-4 border-white/20 shadow-lg hover:border-white/40 transition-colors"
                    />
                  </Link>
                ) : (
                  <img
                    src={player.photo_url}
                    alt={player.name}
                    className="h-20 w-20 rounded-full object-cover border-4 border-white/20 shadow-lg"
                  />
                )
              ) : team?.logo ? (
                <img
                  src={team.logo}
                  alt={team.name}
                  className="h-20 w-20 object-contain"
                />
              ) : null}

              <div className="flex-1 min-w-0">
                {player && (
                  data.player_id ? (
                    <Link to={`/players/${data.player_id}`} className="hover:underline decoration-white/50">
                      <h2 className="text-xl sm:text-2xl font-bold truncate">{player.name}</h2>
                    </Link>
                  ) : (
                    <h2 className="text-xl sm:text-2xl font-bold truncate">{player.name}</h2>
                  )
                )}
                <div className="flex flex-wrap items-center gap-2 mt-1">
                  {team?.name && (
                    <Badge className="bg-white/20 text-primary-foreground border-none">
                      {team.name}
                    </Badge>
                  )}
                  {player?.position && (
                    <Badge variant="outline" className="text-primary-foreground/60 border-primary-foreground/30">
                      {player.position}
                    </Badge>
                  )}
                  {player?.nationality && (
                    <span className="text-sm text-primary-foreground/50">{player.nationality}</span>
                  )}
                </div>

                {data.player_id && (
                  <Link
                    to={`/players/${data.player_id}`}
                    className="inline-flex items-center gap-1.5 mt-3 text-sm text-primary-foreground/60 hover:text-primary-foreground transition-colors"
                  >
                    View Full Profile <ArrowRight className="h-3.5 w-3.5" />
                  </Link>
                )}

                {/* Week context */}
                {data.week_start_date && data.week_end_date && (
                  <div className="flex items-center gap-2 mt-3 text-sm text-primary-foreground/50">
                    <Calendar className="h-4 w-4" />
                    <span>Week of {data.week_start_date} – {data.week_end_date}</span>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Author & Article Info */}
          <CardContent className="p-4 sm:p-6">
            {/* Author Row - shows contributor as primary if present */}
            {(() => {
              const hasContributor = !!data.contributor_id
              const primaryName = hasContributor ? data.contributor_name : (author?.display_name || data.author_name)
              const primaryPhoto = hasContributor ? data.contributor_photo_url : author?.profile_image_url
              const primaryAttribUrl = hasContributor ? data.contributor_attribution_url : author?.attribution_url
              const primaryAttribName = hasContributor ? data.contributor_attribution_name : author?.attribution_name

              return (
                <div className="flex items-center gap-3 mb-4 pb-4 border-b">
                  <Avatar className="h-10 w-10">
                    {primaryPhoto ? (
                      <AvatarImage src={primaryPhoto} alt={primaryName} />
                    ) : null}
                    <AvatarFallback className="bg-violet-100 text-violet-700">
                      {(primaryName || 'A').substring(0, 2).toUpperCase()}
                    </AvatarFallback>
                  </Avatar>
                  <div className="flex-1">
                    <div className="font-semibold text-foreground flex items-center gap-2 flex-wrap">
                      {primaryName}
                      {hasContributor && (author?.display_name || data.author_name) && (
                        <span className="text-sm font-normal text-muted-foreground">
                          via {author?.display_name || data.author_name}
                        </span>
                      )}
                      {(primaryAttribUrl || primaryAttribName) && (
                        <>
                          <span className="text-muted-foreground/50">•</span>
                          {primaryAttribUrl ? (
                            <a
                              href={primaryAttribUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-sm font-normal text-muted-foreground hover:text-primary hover:underline flex items-center gap-1"
                            >
                              {primaryAttribName || 'Visit Site'}
                              <ExternalLink className="h-3 w-3" />
                            </a>
                          ) : (
                            <span className="text-sm font-normal text-muted-foreground">
                              {primaryAttribName}
                            </span>
                          )}
                        </>
                      )}
                    </div>
                    <div className="text-sm text-muted-foreground">
                      {data.created_at && new Date(data.created_at).toLocaleDateString(undefined, {
                        year: 'numeric',
                        month: 'long',
                        day: 'numeric'
                      })}
                    </div>
                  </div>
                  {data.is_premium && (
                    <Badge variant="outline" className="border-amber-300 text-amber-700 bg-amber-50">
                      <Sparkles className="h-3 w-3 mr-1" />
                      Premium
                    </Badge>
                  )}
                </div>
              )
            })()}

            {/* Title */}
            {data.title && (
              <h1 className="text-2xl sm:text-3xl font-bold text-foreground leading-tight mb-4">
                {data.title}
              </h1>
            )}

            {/* Content - supports both structured blocks and legacy HTML */}
            {data.structured_blocks && data.structured_blocks.length > 0 ? (
              // New block-based content rendering
              <BlockRenderer
                blocks={data.structured_blocks}
                isSubscribed={!isLocked}
                playerId={data.player_id}
                weekRange={{
                  start: data.week_start_date,
                  end: data.week_end_date,
                }}
                authorName={author?.display_name || data.author_name}
                authorId={author?.id || data.author_id}
                onSubscribe={() => author?.id && navigate(`/journalists/${author.id}`)}
              />
            ) : isLocked ? (
              // Legacy locked content
              <div className="relative">
                <div
                  className="prose prose-gray max-w-full break-words blur-sm select-none line-clamp-4"
                  dangerouslySetInnerHTML={{ __html: formatTextToHtml(data.content) }}
                />
                <div className="absolute inset-0 flex flex-col items-center justify-center bg-gradient-to-t from-card via-card/95 to-transparent">
                  <Lock className="h-8 w-8 text-muted-foreground/70 mb-3" />
                  <p className="text-muted-foreground mb-3 text-center">
                    Subscribe to {author?.display_name || 'this writer'} to read the full analysis
                  </p>
                  <Button
                    onClick={() => author?.id && navigate(`/journalists/${author.id}`)}
                    className="bg-foreground hover:bg-foreground/90 text-primary-foreground rounded-full px-6"
                  >
                    Subscribe
                  </Button>
                </div>
              </div>
            ) : (
              // Legacy unlocked content
              <div
                className="prose prose-gray max-w-full break-words
                  prose-headings:text-foreground prose-headings:font-bold
                  prose-p:text-foreground/80 prose-p:leading-relaxed prose-p:my-2
                  prose-ul:my-2 prose-ul:pl-5 prose-li:my-1
                  prose-strong:text-foreground
                  prose-a:text-violet-600 prose-a:no-underline hover:prose-a:underline"
                dangerouslySetInnerHTML={{ __html: formatTextToHtml(data.content) }}
              />
            )}

            {/* Footer actions */}
            {!isLocked && (
              <div className="flex items-center gap-4 mt-6 pt-4 border-t">
                <button
                  onClick={handleApplause}
                  disabled={hasApplauded}
                  aria-label={hasApplauded ? `Applauded (${applauseCount})` : 'Applaud this writeup'}
                  className={cn(
                    'flex items-center gap-2 px-4 py-2 rounded-full transition-colors focus-visible:ring-2 focus-visible:ring-violet-500 focus-visible:outline-none',
                    hasApplauded
                      ? 'bg-violet-100 text-violet-700'
                      : 'bg-secondary text-muted-foreground hover:bg-violet-50 hover:text-violet-600'
                  )}
                >
                  <ClapIcon className={cn(
                    'h-4 w-4 transition-transform',
                    hasApplauded && 'scale-105'
                  )} />
                  <span className="font-medium">
                    {applauseCount > 0 ? applauseCount : 'Applaud'}
                  </span>
                </button>

                {author?.id && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => navigate(`/journalists/${author.id}`)}
                  >
                    More from {author.display_name}
                  </Button>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Week's Match Performance */}
        {weekFixtures.length > 0 && (
          <div className="space-y-4">
            <h2 className="text-lg font-bold text-foreground px-1 flex items-center gap-2">
              <Trophy className="h-5 w-5 text-amber-500" />
              This Week's Performance
            </h2>

            <div className="space-y-4">
              {weekFixtures.map((fixture, idx) => (
                <FixtureCard key={idx} fixture={fixture} />
              ))}
            </div>
          </div>
        )}

        {/* Link to newsletter if available */}
        {data.newsletter_id && (
          <Card className="bg-gradient-to-r from-violet-50 to-indigo-50 border-violet-200">
            <CardContent className="p-4 flex items-center gap-4">
              <div className="flex-1">
                <h3 className="font-semibold text-foreground">Full Weekly Newsletter</h3>
                <p className="text-sm text-muted-foreground">
                  See all player performances and analysis for this week
                </p>
              </div>
              <Button
                onClick={() => navigate(`/newsletters/${data.newsletter_id}`)}
                className="bg-violet-600 hover:bg-violet-700 text-primary-foreground"
              >
                <ExternalLink className="h-4 w-4 mr-2" />
                View Newsletter
              </Button>
            </CardContent>
          </Card>
        )}

        {/* Comment Section */}
        {data.newsletter_id && (
          <CommentSection newsletterId={data.newsletter_id} />
        )}
      </div>
    </div>
  )
}
