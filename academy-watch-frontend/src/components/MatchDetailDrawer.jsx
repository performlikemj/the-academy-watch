import React from 'react'
import {
    Drawer,
    DrawerContent,
    DrawerHeader,
    DrawerTitle,
    DrawerDescription,
} from '@/components/ui/drawer'
import { Badge } from '@/components/ui/badge'
import { format } from 'date-fns'
import { Target, Shield, Footprints, Users, ArrowRight, Clock, Star, AlertCircle } from 'lucide-react'

/**
 * MatchDetailDrawer - Shows detailed stats for a single match
 * @param {boolean} open - Whether the drawer is open
 * @param {function} onOpenChange - Callback when open state changes
 * @param {object} match - The match stats object
 * @param {string} playerName - The player's name
 * @param {string} position - The player's position (Goalkeeper, Defender, Midfielder, Attacker)
 */
export function MatchDetailDrawer({ open, onOpenChange, match, playerName, position }) {
    if (!match) return null

    const isGoalkeeper = position === 'Goalkeeper'
    const rating = parseFloat(match.rating)
    const ratingColor = rating >= 7.5 ? 'text-emerald-600' : rating >= 6.0 ? 'text-foreground/80' : 'text-rose-600'
    const ratingBg = rating >= 7.5 ? 'bg-emerald-100' : rating >= 6.0 ? 'bg-secondary' : 'bg-rose-50'

    // Calculate match result for the player's team
    const teamScore = match.is_home ? match.home_goals : match.away_goals
    const opponentScore = match.is_home ? match.away_goals : match.home_goals
    const hasScore = teamScore !== null && teamScore !== undefined && opponentScore !== null && opponentScore !== undefined
    const matchResult = hasScore
        ? teamScore > opponentScore ? 'W' : teamScore < opponentScore ? 'L' : 'D'
        : null
    const resultColor = matchResult === 'W' ? 'text-emerald-600 bg-emerald-50'
        : matchResult === 'L' ? 'text-rose-600 bg-rose-50'
        : 'text-amber-600 bg-amber-50'

    // Stat categories for display
    const attackingStats = [
        { label: 'Goals', value: match.goals, icon: '⚽', highlight: match.goals > 0 },
        { label: 'Assists', value: match.assists, icon: '🅰️', highlight: match.assists > 0 },
        { label: 'Shots', value: match.shots?.total, subValue: match.shots?.on ? `${match.shots.on} on target` : null },
        { label: 'Dribbles', value: match.dribbles?.success, subValue: match.dribbles?.attempts ? `of ${match.dribbles.attempts} attempted` : null },
        { label: 'Offsides', value: match.offsides },
    ].filter(s => s.value !== undefined && s.value !== null)

    const passingStats = [
        { label: 'Passes', value: match.passes?.total, subValue: match.passes?.accuracy },
        { label: 'Key Passes', value: match.passes?.key, highlight: (match.passes?.key || 0) >= 2 },
    ].filter(s => s.value !== undefined && s.value !== null)

    const defensiveStats = [
        { label: 'Tackles', value: match.tackles?.total },
        { label: 'Interceptions', value: match.tackles?.interceptions },
        { label: 'Blocks', value: match.tackles?.blocks },
        { label: 'Clearances', value: match.clearances },
    ].filter(s => s.value !== undefined && s.value !== null)

    const duelStats = [
        { label: 'Duels Won', value: match.duels?.won, subValue: match.duels?.total ? `of ${match.duels.total}` : null },
        { label: 'Dribbled Past', value: match.dribbles?.past },
        { label: 'Fouls Drawn', value: match.fouls?.drawn },
        { label: 'Fouls Committed', value: match.fouls?.committed },
    ].filter(s => s.value !== undefined && s.value !== null)

    const goalkeeperStats = [
        { label: 'Saves', value: match.saves, icon: '🧤', highlight: (match.saves || 0) >= 3 },
        { label: 'Goals Conceded', value: match.goals_conceded, icon: match.goals_conceded === 0 ? '✨' : '⚽' },
        { label: 'Clean Sheet', value: match.goals_conceded === 0 ? 'Yes' : 'No', isBoolean: true },
        { label: 'Penalty Saved', value: match.penalty?.saved, highlight: (match.penalty?.saved || 0) > 0 },
    ].filter(s => s.value !== undefined && s.value !== null)

    const penaltyStats = [
        { label: 'Penalties Won', value: match.penalty?.won },
        { label: 'Penalties Scored', value: match.penalty?.scored },
        { label: 'Penalties Missed', value: match.penalty?.missed },
        { label: 'Penalties Committed', value: match.penalty?.committed },
    ].filter(s => s.value !== undefined && s.value !== null && s.value > 0)

    const StatSection = ({ title, icon: Icon, stats }) => {
        if (stats.length === 0) return null
        return (
            <div className="mb-5">
                <div className="flex items-center gap-2 mb-3">
                    <Icon className="h-4 w-4 text-muted-foreground" />
                    <h3 className="font-semibold text-sm text-foreground/80">{title}</h3>
                </div>
                <div className="grid grid-cols-2 gap-3">
                    {stats.map((stat, idx) => (
                        <div 
                            key={idx} 
                            className={`p-3 rounded-lg ${stat.highlight ? 'bg-primary/5 border border-primary/20' : 'bg-secondary'}`}
                        >
                            <div className="text-xs text-muted-foreground mb-1">{stat.label}</div>
                            <div className={`text-lg font-bold ${stat.highlight ? 'text-primary' : 'text-foreground'}`}>
                                {stat.icon && <span className="mr-1">{stat.icon}</span>}
                                {stat.isBoolean ? stat.value : stat.value}
                            </div>
                            {stat.subValue && (
                                <div className="text-xs text-muted-foreground mt-0.5">{stat.subValue}</div>
                            )}
                        </div>
                    ))}
                </div>
            </div>
        )
    }

    return (
        <Drawer open={open} onOpenChange={onOpenChange}>
            <DrawerContent className="max-h-[90vh]">
                <DrawerHeader className="border-b pb-4">
                    {/* Match Header */}
                    <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-3">
                            {match.loan_team_logo && (
                                <img 
                                    src={match.loan_team_logo} 
                                    alt={match.loan_team_name} 
                                    className="w-10 h-10 rounded-full object-cover border-2 border-border"
                                />
                            )}
                            <div>
                                <DrawerTitle className="text-lg">
                                    {match.loan_team_name} vs {match.opponent}
                                </DrawerTitle>
                                <DrawerDescription className="flex items-center gap-2 mt-1">
                                    <span>{match.fixture_date ? format(new Date(match.fixture_date), 'EEEE, MMM d, yyyy') : 'Unknown date'}</span>
                                    <span className="text-muted-foreground/70">·</span>
                                    <span>{match.competition}</span>
                                </DrawerDescription>
                            </div>
                        </div>
                        {hasScore && (
                            <div className={`px-3 py-2 rounded-lg ${resultColor} text-center min-w-[70px]`}>
                                <div className="text-2xl font-bold">
                                    {teamScore} - {opponentScore}
                                </div>
                                <div className="text-xs font-medium">
                                    {match.is_home ? 'Home' : 'Away'}
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Player Summary Bar */}
                    <div className="flex items-center gap-4 p-3 bg-gradient-to-r from-stone-50 to-stone-100 rounded-lg">
                        <div className="flex items-center gap-2">
                            <Clock className="h-4 w-4 text-muted-foreground" />
                            <span className="font-semibold">{match.minutes}'</span>
                            <span className="text-muted-foreground text-sm">played</span>
                            {match.substitute && (
                                <Badge variant="outline" className="text-xs bg-orange-50 text-orange-600 border-orange-200 ml-1">
                                    Sub
                                </Badge>
                            )}
                        </div>
                        {match.captain && (
                            <Badge variant="outline" className="text-xs bg-amber-50 text-amber-700 border-amber-200">
                                Captain
                            </Badge>
                        )}
                        {match.rating && (
                            <div className={`flex items-center gap-1.5 px-3 py-1 rounded-full ${ratingBg}`}>
                                <Star className="h-4 w-4" style={{ color: rating >= 7.5 ? '#059669' : rating >= 6.0 ? '#57534e' : '#e11d48' }} />
                                <span className={`font-bold ${ratingColor}`}>{match.rating}</span>
                                <span className="text-muted-foreground text-xs">rating</span>
                            </div>
                        )}
                        {(match.yellows > 0 || match.reds > 0) && (
                            <div className="flex items-center gap-1">
                                {match.yellows > 0 && (
                                    <span className="w-4 h-5 bg-yellow-400 rounded-sm" title="Yellow Card" />
                                )}
                                {match.reds > 0 && (
                                    <span className="w-4 h-5 bg-red-600 rounded-sm" title="Red Card" />
                                )}
                            </div>
                        )}
                    </div>
                </DrawerHeader>

                {/* Stats Content */}
                <div className="p-4 overflow-y-auto max-h-[60vh]">
                    {/* Goals & Assists Highlight */}
                    {(match.goals > 0 || match.assists > 0) && (
                        <div className="mb-5 p-4 bg-gradient-to-r from-primary/5 to-primary/10 rounded-xl border border-primary/20">
                            <div className="flex items-center justify-center gap-6">
                                {match.goals > 0 && (
                                    <div className="text-center">
                                        <div className="text-3xl font-bold text-emerald-700">
                                            ⚽ {match.goals}
                                        </div>
                                        <div className="text-xs text-emerald-600 font-medium">
                                            {match.goals === 1 ? 'Goal' : 'Goals'}
                                        </div>
                                    </div>
                                )}
                                {match.goals > 0 && match.assists > 0 && (
                                    <div className="w-px h-10 bg-border" />
                                )}
                                {match.assists > 0 && (
                                    <div className="text-center">
                                        <div className="text-3xl font-bold text-amber-700">
                                            🅰️ {match.assists}
                                        </div>
                                        <div className="text-xs text-amber-600 font-medium">
                                            {match.assists === 1 ? 'Assist' : 'Assists'}
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    )}

                    {/* Goalkeeper-specific stats */}
                    {isGoalkeeper ? (
                        <>
                            <StatSection title="Goalkeeping" icon={Shield} stats={goalkeeperStats} />
                            <StatSection title="Distribution" icon={Footprints} stats={passingStats} />
                        </>
                    ) : (
                        <>
                            <StatSection title="Attacking" icon={Target} stats={attackingStats} />
                            <StatSection title="Passing" icon={ArrowRight} stats={passingStats} />
                            <StatSection title="Defensive" icon={Shield} stats={defensiveStats} />
                            <StatSection title="Duels & Fouls" icon={Users} stats={duelStats} />
                        </>
                    )}

                    {/* Penalty stats (for all players if any) */}
                    {penaltyStats.length > 0 && (
                        <StatSection title="Penalties" icon={AlertCircle} stats={penaltyStats} />
                    )}

                    {/* Loan window indicator */}
                    {match.loan_window && match.loan_window !== 'Summer' && (
                        <div className="mt-4 p-3 bg-orange-50 rounded-lg border border-orange-200">
                            <div className="flex items-center gap-2 text-sm text-orange-700">
                                <Badge variant="outline" className="bg-orange-100 border-orange-300">
                                    {match.loan_window}
                                </Badge>
                                <span>Stats from {match.loan_window.toLowerCase()} window</span>
                            </div>
                        </div>
                    )}
                </div>
            </DrawerContent>
        </Drawer>
    )
}

export default MatchDetailDrawer











