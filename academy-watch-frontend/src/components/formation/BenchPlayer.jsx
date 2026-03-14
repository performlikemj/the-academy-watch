import { Link } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar'

export function BenchPlayer({ player }) {
  const name = player.player_name || player.name || 'Unknown'
  const surname = name.split(' ').pop()
  const stat = player.appearances != null
    ? `${player.appearances} apps${player.goals ? `, ${player.goals}g` : ''}`
    : ''

  return (
    <div
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData('application/json', JSON.stringify({
          source: 'bench',
          player_id: player.player_id || player.id,
          player_name: name,
        }))
        e.dataTransfer.effectAllowed = 'move'
      }}
      className="flex items-center gap-2 px-2 py-1.5 rounded-md border bg-card hover:bg-accent cursor-grab active:cursor-grabbing select-none"
    >
      <Avatar className="h-7 w-7 shrink-0">
        <AvatarImage src={player.photo_url || player.photo} alt={name} />
        <AvatarFallback className="text-[10px]">{surname.slice(0, 2).toUpperCase()}</AvatarFallback>
      </Avatar>
      <div className="flex-1 min-w-0">
        <Link
          to={`/players/${player.player_id || player.id}`}
          className="text-xs font-medium truncate block hover:text-primary hover:underline transition-colors"
          draggable={false}
          onClick={(e) => e.stopPropagation()}
        >
          {name}
        </Link>
        {player.loan_team_name && (
          <p className="text-[10px] text-muted-foreground truncate">{player.loan_team_name}</p>
        )}
      </div>
      <div className="flex items-center gap-1 shrink-0">
        {player.position && (
          <Badge variant="secondary" className="text-[10px] px-1 py-0">{player.position}</Badge>
        )}
        {stat && (
          <span className="text-[10px] text-muted-foreground whitespace-nowrap">{stat}</span>
        )}
      </div>
    </div>
  )
}
