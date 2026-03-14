import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { STATUS_COLORS, getStatusLabel } from './constellation-utils'

function StatusCard({ status, count, isActive, onClick, label }) {
    const color = STATUS_COLORS[status] || '#6b7280'

    return (
        <button
            onClick={onClick}
            className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-sm font-medium transition-colors ${
                isActive
                    ? 'bg-slate-800 text-white border-slate-600'
                    : 'bg-card border-border text-foreground/80 hover:bg-secondary'
            }`}
        >
            <span
                className="w-2.5 h-2.5 rounded-full shrink-0"
                style={{ backgroundColor: color }}
            />
            {label} ({count})
        </button>
    )
}

export function ConstellationSummary({ data, parentTeamName }) {
    const [expandedStatus, setExpandedStatus] = useState(null)

    if (!data?.all_players?.length) return null

    const summary = data.summary || {}
    const statusOrder = ['first_team', 'on_loan', 'academy', 'released', 'sold']
    const activeStatuses = statusOrder.filter(s => summary[s] > 0)

    // Group players by status
    const playersByStatus = {}
    for (const player of data.all_players) {
        const s = player.status || 'unknown'
        if (!playersByStatus[s]) playersByStatus[s] = []
        playersByStatus[s].push(player)
    }

    const toggleStatus = (status) => {
        setExpandedStatus(prev => prev === status ? null : status)
    }

    return (
        <div className="space-y-4">
            {/* Status summary chips */}
            <div className="flex flex-wrap gap-2">
                {activeStatuses.map(status => (
                    <StatusCard
                        key={status}
                        status={status}
                        label={getStatusLabel(status, parentTeamName)}
                        count={summary[status]}
                        isActive={expandedStatus === status}
                        onClick={() => toggleStatus(status)}
                    />
                ))}
                {/* Show any extra statuses not in the standard order */}
                {Object.entries(summary)
                    .filter(([s]) => !statusOrder.includes(s) && summary[s] > 0)
                    .map(([status, count]) => (
                        <StatusCard
                            key={status}
                            status={status}
                            label={getStatusLabel(status, parentTeamName)}
                            count={count}
                            isActive={expandedStatus === status}
                            onClick={() => toggleStatus(status)}
                        />
                    ))
                }
            </div>

            {/* Expandable player list */}
            {expandedStatus && playersByStatus[expandedStatus] && (
                <div className="bg-card rounded-lg border border-border divide-y divide-border">
                    {playersByStatus[expandedStatus].map((player) => (
                        <Link
                            key={player.player_api_id}
                            to={`/players/${player.player_api_id}`}
                            className="flex items-center gap-3 px-4 py-3 hover:bg-secondary transition-colors group"
                        >
                            {player.player_photo ? (
                                <img
                                    src={player.player_photo}
                                    alt=""
                                    className="w-8 h-8 rounded-full object-cover shrink-0"
                                />
                            ) : (
                                <div className="w-8 h-8 rounded-full bg-muted flex items-center justify-center text-xs font-medium text-muted-foreground shrink-0">
                                    {player.player_name?.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()}
                                </div>
                            )}
                            <div className="flex-1 min-w-0">
                                <div className="text-sm font-medium text-foreground group-hover:text-primary transition-colors truncate">
                                    {player.player_name}
                                </div>
                                {player.current_club_name && (
                                    <div className="text-xs text-muted-foreground truncate">
                                        {player.status === 'on_loan' ? 'at ' : ''}{player.current_club_name}
                                    </div>
                                )}
                            </div>
                            <div className="flex items-center gap-2 text-xs text-muted-foreground shrink-0">
                                {expandedStatus === 'first_team' ? (
                                    player.parent_club_appearances > 0 && (
                                        <span>{player.parent_club_appearances} apps</span>
                                    )
                                ) : (
                                    player.total_appearances > 0 && (
                                        <span>{player.total_appearances} apps</span>
                                    )
                                )}
                            </div>
                            <ChevronRight className="h-4 w-4 text-muted-foreground/70 group-hover:text-primary shrink-0" />
                        </Link>
                    ))}
                </div>
            )}

            {/* Full player list when no status is expanded */}
            {!expandedStatus && (
                <div className="text-xs text-muted-foreground/70 text-center py-2">
                    Click a status above to see players
                </div>
            )}
        </div>
    )
}

export default ConstellationSummary
