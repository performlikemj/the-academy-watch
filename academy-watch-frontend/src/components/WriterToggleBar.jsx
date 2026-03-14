import React from 'react'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar.jsx'
import { Badge } from '@/components/ui/badge.jsx'
import { Lock, Check } from 'lucide-react'
import { cn } from '@/lib/utils'

const JOURNALIST_COLORS = [
  { ring: 'ring-violet-500', bg: 'bg-violet-500', bgLight: 'bg-violet-100', text: 'text-violet-700' },
  { ring: 'ring-amber-500', bg: 'bg-amber-500', bgLight: 'bg-amber-100', text: 'text-amber-700' },
  { ring: 'ring-emerald-500', bg: 'bg-emerald-500', bgLight: 'bg-emerald-100', text: 'text-emerald-700' },
  { ring: 'ring-rose-500', bg: 'bg-rose-500', bgLight: 'bg-rose-100', text: 'text-rose-700' },
  { ring: 'ring-cyan-500', bg: 'bg-cyan-500', bgLight: 'bg-cyan-100', text: 'text-cyan-700' },
  { ring: 'ring-orange-500', bg: 'bg-orange-500', bgLight: 'bg-orange-100', text: 'text-orange-700' },
]

export function WriterToggleBar({
  journalists = [],
  activeIds = new Set(),
  onToggle,
  onSubscribe,
  className,
}) {
  if (!journalists || journalists.length === 0) {
    return null
  }

  return (
    <div className={cn(
      'sticky top-0 z-30 bg-card border-b border-border shadow-sm',
      className
    )}>
      <div className="max-w-3xl mx-auto px-4 py-3">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Writers for this week
          </span>
          <Badge variant="secondary" className="text-xs px-1.5 py-0">
            {journalists.length}
          </Badge>
        </div>
        
        <div className="flex gap-2 overflow-x-auto pb-1 -mx-1 px-1 scrollbar-hide">
          {journalists.map((journalist, index) => {
            const isActive = activeIds.has(journalist.id)
            const isSubscribed = journalist.is_subscribed
            const canView = isSubscribed || journalist.has_public
            const colors = JOURNALIST_COLORS[index % JOURNALIST_COLORS.length]
            
            return (
              <button
                key={journalist.id}
                onClick={() => {
                  if (canView) {
                    onToggle?.(journalist.id)
                  } else if (onSubscribe) {
                    onSubscribe(journalist.id)
                  }
                }}
                className={cn(
                  'flex items-center gap-2 px-3 py-2 rounded-full transition-all duration-200',
                  'border-2 whitespace-nowrap flex-shrink-0',
                  'active:scale-95',
                  isActive 
                    ? cn('border-transparent shadow-md', colors.bg, 'text-white')
                    : canView
                      ? 'border-border bg-card hover:border-border hover:bg-secondary text-foreground/80'
                      : 'border-border bg-secondary text-muted-foreground/70',
                  isActive && 'ring-2 ring-offset-1',
                  isActive && colors.ring
                )}
              >
                <Avatar className={cn(
                  'h-6 w-6 border-2 flex-shrink-0',
                  isActive ? 'border-white/30' : 'border-secondary'
                )}>
                  {journalist.profile_image_url ? (
                    <AvatarImage src={journalist.profile_image_url} alt={journalist.display_name} />
                  ) : null}
                  <AvatarFallback className={cn(
                    'text-[10px] font-semibold',
                    isActive ? 'bg-white/20 text-white' : cn(colors.bgLight, colors.text)
                  )}>
                    {(journalist.display_name || 'W').substring(0, 2).toUpperCase()}
                  </AvatarFallback>
                </Avatar>
                
                <span className={cn(
                  'text-sm font-medium max-w-[100px] truncate',
                  isActive ? 'text-white' : ''
                )}>
                  {journalist.display_name}
                </span>
                
                {/* Writeup count */}
                <Badge 
                  variant={isActive ? 'secondary' : 'outline'}
                  className={cn(
                    'text-[10px] px-1.5 py-0 min-w-[18px] justify-center',
                    isActive 
                      ? 'bg-white/20 text-white border-transparent' 
                      : 'border-border text-muted-foreground'
                  )}
                >
                  {journalist.writeup_count}
                </Badge>
                
                {/* Status icon */}
                {isActive ? (
                  <Check className="h-3.5 w-3.5 flex-shrink-0" />
                ) : !canView ? (
                  <Lock className="h-3 w-3 flex-shrink-0 text-muted-foreground/70" />
                ) : null}
              </button>
            )
          })}
        </div>
        
        <p className="text-[11px] text-muted-foreground/70 mt-2 leading-tight">
          Toggle writers to show their analysis with each player
        </p>
      </div>
    </div>
  )
}

export default WriterToggleBar
