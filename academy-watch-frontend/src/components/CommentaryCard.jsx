import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { Card, CardContent, CardHeader } from '@/components/ui/card.jsx'
import { Button } from '@/components/ui/button.jsx'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar.jsx'
import { Badge } from '@/components/ui/badge.jsx'
import { Lock, Sparkles, ExternalLink } from 'lucide-react'
import ClapIcon from '@/components/ClapIcon.jsx'
import { BlockRenderer } from '@/components/BlockRenderer'
import { cn } from '@/lib/utils'
import { formatTextToHtml } from '@/lib/formatText'
import { APIService } from '@/lib/api'

// Color palette for different journalists
const JOURNALIST_COLORS = [
  { border: 'border-l-violet-500', bg: 'bg-violet-50/80', accent: 'text-violet-700', gradient: 'from-violet-500/5' },
  { border: 'border-l-amber-500', bg: 'bg-amber-50/80', accent: 'text-amber-700', gradient: 'from-amber-500/5' },
  { border: 'border-l-emerald-500', bg: 'bg-emerald-50/80', accent: 'text-emerald-700', gradient: 'from-emerald-500/5' },
  { border: 'border-l-rose-500', bg: 'bg-rose-50/80', accent: 'text-rose-700', gradient: 'from-rose-500/5' },
  { border: 'border-l-cyan-500', bg: 'bg-cyan-50/80', accent: 'text-cyan-700', gradient: 'from-cyan-500/5' },
  { border: 'border-l-orange-500', bg: 'bg-orange-50/80', accent: 'text-orange-700', gradient: 'from-orange-500/5' },
]

const TYPE_LABELS = {
  intro: 'Opening Thoughts',
  player: 'Player Analysis',
  summary: 'Week Summary',
}

