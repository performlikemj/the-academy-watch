import React, { useState, useEffect, useCallback, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button.jsx'
import { Card, CardContent } from '@/components/ui/card.jsx'
import { Badge } from '@/components/ui/badge.jsx'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar.jsx'
import { Loader2, ArrowLeft, Calendar, ExternalLink, User } from 'lucide-react'
import { APIService } from '@/lib/api'
import { WriterToggleBar } from './WriterToggleBar'
import { CommentaryCard } from './CommentaryCard'
import { cn } from '@/lib/utils'

// Player card with embedded commentary
function PlayerCard({ player, commentaries = [], onSubscribe }) {
  const hasCommentaries = commentaries.length > 0

  return (
    <div className={cn(
      'bg-card rounded-lg border overflow-hidden',
      hasCommentaries ? 'ring-2 ring-violet-200 shadow-md' : 'shadow-sm'
    )}>
      {/* Player Header */}
      <div className="p-4 sm:p-5 border-b bg-gradient-to-r from-secondary to-card">
        <div className="flex items-center gap-3 sm:gap-4">
          {player.player_photo ? (
            <img
              src={player.player_photo}
              alt={player.player_name}
              className="h-14 w-14 sm:h-16 sm:w-16 rounded-full object-cover border-2 border-white shadow"
            />
          ) : (
            <div className="h-14 w-14 sm:h-16 sm:w-16 rounded-full bg-muted flex items-center justify-center">
              <User className="h-6 w-6 text-muted-foreground/70" />
            </div>
          )}
          <div className="flex-1 min-w-0">
            <h3 className="font-bold text-foreground text-base sm:text-lg truncate">
              {player.player_name}
            </h3>
            <div className="flex items-center gap-2 mt-1">
              {player.loan_team_logo && (
                <img
                  src={player.loan_team_logo}
                  alt={player.loan_team}
                  className="h-4 w-4 object-contain"
                />
              )}
              <span className="text-sm text-muted-foreground truncate">{player.loan_team}</span>
            </div>
          </div>
        </div>

        {/* Stats Summary */}
        {player.stats && (
          <div className="flex flex-wrap gap-2 mt-3">
            {player.stats.minutes > 0 && (
              <Badge variant="secondary" className="text-xs">{player.stats.minutes}'</Badge>
            )}
            {player.stats.goals > 0 && (
              <Badge className="bg-green-100 text-green-800 text-xs">
                {player.stats.goals} goal{player.stats.goals > 1 ? 's' : ''}
              </Badge>
            )}
            {player.stats.assists > 0 && (
              <Badge className="bg-primary/10 text-primary text-xs">
                {player.stats.assists} assist{player.stats.assists > 1 ? 's' : ''}
              </Badge>
            )}
            {player.stats.rating && (
              <Badge variant="outline" className="text-xs">
                {player.stats.rating} rating
              </Badge>
            )}
          </div>
        )}

        {/* Narrative summary if no commentary */}
        {!hasCommentaries && player.narrative && (
          <p className="mt-3 text-sm text-muted-foreground line-clamp-3">{player.narrative}</p>
        )}
      </div>

      {/* Embedded Commentaries */}
      {hasCommentaries && (
        <div className="p-3 sm:p-4 space-y-3 bg-violet-50/30">
          <div className="flex items-center gap-2 text-xs font-semibold text-violet-700 uppercase tracking-wide">
            <span>Writer Analysis</span>
            <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
              {commentaries.length}
            </Badge>
          </div>
          {commentaries.map(c => (
            <CommentaryCard
              key={c.id}
              commentary={c}
              variant="compact"
              showTypeLabel={false}
              onSubscribe={onSubscribe}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// Section component for grouping players
function NewsletterSection({ section, playerCommentaries, onSubscribe }) {
  return (
    <div className="space-y-4">
      <h2 className="text-lg sm:text-xl font-bold text-foreground px-1">{section.title}</h2>
      <div className="grid gap-4">
        {section.players.map(player => (
          <PlayerCard
            key={player.player_id}
            player={player}
            commentaries={playerCommentaries[player.player_id]?.commentaries || []}
            onSubscribe={onSubscribe}
          />
        ))}
      </div>
    </div>
  )
}

export function JournalistNewsletterView() {
  const { newsletterId, journalistId: initialJournalistIdParam } = useParams()
  const navigate = useNavigate()

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [data, setData] = useState(null)

  const [activeJournalistIds, setActiveJournalistIds] = useState(() => {
    const initialId = parseInt(initialJournalistIdParam, 10)
    return initialId ? new Set([initialId]) : new Set()
  })

  const initialJournalistId = useMemo(() => {
    const parsed = parseInt(initialJournalistIdParam, 10)
    return isNaN(parsed) ? null : parsed
  }, [initialJournalistIdParam])

  const fetchData = useCallback(async (journalistIds) => {
    if (!newsletterId) return

    setLoading(true)
    setError(null)

    try {
      const result = await APIService.getNewsletterJournalistView(
        newsletterId,
        Array.from(journalistIds)
      )
      setData(result)
    } catch (err) {
      console.error('Failed to load newsletter view:', err)
      setError(err.message || 'Failed to load newsletter')
    } finally {
      setLoading(false)
    }
  }, [newsletterId])

  useEffect(() => {
    if (initialJournalistId) {
      setActiveJournalistIds(new Set([initialJournalistId]))
      fetchData(new Set([initialJournalistId]))
    } else {
      fetchData(new Set())
    }
  }, [initialJournalistId, fetchData])

  const handleToggle = useCallback((journalistId) => {
    setActiveJournalistIds(prev => {
      const newSet = new Set(prev)
      if (newSet.has(journalistId)) {
        newSet.delete(journalistId)
      } else {
        newSet.add(journalistId)
      }
      fetchData(newSet)
      return newSet
    })
  }, [fetchData])

  // Update meta tags for social sharing
  useEffect(() => {
    if (!data || !data.available_journalists) return

    const activeWriters = data.available_journalists.filter(j => activeJournalistIds.has(j.id))

    if (activeWriters.length > 0) {
      const updateTag = (property, content) => {
        let tag = document.querySelector(`meta[property="${property}"]`)
        if (!tag) {
          tag = document.createElement('meta')
          tag.setAttribute('property', property)
          document.head.appendChild(tag)
        }
        tag.setAttribute('content', content)
      }

      // Description
      const writerNames = activeWriters.map(w => w.display_name).join(', ')
      const description = `Read analysis by ${writerNames} on ${data.newsletter?.team?.name || 'The Academy Watch'}`
      updateTag('og:description', description)

      // Author / Attribution
      if (activeWriters.length === 1) {
        const writer = activeWriters[0]
        updateTag('og:author', writer.attribution_name || writer.display_name)
        if (writer.attribution_url) {
          updateTag('article:author', writer.attribution_url)
        }
      } else {
        const attribution = activeWriters.map(w => w.attribution_name || w.display_name).join(', ')
        updateTag('og:author', attribution)
      }
    }
  }, [data, activeJournalistIds])

  const handleSubscribe = useCallback((journalistId) => {
    navigate(`/journalists/${journalistId}`)
  }, [navigate])

  if (loading && !data) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[50vh] px-4">
        <Loader2 className="h-8 w-8 animate-spin text-violet-500 mb-3" />
        <p className="text-muted-foreground">Loading newsletter...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="max-w-lg mx-auto py-12 px-4 text-center space-y-4">
        <h2 className="text-xl font-semibold text-foreground">Unable to load newsletter</h2>
        <p className="text-muted-foreground">{error}</p>
        <Button variant="ghost" onClick={() => navigate(-1)}>
          <ArrowLeft className="mr-2 h-4 w-4" /> Go back
        </Button>
      </div>
    )
  }

  const newsletter = data?.newsletter
  const commentaries = data?.commentaries || { intro: [], player: {}, summary: [] }
  const sections = data?.sections || []

  return (
    <div className="min-h-screen bg-secondary">
      {/* Header */}
      <div className="bg-card border-b">
        <div className="max-w-3xl mx-auto px-4 py-4">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate(-1)}
            className="-ml-2 mb-3"
          >
            <ArrowLeft className="mr-2 h-4 w-4" /> Back
          </Button>

          {/* Newsletter Title */}
          <div className="flex items-start gap-3 sm:gap-4">
            {newsletter?.team?.logo && (
              <img
                src={newsletter.team.logo}
                alt={newsletter.team.name}
                className="h-12 w-12 sm:h-14 sm:w-14 object-contain flex-shrink-0"
              />
            )}
            <div className="flex-1 min-w-0">
              <h1 className="text-lg sm:text-xl font-bold text-foreground leading-tight">
                {newsletter?.title}
              </h1>
              <div className="flex flex-wrap items-center gap-2 mt-1 text-sm text-muted-foreground">
                {newsletter?.team?.name && (
                  <span>{newsletter.team.name}</span>
                )}
                {newsletter?.week_start_date && newsletter?.week_end_date && (
                  <>
                    <span>·</span>
                    <span className="flex items-center gap-1">
                      <Calendar className="h-3.5 w-3.5" />
                      {newsletter.week_start_date} – {newsletter.week_end_date}
                    </span>
                  </>
                )}
              </div>
            </div>
          </div>

          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate(`/newsletters/${newsletterId}`)}
            className="mt-3 w-full sm:w-auto"
          >
            <ExternalLink className="h-4 w-4 mr-2" />
            View Full Newsletter
          </Button>
        </div>
      </div>

      {/* Writer Toggle Bar */}
      <WriterToggleBar
        journalists={data?.available_journalists || []}
        activeIds={activeJournalistIds}
        onToggle={handleToggle}
        onSubscribe={handleSubscribe}
      />

      {/* Main Content */}
      <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">

        {/* Empty State */}
        {activeJournalistIds.size === 0 && (
          <Card className="border-dashed bg-card/50">
            <CardContent className="py-8 sm:py-12 text-center">
              <p className="text-muted-foreground mb-2">
                Select a writer above to see their analysis
              </p>
              <p className="text-sm text-muted-foreground/70">
                Analysis will appear inline with each player they've written about.
              </p>
            </CardContent>
          </Card>
        )}

        {/* Intro Commentaries */}
        {commentaries.intro?.length > 0 && (
          <div className="space-y-4">
            {commentaries.intro.map(c => (
              <CommentaryCard
                key={c.id}
                commentary={c}
                showTypeLabel={true}
                onSubscribe={handleSubscribe}
              />
            ))}
          </div>
        )}

        {/* Player Sections with embedded commentaries */}
        {sections.length > 0 ? (
          sections.map((section, idx) => (
            <NewsletterSection
              key={idx}
              section={section}
              playerCommentaries={commentaries.player}
              onSubscribe={handleSubscribe}
            />
          ))
        ) : activeJournalistIds.size > 0 && (
          /* Fallback: Show player commentaries with context if no sections */
          Object.keys(commentaries.player).length > 0 && (
            <div className="space-y-4">
              <h2 className="text-lg font-bold text-foreground px-1">Player Analysis</h2>
              {Object.entries(commentaries.player).map(([playerId, data]) => (
                <div key={playerId} className="bg-card rounded-lg border shadow-sm overflow-hidden">
                  {/* Player info header */}
                  {data.player_info && (
                    <div className="p-4 border-b bg-secondary flex items-center gap-3">
                      {data.player_info.photo ? (
                        <img
                          src={data.player_info.photo}
                          alt={data.player_info.name}
                          className="h-12 w-12 rounded-full object-cover border-2 border-white shadow"
                        />
                      ) : (
                        <div className="h-12 w-12 rounded-full bg-muted flex items-center justify-center">
                          <User className="h-5 w-5 text-muted-foreground/70" />
                        </div>
                      )}
                      <div>
                        <h3 className="font-bold text-foreground">{data.player_info.name || 'Player'}</h3>
                        {data.player_info.loan_team && (
                          <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
                            {data.player_info.loan_team_logo && (
                              <img src={data.player_info.loan_team_logo} alt="" className="h-4 w-4 object-contain" />
                            )}
                            <span>{data.player_info.loan_team}</span>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                  {/* Commentaries */}
                  <div className="p-3 sm:p-4 space-y-3 bg-violet-50/30">
                    {data.commentaries.map(c => (
                      <CommentaryCard
                        key={c.id}
                        commentary={c}
                        variant="compact"
                        showTypeLabel={false}
                        onSubscribe={handleSubscribe}
                      />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )
        )}

        {/* Summary Commentaries */}
        {commentaries.summary?.length > 0 && (
          <div className="space-y-4">
            {commentaries.summary.map(c => (
              <CommentaryCard
                key={c.id}
                commentary={c}
                showTypeLabel={true}
                onSubscribe={handleSubscribe}
              />
            ))}
          </div>
        )}
      </div>

      {/* Loading overlay */}
      {loading && data && (
        <div className="fixed inset-0 bg-card/60 backdrop-blur-sm flex items-center justify-center z-50">
          <Loader2 className="h-8 w-8 animate-spin text-violet-500" />
        </div>
      )}
    </div>
  )
}

export default JournalistNewsletterView
