import { Link } from 'react-router-dom'
import { X } from 'lucide-react'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar'
import { Card, CardContent } from '@/components/ui/card'

function MiniJourneyTrail({ journeyPath, selectedClubApiId }) {
    if (!journeyPath?.length) return null

    return (
        <div className="flex items-center gap-0.5 flex-wrap mt-1">
            {journeyPath.map((stop, i) => {
                const isSelected = stop.club_api_id === selectedClubApiId
                return (
                    <span key={`${stop.club_api_id}-${i}`} className="flex items-center gap-0.5">
                        {i > 0 && <span className="text-[10px] text-muted-foreground/70 mx-0.5">&rarr;</span>}
                        <img
                            src={stop.club_logo}
                            alt={stop.club_name}
                            title={stop.club_name}
                            className={`w-5 h-5 object-contain rounded-full ${isSelected ? 'ring-2 ring-ring ring-offset-1' : ''}`}
                            onError={e => { e.target.style.display = 'none' }}
                        />
                    </span>
                )
            })}
        </div>
    )
}

export function NodeDetailPanel({ node, allPlayers, onClose }) {
    if (!node) return null

    // Filter players whose journey_path includes this club
    const clubApiId = node.club_api_id
    const playersAtNode = allPlayers.filter(p =>
        p.journey_path?.some(stop => stop.club_api_id === clubApiId)
    )

    return (
        <Card className="border-slate-200">
            <CardContent className="p-4">
                {/* Header */}
                <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                        {node.club_logo && (
                            <img
                                src={node.club_logo}
                                alt={node.club_name}
                                className="w-6 h-6 object-contain"
                            />
                        )}
                        <div>
                            <h4 className="text-sm font-semibold text-foreground">{node.club_name}</h4>
                            <p className="text-xs text-muted-foreground">
                                {playersAtNode.length} player{playersAtNode.length !== 1 ? 's' : ''}
                            </p>
                        </div>
                    </div>
                    <button
                        onClick={onClose}
                        className="text-muted-foreground/70 hover:text-muted-foreground p-1 rounded"
                    >
                        <X className="h-4 w-4" />
                    </button>
                </div>

                {/* Player list */}
                {playersAtNode.length === 0 ? (
                    <p className="text-xs text-muted-foreground/70">No player journey data available.</p>
                ) : (
                    <div className="space-y-2 max-h-64 overflow-y-auto">
                        {playersAtNode.map(player => (
                            <div key={player.player_api_id} className="flex items-start gap-2">
                                <Avatar className="h-7 w-7 mt-0.5 shrink-0">
                                    <AvatarImage src={player.player_photo} alt={player.player_name} />
                                    <AvatarFallback className="text-[10px]">
                                        {player.player_name?.split(' ').map(w => w[0]).join('').slice(0, 2)}
                                    </AvatarFallback>
                                </Avatar>
                                <div className="min-w-0 flex-1">
                                    <Link
                                        to={`/players/${player.player_api_id}`}
                                        className="text-sm font-medium text-primary hover:text-primary/90 hover:underline leading-tight block truncate"
                                    >
                                        {player.player_name}
                                    </Link>
                                    <MiniJourneyTrail
                                        journeyPath={player.journey_path}
                                        selectedClubApiId={clubApiId}
                                    />
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </CardContent>
        </Card>
    )
}

export default NodeDetailPanel