export function CommentaryCard({
  commentary,
  variant = 'default', // 'default' | 'compact'
  showTypeLabel = true,
  onSubscribe,
  className,
}) {
  const [applauseCount, setApplauseCount] = useState(commentary?.applause_count || 0)
  const [hasApplauded, setHasApplauded] = useState(false)
  const [applauding, setApplauding] = useState(false)

  if (!commentary) return null

  const colorIndex = commentary.author_color_index ?? 0
  const colors = JOURNALIST_COLORS[colorIndex % JOURNALIST_COLORS.length]
  const isLocked = commentary.is_locked
  const typeLabel = TYPE_LABELS[commentary.commentary_type] || 'Analysis'
  const isCompact = variant === 'compact'

  // Determine display name and photo (contributor takes precedence if present)
  const hasContributor = !!commentary.contributor_id
  const displayName = hasContributor ? commentary.contributor_name : commentary.author_name
  const displayPhoto = hasContributor ? commentary.contributor_photo_url : commentary.author_profile_image

  const handleApplause = async () => {
    if (applauding || hasApplauded) return
    setApplauding(true)
    try {
      setApplauseCount(prev => prev + 1)
      setHasApplauded(true)
      await APIService.applaudCommentary(commentary.id)
    } catch {
      setApplauseCount(prev => prev - 1)
      setHasApplauded(false)
    } finally {
      setApplauding(false)
    }
  }

  const handleSubscribeClick = () => {
    if (onSubscribe && commentary.author_id) {
      onSubscribe(commentary.author_id)
    }
  }

  return (
    <div 
      className={cn(
        'relative overflow-hidden transition-all duration-200',
        'border-l-4 rounded-lg',
        colors.border,
        colors.bg,
        isCompact ? 'p-3' : 'p-4 sm:p-5',
        className
      )}
    >
      {/* Header */}
      <div className={cn(
        'flex items-start gap-2 sm:gap-3',
        isCompact ? 'mb-2' : 'mb-3'
      )}>
        <Avatar className={cn(
          'border-2 border-white shadow-sm flex-shrink-0',
          isCompact ? 'h-8 w-8' : 'h-9 w-9 sm:h-10 sm:w-10'
        )}>
          {displayPhoto ? (
            <AvatarImage src={displayPhoto} alt={displayName} />
          ) : null}
          <AvatarFallback className={cn('font-medium text-xs', colors.accent, 'bg-white')}>
            {(displayName || 'A').substring(0, 2).toUpperCase()}
          </AvatarFallback>
        </Avatar>

        <div className="flex-1 min-w-0">
          <div className="flex items-center flex-wrap gap-x-2 gap-y-1">
            <span className={cn(
              'font-semibold text-foreground truncate',
              isCompact ? 'text-sm' : 'text-sm sm:text-base'
            )}>
              {displayName}
            </span>
            {hasContributor && commentary.author_name && (
              <span className="text-xs text-muted-foreground">
                via {commentary.author_name}
              </span>
            )}
            {commentary.is_premium && (
              <Badge variant="outline" className="text-[10px] border-amber-300 text-amber-700 bg-amber-50/50 px-1.5 py-0">
                <Sparkles className="h-2.5 w-2.5 mr-0.5" />
                Premium
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            {showTypeLabel && (
              <span className={cn('font-medium uppercase tracking-wide', colors.accent)}>
                {typeLabel}
              </span>
            )}
            {commentary.created_at && (
              <>
                {showTypeLabel && <span>·</span>}
                <span>
                  {new Date(commentary.created_at).toLocaleDateString(undefined, {
                    month: 'short',
                    day: 'numeric',
                  })}
                </span>
              </>
            )}
          </div>
        </div>
      </div>
      
      {/* Title if present */}
      {commentary.title && (
        <h4 className={cn(
          'font-bold text-foreground leading-tight mb-2',
          isCompact ? 'text-base' : 'text-base sm:text-lg'
        )}>
          {commentary.title}
        </h4>
      )}
      
      {/* Content - supports both structured blocks and legacy HTML */}
      {commentary.structured_blocks && commentary.structured_blocks.length > 0 ? (
        // New block-based content
        <>
          <BlockRenderer
            blocks={commentary.structured_blocks}
            isSubscribed={!isLocked}
            playerId={commentary.player_id}
            weekRange={{
              start: commentary.week_start_date,
              end: commentary.week_end_date,
            }}
            authorName={commentary.author_name}
            authorId={commentary.author_id}
            onSubscribe={handleSubscribeClick}
            className={isCompact ? 'text-sm' : ''}
          />
          
          {/* Footer */}
          {!isLocked && (
            <div className={cn(
              'flex items-center justify-between border-t border-border',
              isCompact ? 'mt-2 pt-2' : 'mt-3 pt-3'
            )}>
              <button
                onClick={handleApplause}
                disabled={applauding || hasApplauded}
                className={cn(
                  'flex items-center gap-1.5 text-xs transition-all',
                  hasApplauded 
                    ? 'text-violet-600' 
                    : 'text-muted-foreground hover:text-violet-600'
                )}
              >
                <ClapIcon className={cn(
                  'h-3.5 w-3.5 transition-transform',
                  hasApplauded && 'scale-110'
                )} />
                <span>{applauseCount > 0 ? applauseCount : 'Applaud'}</span>
              </button>
              
              {commentary.id && (
                <Link
                  to={`/writeups/${commentary.id}`}
                  className={cn(
                    'flex items-center gap-1 text-xs font-medium transition-colors',
                    colors.accent,
                    'hover:underline'
                  )}
                >
                  <span>Full analysis</span>
                  <ExternalLink className="h-3 w-3" />
                </Link>
              )}
            </div>
          )}
        </>
      ) : isLocked ? (
        // Legacy locked content
        <div className="relative">
          <div 
            className="text-muted-foreground text-sm leading-relaxed blur-[2px] select-none line-clamp-2"
            dangerouslySetInnerHTML={{ __html: formatTextToHtml(commentary.content) }}
          />
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-gradient-to-t from-card/95 via-card/80 to-transparent pt-4">
            <Lock className="h-5 w-5 text-muted-foreground/70 mb-2" />
            <p className="text-xs text-muted-foreground mb-2 text-center px-4">
              Subscribe to unlock
            </p>
            <Button 
              size="sm" 
              onClick={handleSubscribeClick}
              className="bg-foreground hover:bg-foreground/90 text-background rounded-full px-4 h-8 text-xs"
            >
              Subscribe
            </Button>
          </div>
        </div>
      ) : (
        // Legacy unlocked content
        <>
          <div 
            className={cn(
              'prose prose-sm max-w-none text-foreground/80',
              'prose-p:my-2 prose-ul:my-2 prose-ol:my-2 prose-li:my-1',
              'prose-ul:pl-5 prose-ol:pl-5',
              'prose-headings:text-foreground prose-headings:font-semibold',
              'prose-strong:text-foreground prose-a:text-violet-600 text-foreground/80',
              isCompact ? 'text-sm leading-relaxed' : 'text-sm sm:text-base leading-relaxed'
            )}
            dangerouslySetInnerHTML={{ __html: formatTextToHtml(commentary.content) }}
          />
          
          {/* Footer */}
          <div className={cn(
            'flex items-center justify-between border-t border-border',
            isCompact ? 'mt-2 pt-2' : 'mt-3 pt-3'
          )}>
            <button
              onClick={handleApplause}
              disabled={applauding || hasApplauded}
              className={cn(
                'flex items-center gap-1.5 text-xs transition-all',
                hasApplauded 
                  ? 'text-violet-600' 
                  : 'text-muted-foreground hover:text-violet-600'
              )}
            >
              <ClapIcon className={cn(
                'h-3.5 w-3.5 transition-transform',
                hasApplauded && 'scale-110'
              )} />
              <span>{applauseCount > 0 ? applauseCount : 'Applaud'}</span>
            </button>
            
            {commentary.id && (
              <Link
                to={`/writeups/${commentary.id}`}
                className={cn(
                  'flex items-center gap-1 text-xs font-medium transition-colors',
                  colors.accent,
                  'hover:underline'
                )}
              >
                <span>Full analysis</span>
                <ExternalLink className="h-3 w-3" />
              </Link>
            )}
          </div>
        </>
      )}
    </div>
  )
}

export default CommentaryCard
