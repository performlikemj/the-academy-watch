import { useState, useEffect, useCallback } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { APIService } from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Loader2 } from 'lucide-react'
import { STATUS_BADGE_CLASSES } from '../lib/theme-constants'

export function CohortBrowser() {
    const navigate = useNavigate()
    const [teams, setTeams] = useState([])
    const [teamsLoading, setTeamsLoading] = useState(true)
    const [selectedTeam, setSelectedTeam] = useState(null)
    const [cohorts, setCohorts] = useState([])
    const [cohortsLoading, setCohortsLoading] = useState(false)

    const loadTeams = useCallback(async () => {
        try {
            setTeamsLoading(true)
            const data = await APIService.getCohortTeams()
            setTeams(data?.teams || [])
        } catch (err) {
            console.error('Failed to load cohort teams', err)
        } finally {
            setTeamsLoading(false)
        }
    }, [])

    useEffect(() => {
        loadTeams()
    }, [loadTeams])

    const handleTeamSelect = useCallback(async (team) => {
        setSelectedTeam(team)
        setCohortsLoading(true)
        try {
            const data = await APIService.getCohorts({ team_api_id: team.team_api_id })
            setCohorts(data?.cohorts || [])
        } catch (err) {
            console.error('Failed to load cohorts', err)
            setCohorts([])
        } finally {
            setCohortsLoading(false)
        }
    }, [])

    const getStatusBadge = (status) => {
        const colorClass = STATUS_BADGE_CLASSES[status] || 'bg-secondary text-foreground/80 border-border'
        return (
            <Badge className={colorClass}>
                {status?.replace('_', ' ')}
            </Badge>
        )
    }

    return (
        <div className="min-h-screen bg-gradient-to-b from-secondary to-background">
            <div className="max-w-6xl mx-auto px-4 py-8">
                {/* Header */}
                <div className="flex items-center justify-between mb-8">
                    <div>
                        <h1 className="text-3xl font-bold tracking-tight text-foreground">Academy Cohorts</h1>
                        <p className="text-muted-foreground mt-1">Browse academy cohorts by team to track player development pathways</p>
                    </div>
                    <Link to="/academy/analytics">
                        <Button variant="outline">View Analytics</Button>
                    </Link>
                </div>

                {/* Team Selection Grid */}
                {teamsLoading ? (
                    <div className="flex items-center justify-center py-16">
                        <Loader2 className="h-8 w-8 animate-spin text-primary" />
                    </div>
                ) : (
                    <div className="space-y-8">
                        <div>
                            <h2 className="text-lg font-semibold text-foreground/80 mb-4">Select a Team</h2>
                            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
                                {teams.map((team) => (
                                    <Card
                                        key={team.team_api_id}
                                        className={`cursor-pointer transition-all hover:shadow-md hover:border-primary/20 ${
                                            selectedTeam?.team_api_id === team.team_api_id
                                                ? 'border-primary ring-2 ring-primary/20'
                                                : ''
                                        }`}
                                        onClick={() => handleTeamSelect(team)}
                                    >
                                        <CardContent className="flex items-center gap-3 p-4">
                                            <img
                                                src={team.team_logo}
                                                alt={team.team_name}
                                                className="w-8 h-8 object-contain"
                                            />
                                            <span className="font-medium text-foreground truncate">{team.team_name}</span>
                                        </CardContent>
                                    </Card>
                                ))}
                            </div>
                        </div>

                        {/* Cohorts List */}
                        {selectedTeam && (
                            <div>
                                <h2 className="text-lg font-semibold text-foreground/80 mb-4">
                                    Cohorts for {selectedTeam.team_name}
                                </h2>

                                {cohortsLoading ? (
                                    <div className="flex items-center justify-center py-12">
                                        <Loader2 className="h-8 w-8 animate-spin text-primary" />
                                    </div>
                                ) : cohorts.length === 0 ? (
                                    <Card>
                                        <CardContent className="py-12 text-center text-muted-foreground">
                                            No cohorts found for this team.
                                        </CardContent>
                                    </Card>
                                ) : (
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                        {cohorts.map((cohort) => (
                                            <Card
                                                key={cohort.id}
                                                className="cursor-pointer transition-all hover:shadow-md hover:border-primary/20"
                                                onClick={() => navigate(`/academy/cohorts/${cohort.id}`)}
                                            >
                                                <CardHeader className="pb-2">
                                                    <div className="flex items-center justify-between">
                                                        <CardTitle className="text-base">
                                                            {cohort.season} Season
                                                        </CardTitle>
                                                        <Badge variant="outline">{cohort.analytics?.total_players || 0} players</Badge>
                                                    </div>
                                                    {cohort.league_name && (
                                                        <p className="text-sm text-muted-foreground">{cohort.league_name}</p>
                                                    )}
                                                </CardHeader>
                                                <CardContent>
                                                    {cohort.analytics && (
                                                        <div className="flex flex-wrap gap-2">
                                                            {cohort.analytics.players_first_team > 0 && getStatusBadge('first_team')}
                                                            {cohort.analytics.players_on_loan > 0 && getStatusBadge('on_loan')}
                                                            {cohort.analytics.players_still_academy > 0 && getStatusBadge('academy')}
                                                            {cohort.analytics.players_released > 0 && getStatusBadge('released')}
                                                        </div>
                                                    )}
                                                </CardContent>
                                            </Card>
                                        ))}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    )
}
