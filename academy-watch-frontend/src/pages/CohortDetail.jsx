import { useState, useEffect, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { PieChart, Pie, Cell, Legend, ResponsiveContainer } from 'recharts'
import { APIService } from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Loader2 } from 'lucide-react'
import { STATUS_BADGE_CLASSES, CONSTELLATION_STATUS_COLORS } from '../lib/theme-constants'

const CHART_COLORS = {
    first_team: CONSTELLATION_STATUS_COLORS.first_team,
    on_loan: CONSTELLATION_STATUS_COLORS.on_loan,
    academy: CONSTELLATION_STATUS_COLORS.academy,
    released: CONSTELLATION_STATUS_COLORS.released,
    unknown: '#a855f7',
}

export function CohortDetail() {
    const { cohortId } = useParams()
    const [cohort, setCohort] = useState(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)
    const [sortField, setSortField] = useState('player_name')
    const [sortDir, setSortDir] = useState('asc')

    const loadCohort = useCallback(async () => {
        try {
            setLoading(true)
            setError(null)
            const data = await APIService.getCohort(cohortId, { include_members: 'true' })
            setCohort(data)
        } catch (err) {
            console.error('Failed to load cohort', err)
            setError('Failed to load cohort details.')
        } finally {
            setLoading(false)
        }
    }, [cohortId])

    useEffect(() => {
        if (cohortId) {
            loadCohort()
        }
    }, [cohortId, loadCohort])

    const handleSort = (field) => {
        if (sortField === field) {
            setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
        } else {
            setSortField(field)
            setSortDir('asc')
        }
    }

    const getSortValue = (member, field) => {
        switch (field) {
            case 'player_name': return member.player_name || ''
            case 'position': return member.position || ''
            case 'nationality': return member.nationality || ''
            case 'appearances': return member.cohort_stats?.appearances || 0
            case 'goals': return member.cohort_stats?.goals || 0
            case 'current_club': return member.current?.club_name || ''
            case 'status': return member.current?.status || 'unknown'
            default: return ''
        }
    }

    const sortedMembers = () => {
        if (!cohort?.members) return []
        return [...cohort.members].sort((a, b) => {
            let valA = getSortValue(a, sortField)
            let valB = getSortValue(b, sortField)

            if (typeof valA === 'string') {
                valA = valA.toLowerCase()
                valB = (valB || '').toLowerCase()
            }

            if (valA < valB) return sortDir === 'asc' ? -1 : 1
            if (valA > valB) return sortDir === 'asc' ? 1 : -1
            return 0
        })
    }

    const getStatusBadge = (status) => {
        const colorClass = STATUS_BADGE_CLASSES[status] || 'bg-purple-50 text-purple-800 border-purple-200'
        return (
            <Badge className={colorClass}>
                {status?.replace('_', ' ') || 'unknown'}
            </Badge>
        )
    }

    const buildChartData = () => {
        if (!cohort?.analytics) return []
        const entries = [
            { name: 'First Team', value: cohort.analytics.players_first_team || 0, key: 'first_team' },
            { name: 'On Loan', value: cohort.analytics.players_on_loan || 0, key: 'on_loan' },
            { name: 'Academy', value: cohort.analytics.players_still_academy || 0, key: 'academy' },
            { name: 'Released', value: cohort.analytics.players_released || 0, key: 'released' },
        ]
        return entries.filter((e) => e.value > 0)
    }

    const SortHeader = ({ field, label }) => (
        <th
            className="p-3 font-medium text-muted-foreground cursor-pointer hover:text-foreground select-none"
            onClick={() => handleSort(field)}
        >
            <span className="inline-flex items-center gap-1">
                {label}
                {sortField === field && (
                    <span className="text-xs">{sortDir === 'asc' ? '\u2191' : '\u2193'}</span>
                )}
            </span>
        </th>
    )

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-gradient-to-b from-secondary to-background">
                <div className="text-center">
                    <Loader2 className="h-12 w-12 animate-spin text-primary mx-auto mb-4" />
                    <p className="text-muted-foreground">Loading cohort details...</p>
                </div>
            </div>
        )
    }

    if (error) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-gradient-to-b from-secondary to-background">
                <Card className="max-w-md">
                    <CardContent className="pt-6 text-center">
                        <p className="text-red-500 mb-4">{error}</p>
                        <Button variant="outline" onClick={() => window.history.back()}>
                            Go Back
                        </Button>
                    </CardContent>
                </Card>
            </div>
        )
    }

    if (!cohort) return null

    const chartData = buildChartData()
    const analytics = cohort.analytics || {}

    return (
        <div className="min-h-screen bg-gradient-to-b from-secondary to-background">
            <div className="max-w-6xl mx-auto px-4 py-8">
                {/* Header */}
                <div className="flex items-center gap-4 mb-8">
                    <Button variant="ghost" size="sm" onClick={() => window.history.back()}>
                        Back
                    </Button>
                    {cohort.team_logo && (
                        <img
                            src={cohort.team_logo}
                            alt={cohort.team_name}
                            className="w-12 h-12 object-contain"
                        />
                    )}
                    <div>
                        <h1 className="text-3xl font-bold tracking-tight text-foreground">
                            {cohort.team_name}
                        </h1>
                        <p className="text-muted-foreground">
                            {cohort.league_name && `${cohort.league_name} \u00b7 `}
                            {cohort.season} Season
                        </p>
                    </div>
                </div>

                {/* Stats Row */}
                <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
                    <Card>
                        <CardHeader className="pb-2">
                            <CardTitle className="text-sm text-muted-foreground">Total Players</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="text-3xl font-bold">{analytics.total_players || 0}</div>
                        </CardContent>
                    </Card>
                    <Card>
                        <CardHeader className="pb-2">
                            <CardTitle className="text-sm text-emerald-600">First Team</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="text-3xl font-bold text-emerald-600">{analytics.players_first_team || 0}</div>
                        </CardContent>
                    </Card>
                    <Card>
                        <CardHeader className="pb-2">
                            <CardTitle className="text-sm text-amber-600">On Loan</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="text-3xl font-bold text-amber-600">{analytics.players_on_loan || 0}</div>
                        </CardContent>
                    </Card>
                    <Card>
                        <CardHeader className="pb-2">
                            <CardTitle className="text-sm text-yellow-600">Academy</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="text-3xl font-bold text-yellow-600">{analytics.players_still_academy || 0}</div>
                        </CardContent>
                    </Card>
                    <Card>
                        <CardHeader className="pb-2">
                            <CardTitle className="text-sm text-muted-foreground">Released</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="text-3xl font-bold text-muted-foreground">{analytics.players_released || 0}</div>
                        </CardContent>
                    </Card>
                </div>

                {/* Donut Chart */}
                {chartData.length > 0 && (
                    <Card className="mb-8">
                        <CardHeader>
                            <CardTitle>Player Status Distribution</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <ResponsiveContainer width="100%" height={250}>
                                <PieChart>
                                    <Pie
                                        data={chartData}
                                        cx="50%"
                                        cy="50%"
                                        innerRadius={60}
                                        outerRadius={100}
                                        paddingAngle={2}
                                        dataKey="value"
                                        nameKey="name"
                                    >
                                        {chartData.map((entry) => (
                                            <Cell
                                                key={entry.key}
                                                fill={CHART_COLORS[entry.key]}
                                            />
                                        ))}
                                    </Pie>
                                    <Legend />
                                </PieChart>
                            </ResponsiveContainer>
                        </CardContent>
                    </Card>
                )}

                {/* Player Table */}
                <Card>
                    <CardHeader>
                        <CardTitle>Squad Members</CardTitle>
                    </CardHeader>
                    <CardContent>
                        {(!cohort.members || cohort.members.length === 0) ? (
                            <p className="text-center text-muted-foreground py-8">No players in this cohort.</p>
                        ) : (
                            <div className="overflow-x-auto">
                                <table className="w-full text-sm text-left">
                                    <thead className="bg-secondary">
                                        <tr>
                                            <SortHeader field="player_name" label="Player" />
                                            <SortHeader field="position" label="Position" />
                                            <SortHeader field="nationality" label="Nationality" />
                                            <SortHeader field="appearances" label="Apps" />
                                            <SortHeader field="goals" label="Goals" />
                                            <SortHeader field="current_club" label="Current Club" />
                                            <SortHeader field="status" label="Status" />
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-border">
                                        {sortedMembers().map((member, i) => (
                                            <tr key={member.id || i} className="hover:bg-secondary">
                                                <td className="p-3">
                                                    <Link
                                                        to={`/players/${member.player_api_id}`}
                                                        className="flex items-center gap-3 hover:underline"
                                                    >
                                                        {member.player_photo ? (
                                                            <img
                                                                src={member.player_photo}
                                                                alt={member.player_name}
                                                                className="w-8 h-8 rounded-full object-cover"
                                                            />
                                                        ) : (
                                                            <div className="w-8 h-8 rounded-full bg-muted flex items-center justify-center text-xs text-muted-foreground">
                                                                {member.player_name?.charAt(0) || '?'}
                                                            </div>
                                                        )}
                                                        <span className="font-medium text-primary">{member.player_name}</span>
                                                    </Link>
                                                </td>
                                                <td className="p-3 text-muted-foreground">{member.position || '-'}</td>
                                                <td className="p-3 text-muted-foreground">{member.nationality || '-'}</td>
                                                <td className="p-3 text-muted-foreground">{member.cohort_stats?.appearances ?? '-'}</td>
                                                <td className="p-3 text-muted-foreground">{member.cohort_stats?.goals ?? '-'}</td>
                                                <td className="p-3 text-muted-foreground">{member.current?.club_name || '-'}</td>
                                                <td className="p-3">{getStatusBadge(member.current?.status)}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </CardContent>
                </Card>
            </div>
        </div>
    )
}
