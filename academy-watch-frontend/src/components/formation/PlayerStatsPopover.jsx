import { Link } from 'react-router-dom'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { X, ExternalLink } from 'lucide-react'

export function PlayerStatsPopover({ player, slotLabel, onClose, onRemove }) {
  if (!player) return null

  const name = player.player_name || player.name || 'Unknown'
  const stats = [
    { label: 'Appearances', value: player.appearances },
    { label: 'Goals', value: player.goals },
    { label: 'Assists', value: player.assists },
    { label: 'Minutes', value: player.minutes_played },
    { label: 'Yellow Cards', value: player.yellows },
    { label: 'Red Cards', value: player.reds },
  ].filter((s) => s.value != null && s.value > 0)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={onClose}>
      <div
        className="bg-card border rounded-xl shadow-2xl w-[320px] overflow-hidden animate-in fade-in zoom-in-95 duration-150"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="bg-gradient-to-r from-green-800 to-green-600 p-4 flex items-center gap-3">
          <Avatar className="h-14 w-14 border-2 border-white shadow-lg">
            <AvatarImage src={player.photo_url || player.photo} alt={name} />
            <AvatarFallback className="text-lg bg-white text-foreground/80 font-bold">
              {name.split(' ').pop().slice(0, 2).toUpperCase()}
            </AvatarFallback>
          </Avatar>
          <div className="flex-1 min-w-0">
            <p className="font-bold text-white text-sm truncate">{name}</p>
            {player.loan_team_name && (
              <p className="text-green-100 text-xs truncate">Currently at {player.loan_team_name}</p>
            )}
            <div className="flex items-center gap-1.5 mt-1">
              {player.position && (
                <Badge variant="secondary" className="text-[10px] px-1.5 py-0 bg-white/20 text-white border-0">
                  {player.position}
                </Badge>
              )}
              {slotLabel && (
                <Badge className="text-[10px] px-1.5 py-0 bg-white/30 text-white border-0">
                  Playing: {slotLabel}
                </Badge>
              )}
            </div>
          </div>
          <button onClick={onClose} className="text-white/70 hover:text-white shrink-0">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Stats grid */}
        <div className="p-4">
          {stats.length > 0 ? (
            <div className="grid grid-cols-3 gap-3">
              {stats.map((s) => (
                <div key={s.label} className="text-center">
                  <p className="text-lg font-bold">{s.value}</p>
                  <p className="text-[10px] text-muted-foreground leading-tight">{s.label}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground text-center py-2">No stats available</p>
          )}
        </div>

        {/* Actions */}
        <div className="px-4 pb-4 space-y-2">
          {(player.player_id || player.id) && (
            <Button variant="default" size="sm" className="w-full text-xs" asChild>
              <Link to={`/players/${player.player_id || player.id}`}>
                View Profile <ExternalLink className="h-3 w-3 ml-1" />
              </Link>
            </Button>
          )}
          <Button variant="outline" size="sm" className="w-full text-xs" onClick={onRemove}>
            Remove from pitch
          </Button>
        </div>
      </div>
    </div>
  )
}
