import { Link } from 'react-router-dom'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar'
import { ChevronRight } from 'lucide-react'

function MiniJourneyTrail({ journeyPath, highlightClubId }) {
    if (!journeyPath?.length) return null

    return (
        <div className="flex items-center gap-0.5 flex-wrap mt-1">
            {journeyPath.map((stop, i) => {
                const isHighlighted = stop.club_api_id === highlightClubId
                return (
                    <span key={`${stop.club_api_id}-${i}`} className="flex items-center gap-0.5">
                        {i > 0 && <span className="text-[10px] text-slate-500 mx-0.5">&rarr;</span>}
                        <img
                            src={stop.club_logo}
                            alt={stop.club_name}
                            title={stop.club_name}
                            className={`w-5 h-5 object-contain rounded-full ${isHighlighted ? 'ring-2 ring-amber-400 ring-offset-1 ring-offset-slate-900' : ''}`}
                            onError={e => { e.target.style.display = 'none' }}
                        />
                    </span>
                )
            })}
        </div>
    )
}

export function PlayerCard({ player, highlightClubId, showJourneyTrail = true, showStats = true }) {
    const initials = (player.player_name || '')
        .split(' ')
        .map(n => n[0])
        .join('')
        .slice(0, 2)
        .toUpperCase()

    return (
        <Link
            to={`/players/${player.player_api_id}`}
            className="flex items-center gap-3 py-2.5 px-3 rounded-lg hover:bg-slate-700/50 transition-colors group"
        >
            <Avatar className="h-8 w-8 shrink-0">
                <AvatarImage src={player.player_photo} alt={player.player_name} />
                <AvatarFallback className="text-[10px] bg-slate-700 text-slate-300">
                    {initials}
                </AvatarFallback>
            </Avatar>
            <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-slate-100 group-hover:text-amber-400 transition-colors truncate">
                    {player.player_name}
                </div>
                {player.current_club_name && (
                    <div className="text-xs text-slate-400 truncate">
                        {player.status === 'on_loan' ? 'at ' : ''}{player.current_club_name}
                    </div>
                )}
                {showJourneyTrail && (
                    <MiniJourneyTrail
                        journeyPath={player.journey_path}
                        highlightClubId={highlightClubId}
                    />
                )}
            </div>
            {showStats && (
                <div className="text-xs text-slate-400 shrink-0">
                    {player.total_appearances > 0 && (
                        <span>{player.total_appearances} apps</span>
                    )}
                </div>
            )}
            <ChevronRight className="h-4 w-4 text-slate-600 group-hover:text-amber-400 shrink-0" />
        </Link>
    )
}

export default PlayerCard
