import { useState, useEffect, useCallback } from 'react'
import { Link, useParams, useSearchParams, useNavigate } from 'react-router-dom'
import { APIService } from '@/lib/api'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { Loader2, ArrowLeft, ChevronDown, ChevronRight } from 'lucide-react'

const CURRENT_SEASON = new Date().getFullYear() - (new Date().getMonth() < 7 ? 1 : 0)

const formatSeason = (s) => `${s}/${(s + 1).toString().slice(-2)}`

export function SquadOriginsDetail() {
    const { teamApiId } = useParams()
    const [searchParams] = useSearchParams()
    const navigate = useNavigate()

    const league = Number(searchParams.get('league') || 2)
    const season = Number(searchParams.get('season') || CURRENT_SEASON)

    const [team, setTeam] = useState(null)
    const [origins, setOrigins] = useState(null)
    const [loading, setLoading] = useState(true)
    const [expandedAcademy, setExpandedAcademy] = useState(null)

    useEffect(() => {
        const load = async () => {
            setLoading(true)
            try {
                const data = await APIService.getSquadOrigins(teamApiId, { league, season })
                setOrigins(data)
                // Use team info from origins response if available
                if (data?.team) {
                    setTeam(data.team)
                }
            } catch (err) {
                console.error('Failed to load squad origins', err)
                setOrigins(null)
            } finally {
                setLoading(false)
            }
        }
        load()
    }, [teamApiId, league, season])

    const handleBack = () => navigate('/teams')

    if (loading) {
        return (
            <div className="max-w-6xl mx-auto px-4 py-8">
                <Button variant="ghost" size="sm" onClick={handleBack} className="mb-2">
                    <ArrowLeft className="h-4 w-4 mr-1" /> Back to teams
                </Button>
                <div className="flex flex-col items-center justify-center py-16 gap-3">
                    <Loader2 className="h-8 w-8 animate-spin text-primary" />
                    <p className="text-sm text-muted-foreground">
                        Resolving academy origins — this may take a moment for first-time lookups...
                    </p>
                </div>
            </div>
        )
    }

    if (!origins || origins.squad_size === 0) {
        return (
            <div className="max-w-6xl mx-auto px-4 py-8">
                <Button variant="ghost" size="sm" onClick={handleBack} className="mb-4">
                    <ArrowLeft className="h-4 w-4 mr-1" /> Back to teams
                </Button>
                <Card>
                    <CardContent className="py-12 text-center text-muted-foreground">
                        No squad data found for this team.
                    </CardContent>
                </Card>
            </div>
        )
    }

    const { academy_breakdown, unknown_origin, squad_size, homegrown_count, homegrown_pct } = origins

    return (
        <div className="max-w-6xl mx-auto px-4 py-8 space-y-6">
            {/* Header */}
            <div className="flex items-center gap-4">
                <Button variant="ghost" size="sm" onClick={handleBack}>
                    <ArrowLeft className="h-4 w-4 mr-1" /> Back
                </Button>
            </div>

            <div className="flex items-center gap-4">
                {team?.logo && (
                    <img
                        src={team.logo}
                        alt={team.name}
                        className="w-16 h-16 object-contain"
                    />
                )}
                <div>
                    <h2 className="text-2xl font-bold text-foreground">{team?.name || `Team ${teamApiId}`}</h2>
                    <p className="text-muted-foreground">
                        Champions League {formatSeason(season)}
                    </p>
                </div>
            </div>

            {/* Summary stats */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <Card>
                    <CardContent className="p-4 text-center">
                        <div className="text-2xl font-bold text-foreground">{squad_size}</div>
                        <div className="text-xs text-muted-foreground">Squad Players</div>
                    </CardContent>
                </Card>
                <Card>
                    <CardContent className="p-4 text-center">
                        <div className="text-2xl font-bold text-primary">{homegrown_count}</div>
                        <div className="text-xs text-muted-foreground">Homegrown</div>
                    </CardContent>
                </Card>
                <Card>
                    <CardContent className="p-4 text-center">
                        <div className="text-2xl font-bold text-foreground">{homegrown_pct}%</div>
                        <div className="text-xs text-muted-foreground">Homegrown Rate</div>
                    </CardContent>
                </Card>
                <Card>
                    <CardContent className="p-4 text-center">
                        <div className="text-2xl font-bold text-foreground">{academy_breakdown.length}</div>
                        <div className="text-xs text-muted-foreground">Feeder Academies</div>
                    </CardContent>
                </Card>
            </div>

            {/* Academy breakdown */}
            <div className="space-y-2">
                <h3 className="text-lg font-semibold text-foreground/80">Academy Breakdown</h3>
                {academy_breakdown.map((group) => {
                    const isExpanded = expandedAcademy === group.academy.api_id
                    return (
                        <Card key={group.academy.api_id} className="overflow-hidden">
                            <div
                                className="flex items-center gap-3 p-4 cursor-pointer hover:bg-secondary/50 transition-colors"
                                onClick={() => setExpandedAcademy(isExpanded ? null : group.academy.api_id)}
                            >
                                <img
                                    src={group.academy.logo}
                                    alt={group.academy.name}
                                    className="w-8 h-8 object-contain flex-shrink-0"
                                />
                                <div className="flex-1 min-w-0">
                                    <span className="font-medium text-foreground">
                                        {group.academy.name}
                                    </span>
                                    {group.is_homegrown && (
                                        <Badge className="ml-2 bg-primary/10 text-primary border-primary/20 text-xs">
                                            Homegrown
                                        </Badge>
                                    )}
                                </div>
                                <Badge variant="outline" className="flex-shrink-0">
                                    {group.count} {group.count === 1 ? 'player' : 'players'}
                                </Badge>
                                {isExpanded ? (
                                    <ChevronDown className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                                ) : (
                                    <ChevronRight className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                                )}
                            </div>
                            {isExpanded && (
                                <div className="border-t bg-secondary/20 px-4 py-2">
                                    <div className="space-y-2">
                                        {group.players.map((player) => (
                                            <Link
                                                key={player.player_api_id}
                                                to={`/players/${player.player_api_id}`}
                                                className="flex items-center gap-3 py-2 px-2 rounded-md hover:bg-secondary transition-colors no-underline"
                                            >
                                                <Avatar className="h-8 w-8">
                                                    <AvatarImage src={player.photo} alt={player.player_name} />
                                                    <AvatarFallback className="text-xs">
                                                        {(player.player_name || '').split(' ').map(n => n[0]).join('').slice(0, 2)}
                                                    </AvatarFallback>
                                                </Avatar>
                                                <div className="flex-1 min-w-0">
                                                    <div className="text-sm font-medium text-foreground">
                                                        {player.player_name}
                                                    </div>
                                                    <div className="text-xs text-muted-foreground">
                                                        {player.position} — {player.nationality}
                                                    </div>
                                                </div>
                                                <div className="text-xs text-muted-foreground text-right">
                                                    {player.appearances > 0 && (
                                                        <span>{player.appearances} apps</span>
                                                    )}
                                                    {player.goals > 0 && (
                                                        <span className="ml-2">{player.goals}G</span>
                                                    )}
                                                    {player.assists > 0 && (
                                                        <span className="ml-1">{player.assists}A</span>
                                                    )}
                                                </div>
                                            </Link>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </Card>
                    )
                })}
            </div>

            {/* Unknown origins */}
            {unknown_origin.length > 0 && (
                <div className="space-y-2">
                    <h3 className="text-lg font-semibold text-foreground/80">
                        Unknown Origin
                        <Badge variant="outline" className="ml-2">{unknown_origin.length}</Badge>
                    </h3>
                    <Card>
                        <CardContent className="p-4">
                            <div className="space-y-2">
                                {unknown_origin.map((player) => (
                                    <Link
                                        key={player.player_api_id}
                                        to={`/players/${player.player_api_id}`}
                                        className="flex items-center gap-3 py-2 px-2 rounded-md hover:bg-secondary transition-colors no-underline"
                                    >
                                        <Avatar className="h-8 w-8">
                                            <AvatarImage src={player.photo} alt={player.player_name} />
                                            <AvatarFallback className="text-xs">
                                                {(player.player_name || '').split(' ').map(n => n[0]).join('').slice(0, 2)}
                                            </AvatarFallback>
                                        </Avatar>
                                        <span className="text-sm font-medium text-foreground">
                                            {player.player_name}
                                        </span>
                                        <span className="text-xs text-muted-foreground">
                                            {player.position}
                                        </span>
                                    </Link>
                                ))}
                            </div>
                        </CardContent>
                    </Card>
                </div>
            )}
        </div>
    )
}
