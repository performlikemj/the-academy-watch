import React, { useState, useEffect, useCallback, useMemo, createContext, useContext } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar'
import {
  ChevronDown,
  ChevronUp,
  Sparkles,
  Users,
  Lock,
  Search,
  X,
  PenLine,
  Eye,
  ExternalLink
} from 'lucide-react'
import { CommentaryCard } from './CommentaryCard'
import { useAuth } from '@/context/AuthContext'
import { APIService } from '@/lib/api'
import { cn } from '@/lib/utils'

// Context for sharing writer data across newsletter components
const WriterCommentaryContext = createContext({
  commentaries: { intro: [], summary: [], player: {} },
  loading: false,
  activeWriterIds: new Set()
})

export const useWriterCommentaries = () => useContext(WriterCommentaryContext)

// Color palette for writers
const WRITER_COLORS = [
  { ring: 'ring-violet-500', bg: 'bg-violet-500', bgLight: 'bg-violet-50', text: 'text-violet-700', border: 'border-violet-200' },
  { ring: 'ring-amber-500', bg: 'bg-amber-500', bgLight: 'bg-amber-50', text: 'text-amber-700', border: 'border-amber-200' },
  { ring: 'ring-emerald-500', bg: 'bg-emerald-500', bgLight: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-200' },
  { ring: 'ring-rose-500', bg: 'bg-rose-500', bgLight: 'bg-rose-50', text: 'text-rose-700', border: 'border-rose-200' },
  { ring: 'ring-cyan-500', bg: 'bg-cyan-500', bgLight: 'bg-cyan-50', text: 'text-cyan-700', border: 'border-cyan-200' },
  { ring: 'ring-orange-500', bg: 'bg-orange-500', bgLight: 'bg-orange-50', text: 'text-orange-700', border: 'border-orange-200' },
]

/**
 * WriterDiscoveryBar - Shows available writers for a newsletter
 * Non-subscribers can browse and subscribe; subscribers see their active writers
 */
export function WriterDiscoveryBar({
  writers = [],
  activeWriterIds = new Set(),
  onToggleWriter,
  onSubscribe,
  isPreviewMode = false,
  className
}) {
  const [isExpanded, setIsExpanded] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')

  const filteredWriters = useMemo(() => {
    if (!searchQuery.trim()) return writers
    const query = searchQuery.toLowerCase()
    return writers.filter(w =>
      w.display_name?.toLowerCase().includes(query) ||
      w.bio?.toLowerCase().includes(query)
    )
  }, [writers, searchQuery])

  const subscribedWriters = useMemo(() =>
    writers.filter(w => w.is_subscribed || activeWriterIds.has(w.id)),
    [writers, activeWriterIds]
  )

  const unsubscribedWriters = useMemo(() =>
    filteredWriters.filter(w => !w.is_subscribed && !activeWriterIds.has(w.id)),
    [filteredWriters, activeWriterIds]
  )

  if (!writers || writers.length === 0) return null

  return (
    <div className={cn(
      'bg-gradient-to-r from-secondary to-card border rounded-xl shadow-sm overflow-hidden',
      className
    )}>
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-4 py-3 flex items-center justify-between hover:bg-slate-50/50 transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-violet-100">
            <PenLine className="h-4 w-4 text-violet-600" />
          </div>
          <div className="text-left">
            <h3 className="font-semibold text-foreground text-sm">
              {isPreviewMode ? 'Writer Preview Mode' : 'Expert Writers'}
            </h3>
            <p className="text-xs text-muted-foreground">
              {isPreviewMode
                ? 'See how your content appears to subscribers'
                : `${writers.length} writer${writers.length !== 1 ? 's' : ''} covering this newsletter`
              }
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {subscribedWriters.length > 0 && (
            <Badge variant="secondary" className="bg-green-100 text-green-700 text-xs">
              {subscribedWriters.length} active
            </Badge>
          )}
          {isExpanded ? (
            <ChevronUp className="h-4 w-4 text-muted-foreground/70" />
          ) : (
            <ChevronDown className="h-4 w-4 text-muted-foreground/70" />
          )}
        </div>
      </button>

      {/* Expanded content */}
      {isExpanded && (
        <div className="px-4 pb-4 space-y-4">
          {/* Search (only show if more than 3 writers) */}
          {writers.length > 3 && (
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/70" />
              <input
                type="text"
                placeholder="Search writers..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-8 py-2 text-sm border rounded-lg focus:ring-2 focus:ring-violet-200 focus:border-violet-400 outline-none"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground/70 hover:text-muted-foreground"
                >
                  <X className="h-4 w-4" />
                </button>
              )}
            </div>
          )}

          {/* Active/subscribed writers */}
          {subscribedWriters.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                {isPreviewMode ? 'Your Content' : 'Your Subscriptions'}
              </p>
              <div className="flex flex-wrap gap-2">
                {subscribedWriters.map((writer, index) => {
                  const colors = WRITER_COLORS[index % WRITER_COLORS.length]
                  const isActive = activeWriterIds.has(writer.id)

                  return (
                    <button
                      key={writer.id}
                      onClick={() => onToggleWriter?.(writer.id)}
                      className={cn(
                        'flex items-center gap-2 px-3 py-2 rounded-full transition-all duration-200',
                        'border-2',
                        isActive
                          ? cn(colors.bg, 'border-transparent text-white shadow-md')
                          : cn('bg-card border-border hover:border-border text-foreground/80')
                      )}
                    >
                      <Avatar className="h-6 w-6 border-2 border-white/30">
                        {writer.profile_image_url && (
                          <AvatarImage src={writer.profile_image_url} alt={writer.display_name} />
                        )}
                        <AvatarFallback className={cn(
                          'text-[10px] font-semibold',
                          isActive ? 'bg-card/20 text-white' : cn(colors.bgLight, colors.text)
                        )}>
                          {(writer.display_name || 'W').substring(0, 2).toUpperCase()}
                        </AvatarFallback>
                      </Avatar>
                      <span className="text-sm font-medium truncate max-w-[120px]">
                        {writer.display_name}
                      </span>
                      <Badge
                        variant="secondary"
                        className={cn(
                          'text-[10px] px-1.5 py-0',
                          isActive ? 'bg-card/20 text-white' : ''
                        )}
                      >
                        {writer.writeup_count || 0}
                      </Badge>
                      {isActive && <Eye className="h-3.5 w-3.5" />}
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          {/* Discover new writers */}
          {unsubscribedWriters.length > 0 && !isPreviewMode && (
            <div className="space-y-2">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                Discover Writers
              </p>
              <div className="grid gap-2">
                {unsubscribedWriters.map((writer, index) => {
                  const colors = WRITER_COLORS[(subscribedWriters.length + index) % WRITER_COLORS.length]

                  return (
                    <div
                      key={writer.id}
                      className={cn(
                        'flex items-center gap-3 p-3 rounded-lg border bg-card',
                        'hover:shadow-sm transition-shadow'
                      )}
                    >
                      <Avatar className={cn('h-10 w-10 border-2', colors.border)}>
                        {writer.profile_image_url && (
                          <AvatarImage src={writer.profile_image_url} alt={writer.display_name} />
                        )}
                        <AvatarFallback className={cn('font-semibold', colors.bgLight, colors.text)}>
                          {(writer.display_name || 'W').substring(0, 2).toUpperCase()}
                        </AvatarFallback>
                      </Avatar>

                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-foreground truncate">
                            {writer.display_name}
                          </span>
                          <Badge variant="outline" className="text-[10px] shrink-0">
                            {writer.writeup_count || 0} writeup{writer.writeup_count !== 1 ? 's' : ''}
                          </Badge>
                        </div>
                        {(writer.attribution_url || writer.attribution_name) && (
                          <div className="flex items-center gap-1 text-xs text-primary mt-0.5">
                            {writer.attribution_url ? (
                              <a
                                href={writer.attribution_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="hover:underline flex items-center gap-1"
                                onClick={(e) => e.stopPropagation()}
                              >
                                {writer.attribution_name || 'Visit Site'}
                                <ExternalLink className="h-2.5 w-2.5" />
                              </a>
                            ) : (
                              <span className="text-muted-foreground">{writer.attribution_name}</span>
                            )}
                          </div>
                        )}
                        {writer.bio && (
                          <p className="text-xs text-muted-foreground line-clamp-1 mt-0.5">
                            {writer.bio}
                          </p>
                        )}
                      </div>

                      <div className="flex items-center gap-2 shrink-0">
                        {writer.has_public ? (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => onToggleWriter?.(writer.id)}
                            className="text-xs h-8"
                          >
                            <Eye className="h-3 w-3 mr-1" />
                            Preview
                          </Button>
                        ) : (
                          <Badge variant="outline" className="text-[10px] text-muted-foreground/70">
                            <Lock className="h-2.5 w-2.5 mr-1" />
                            Premium
                          </Badge>
                        )}
                        <Button
                          size="sm"
                          onClick={() => onSubscribe?.(writer.id)}
                          className="text-xs h-8 bg-violet-600 hover:bg-violet-700"
                        >
                          <Users className="h-3 w-3 mr-1" />
                          Subscribe
                        </Button>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Empty state */}
          {filteredWriters.length === 0 && searchQuery && (
            <div className="text-center py-4 text-muted-foreground text-sm">
              No writers found matching "{searchQuery}"
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/**
 * WriterSummarySection - Shows team summary commentaries
 * Displayed after the agent-generated summary
 */
export function WriterSummarySection({
  commentaries = [],
  onSubscribe,
  className
}) {
  if (!commentaries || commentaries.length === 0) return null

  return (
    <div className={cn('space-y-4', className)}>
      <div className="flex items-center gap-2">
        <Sparkles className="h-4 w-4 text-violet-500" />
        <h3 className="font-semibold text-foreground">Expert Analysis</h3>
        <Badge variant="secondary" className="text-xs">
          {commentaries.length} writer{commentaries.length !== 1 ? 's' : ''}
        </Badge>
      </div>

      <div className="space-y-3">
        {commentaries.map(c => (
          <CommentaryCard
            key={c.id}
            commentary={c}
            showTypeLabel={true}
            onSubscribe={onSubscribe}
          />
        ))}
      </div>
    </div>
  )
}

/**
 * PlayerWriterCommentary - Shows commentary for a specific player
 * Embedded within the player's section in the newsletter
 */
export function PlayerWriterCommentary({
  playerId,
  playerName,
  commentaries = [],
  onSubscribe,
  className
}) {
  if (!commentaries || commentaries.length === 0) return null

  return (
    <div className={cn(
      'mt-4 pt-4 border-t border-violet-100 space-y-3',
      className
    )}>
      <div className="flex items-center gap-2 text-xs font-semibold text-violet-700 uppercase tracking-wide">
        <PenLine className="h-3.5 w-3.5" />
        <span>Writer Analysis on {playerName}</span>
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
  )
}

/**
 * useNewsletterWriters - Hook to fetch and manage writer data for a newsletter
 */
export function useNewsletterWriters(newsletterId) {
  const auth = useAuth()
  const [loading, setLoading] = useState(false)
  const [writers, setWriters] = useState([])
  const [commentaries, setCommentaries] = useState({
    intro: [],
    summary: [],
    player: {}
  })
  const [activeWriterIds, setActiveWriterIds] = useState(new Set())
  const [isPreviewMode, setIsPreviewMode] = useState(false)

  // Fetch writer data when newsletter or user changes
  const fetchData = useCallback(async (writerIds = []) => {
    if (!newsletterId) return

    setLoading(true)
    try {
      const result = await APIService.getNewsletterJournalistView(
        newsletterId,
        writerIds
      )

      setWriters(result.available_journalists || [])
      setCommentaries({
        intro: result.commentaries?.intro || [],
        summary: result.commentaries?.summary || [],
        player: result.commentaries?.player || {}
      })

      // Check if current user is a writer for this newsletter (preview mode)
      // is_self flag comes from the API when the journalist matches current user
      if (auth.isJournalist && result.available_journalists) {
        const selfWriter = result.available_journalists.find(w => w.is_self)
        setIsPreviewMode(!!selfWriter)
      }
    } catch (err) {
      console.error('Failed to fetch newsletter writers:', err)
    } finally {
      setLoading(false)
    }
  }, [newsletterId, auth.isJournalist])

  // Initial fetch - auto-enable subscribed writers and self (for preview)
  useEffect(() => {
    const init = async () => {
      if (!newsletterId) return

      setLoading(true)
      try {
        // First fetch without any writer IDs to get the list
        const result = await APIService.getNewsletterJournalistView(newsletterId, [])
        const availableWriters = result.available_journalists || []
        setWriters(availableWriters)

        // Auto-enable subscribed writers and self (is_self flag from API)
        const autoEnabledIds = new Set()
        let foundSelf = false
        availableWriters.forEach(w => {
          if (w.is_subscribed) {
            autoEnabledIds.add(w.id)
          }
          // Also enable self for preview (is_self comes from backend)
          if (w.is_self) {
            autoEnabledIds.add(w.id)
            foundSelf = true
          }
        })

        if (foundSelf) {
          setIsPreviewMode(true)
        }

        // If there are auto-enabled writers, fetch their content
        if (autoEnabledIds.size > 0) {
          setActiveWriterIds(autoEnabledIds)
          const resultWithContent = await APIService.getNewsletterJournalistView(
            newsletterId,
            Array.from(autoEnabledIds)
          )
          setCommentaries({
            intro: resultWithContent.commentaries?.intro || [],
            summary: resultWithContent.commentaries?.summary || [],
            player: resultWithContent.commentaries?.player || {}
          })
        }
      } catch (err) {
        console.error('Failed to init newsletter writers:', err)
      } finally {
        setLoading(false)
      }
    }

    init()
  }, [newsletterId, auth.isJournalist])

  // Toggle a writer on/off
  const toggleWriter = useCallback((writerId) => {
    setActiveWriterIds(prev => {
      const newSet = new Set(prev)
      if (newSet.has(writerId)) {
        newSet.delete(writerId)
      } else {
        newSet.add(writerId)
      }
      // Fetch updated content
      fetchData(Array.from(newSet))
      return newSet
    })
  }, [fetchData])

  return {
    loading,
    writers,
    commentaries,
    activeWriterIds,
    isPreviewMode,
    toggleWriter,
    refresh: () => fetchData(Array.from(activeWriterIds))
  }
}

/**
 * PlayerCommentarySection - Shows all player commentaries grouped
 */
function PlayerCommentarySection({
  playerCommentaries = {},
  onSubscribe,
  className
}) {
  // Flatten all player commentaries into a list with player info
  const allPlayerComments = useMemo(() => {
    const items = []
    Object.entries(playerCommentaries).forEach(([playerId, data]) => {
      const playerInfo = data.player_info || {}
      const comms = data.commentaries || []
      comms.forEach(c => {
        items.push({
          ...c,
          _player_id: playerId,
          _player_name: playerInfo.name || 'Unknown Player',
          _player_photo: playerInfo.photo,
          _loan_team: playerInfo.loan_team,
          _loan_team_logo: playerInfo.loan_team_logo
        })
      })
    })
    return items
  }, [playerCommentaries])

  if (allPlayerComments.length === 0) return null

  // Group by player
  const groupedByPlayer = useMemo(() => {
    const groups = {}
    allPlayerComments.forEach(c => {
      const key = c._player_id
      if (!groups[key]) {
        groups[key] = {
          player_name: c._player_name,
          player_photo: c._player_photo,
          loan_team: c._loan_team,
          loan_team_logo: c._loan_team_logo,
          commentaries: []
        }
      }
      groups[key].commentaries.push(c)
    })
    return Object.values(groups)
  }, [allPlayerComments])

  return (
    <div className={cn('space-y-4', className)}>
      <div className="flex items-center gap-2">
        <PenLine className="h-4 w-4 text-violet-500" />
        <h3 className="font-semibold text-foreground">Player Analysis</h3>
        <Badge variant="secondary" className="text-xs">
          {allPlayerComments.length} writeup{allPlayerComments.length !== 1 ? 's' : ''}
        </Badge>
      </div>

      <div className="space-y-4">
        {groupedByPlayer.map((group, idx) => (
          <div key={idx} className="bg-card rounded-lg border shadow-sm overflow-hidden">
            {/* Player header */}
            <div className="p-3 sm:p-4 border-b bg-gradient-to-r from-secondary to-card flex items-center gap-3">
              {group.player_photo ? (
                <img
                  src={group.player_photo}
                  alt={group.player_name}
                  className="h-12 w-12 rounded-full object-cover border-2 border-white shadow"
                />
              ) : (
                <div className="h-12 w-12 rounded-full bg-muted flex items-center justify-center">
                  <Users className="h-5 w-5 text-muted-foreground/70" />
                </div>
              )}
              <div className="flex-1 min-w-0">
                <h4 className="font-bold text-foreground truncate">{group.player_name}</h4>
                {group.loan_team && (
                  <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
                    {group.loan_team_logo && (
                      <img src={group.loan_team_logo} alt="" className="h-4 w-4 object-contain" />
                    )}
                    <span>{group.loan_team}</span>
                  </div>
                )}
              </div>
            </div>

            {/* Commentaries */}
            <div className="p-3 sm:p-4 space-y-3 bg-violet-50/30">
              {group.commentaries.map(c => (
                <CommentaryCard
                  key={c.id}
                  commentary={c}
                  variant="compact"
                  showTypeLabel={false}
                  onSubscribe={onSubscribe}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

/**
 * NewsletterWriterOverlay - Main component that integrates writer content
 * into a newsletter view
 */
export function NewsletterWriterOverlay({
  newsletterId,
  className
}) {
  const navigate = useNavigate()
  const {
    loading,
    writers,
    commentaries,
    activeWriterIds,
    isPreviewMode,
    toggleWriter
  } = useNewsletterWriters(newsletterId)

  const handleSubscribe = useCallback((writerId) => {
    navigate(`/journalists/${writerId}`)
  }, [navigate])

  // Show loading indicator
  if (loading && writers.length === 0) {
    return (
      <div className={cn('p-4 rounded-lg border bg-slate-50 animate-pulse', className)}>
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 rounded-full bg-slate-200" />
          <div className="space-y-2">
            <div className="h-4 w-32 bg-slate-200 rounded" />
            <div className="h-3 w-48 bg-slate-200 rounded" />
          </div>
        </div>
      </div>
    )
  }

  // Don't render anything if no writers available
  if (writers.length === 0) return null

  // Combine intro and summary for the header section
  const headerCommentaries = [...commentaries.intro, ...commentaries.summary]

  return (
    <div className={cn('space-y-4', className)}>
      {/* Writer discovery/toggle bar */}
      <WriterDiscoveryBar
        writers={writers}
        activeWriterIds={activeWriterIds}
        onToggleWriter={toggleWriter}
        onSubscribe={handleSubscribe}
        isPreviewMode={isPreviewMode}
      />

      {/* Summary/Intro commentaries - shown after agent summary */}
      {headerCommentaries.length > 0 && (
        <WriterSummarySection
          commentaries={headerCommentaries}
          onSubscribe={handleSubscribe}
        />
      )}

      {/* Player commentaries are rendered inline within player cards, not here */}
    </div>
  )
}

/**
 * Get player commentaries for use in player sections
 */
export function getPlayerCommentaries(commentaries, playerId) {
  if (!commentaries?.player || !playerId) return []

  const playerData = commentaries.player[playerId] || commentaries.player[String(playerId)]
  return playerData?.commentaries || []
}

/**
 * InlinePlayerWriteups - Renders writer commentaries inline within a player card
 * Use this inside player cards to show writeups for that specific player
 */
export function InlinePlayerWriteups({
  playerId,
  playerName,
  className
}) {
  const navigate = useNavigate()
  const { commentaries, activeWriterIds } = useWriterCommentaries()

  const handleSubscribe = useCallback((writerId) => {
    navigate(`/journalists/${writerId}`)
  }, [navigate])

  // Get commentaries for this player
  const playerCommentaries = useMemo(() => {
    if (!commentaries?.player || !playerId) return []
    const playerData = commentaries.player[playerId] || commentaries.player[String(playerId)]
    return playerData?.commentaries || []
  }, [commentaries, playerId])

  // Only show if there are active writers and commentaries
  if (activeWriterIds.size === 0 || playerCommentaries.length === 0) {
    return null
  }

  return (
    <div className={cn('mt-4 pt-4 border-t border-violet-100', className)}>
      <div className="flex items-center gap-2 mb-3 text-xs font-semibold text-violet-700 uppercase tracking-wide">
        <PenLine className="h-3.5 w-3.5" />
        <span>Expert Analysis</span>
        <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
          {playerCommentaries.length}
        </Badge>
      </div>

      <div className="space-y-3">
        {playerCommentaries.map(c => (
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
  )
}

/**
 * NewsletterWriterProvider - Wraps a newsletter to provide writer data context
 */
export function NewsletterWriterProvider({
  newsletterId,
  children
}) {
  const {
    loading,
    writers,
    commentaries,
    activeWriterIds,
    isPreviewMode,
    toggleWriter
  } = useNewsletterWriters(newsletterId)

  const contextValue = useMemo(() => ({
    loading,
    writers,
    commentaries,
    activeWriterIds,
    isPreviewMode,
    toggleWriter
  }), [loading, writers, commentaries, activeWriterIds, isPreviewMode, toggleWriter])

  return (
    <WriterCommentaryContext.Provider value={contextValue}>
      {children}
    </WriterCommentaryContext.Provider>
  )
}

/**
 * WriterHeaderSection - Just the writer bar and summary, for use within provider
 */
export function WriterHeaderSection({ className }) {
  const navigate = useNavigate()
  const { loading, writers, commentaries, activeWriterIds, isPreviewMode, toggleWriter } = useWriterCommentaries()

  const handleSubscribe = useCallback((writerId) => {
    navigate(`/journalists/${writerId}`)
  }, [navigate])

  // Show loading indicator
  if (loading && writers.length === 0) {
    return (
      <div className={cn('p-4 rounded-lg border bg-slate-50 animate-pulse', className)}>
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 rounded-full bg-slate-200" />
          <div className="space-y-2">
            <div className="h-4 w-32 bg-slate-200 rounded" />
            <div className="h-3 w-48 bg-slate-200 rounded" />
          </div>
        </div>
      </div>
    )
  }

  // Don't render anything if no writers available
  if (writers.length === 0) return null

  // Combine intro and summary for the header section
  const headerCommentaries = [...(commentaries.intro || []), ...(commentaries.summary || [])]

  return (
    <div className={cn('space-y-4', className)}>
      {/* Writer discovery/toggle bar */}
      <WriterDiscoveryBar
        writers={writers}
        activeWriterIds={activeWriterIds}
        onToggleWriter={toggleWriter}
        onSubscribe={handleSubscribe}
        isPreviewMode={isPreviewMode}
      />

      {/* Summary/Intro commentaries - shown after agent summary */}
      {headerCommentaries.length > 0 && (
        <WriterSummarySection
          commentaries={headerCommentaries}
          onSubscribe={handleSubscribe}
        />
      )}
    </div>
  )
}

/**
 * PlayerWriteupsSection - Renders ALL player commentaries in a dedicated section
 * Use this when the newsletter uses pre-rendered HTML and can't embed inline writeups
 */
export function PlayerWriteupsSection({ className }) {
  const navigate = useNavigate()
  const { commentaries, activeWriterIds, writers } = useWriterCommentaries()

  const handleSubscribe = useCallback((writerId) => {
    navigate(`/journalists/${writerId}`)
  }, [navigate])

  // Get all player commentaries
  const playerCommentaryEntries = useMemo(() => {
    if (!commentaries?.player || activeWriterIds.size === 0) return []
    return Object.entries(commentaries.player)
  }, [commentaries, activeWriterIds])

  if (playerCommentaryEntries.length === 0 || activeWriterIds.size === 0) {
    return null
  }

  return (
    <div className={cn('mt-8 space-y-4 border-t pt-8', className)}>
      <h3 className="text-xl font-bold text-foreground flex items-center gap-2">
        <Sparkles className="h-5 w-5 text-violet-500" />
        Expert Player Analysis
      </h3>
      <div className="grid gap-6">
        {playerCommentaryEntries.map(([playerId, playerData]) => {
          // playerData structure: { player_info: {...}, commentaries: [...] }
          const commentaries = playerData?.commentaries || []
          const playerInfo = playerData?.player_info || {}

          if (commentaries.length === 0) return null

          return (
            <div key={playerId} className="space-y-3">
              {/* Player header if available */}
              {playerInfo.name && (
                <div className="flex items-center gap-3 mb-2">
                  {playerInfo.photo && (
                    <img
                      src={playerInfo.photo}
                      alt={playerInfo.name}
                      className="h-10 w-10 rounded-full object-cover border-2 border-white shadow"
                    />
                  )}
                  <div>
                    <span className="font-semibold text-foreground">{playerInfo.name}</span>
                    {playerInfo.loan_team && (
                      <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
                        {playerInfo.loan_team_logo && (
                          <img src={playerInfo.loan_team_logo} alt="" className="h-4 w-4 object-contain" />
                        )}
                        <span>{playerInfo.loan_team}</span>
                      </div>
                    )}
                  </div>
                </div>
              )}
              {commentaries.map((commentary, idx) => (
                <CommentaryCard
                  key={commentary.id || idx}
                  commentary={commentary}
                  onSubscribe={handleSubscribe}
                  showPlayerContext={!playerInfo.name}
                />
              ))}
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default NewsletterWriterOverlay

