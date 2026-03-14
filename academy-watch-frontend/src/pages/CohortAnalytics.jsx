import { useState, useEffect, useCallback } from 'react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { APIService } from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Loader2 } from 'lucide-react'
import { CHART_GRID_COLOR, CHART_AXIS_COLOR, CONSTELLATION_STATUS_COLORS } from '../lib/theme-constants'

export function CohortAnalytics() {
    const [analytics, setAnalytics] = useState([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)
    const [sortField, setSortField] = useState('conversion_rate')
    const [sortDir, setSortDir] = useState('desc')

    const loadAnalytics = useCallback(async () => {
        try {
            setLoading(true)
            setError(null)
            const data = await APIService.getCohortAnalytics()
            setAnalytics(data?.analytics || [])
        } catch (err) {
            console.error('Failed to load cohort analytics', err)
            setError('Failed to load analytics data.')
        } finally {
            setLoading(false)
        }
    }, [])

    useEffect(() => {
        loadAnalytics()
    }, [loadAnalytics])

    const handleSort = (field) => {
        if (sortField === field) {
            setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
        } else {
            setSortField(field)
            setSortDir('desc')
        }
    }

    const sortedAnalytics = () => {
        return [...analytics].sort((a, b) => {
            let valA = a[sortField]
            let valB = b[sortField]

            if (typeof valA === 'string') {
                valA = valA.toLowerCase()
                valB = (valB || '').toLowerCase()
            }

            if (typeof valA === 'number' || typeof valB === 'number') {
                valA = valA || 0
                valB = valB || 0
            }

            if (valA < valB) return sortDir === 'asc' ? -1 : 1
            if (valA > valB) return sortDir === 'asc' ? 1 : -1
            return 0
        })
    }

    const chartData = sortedAnalytics().map((team) => ({
        team_name: team.team_name,
        conversion_rate: team.conversion_rate || 0,
    }))

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
                    <p className="text-muted-foreground">Loading analytics...</p>
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

    return (
        <div className="min-h-screen bg-gradient-to-b from-secondary to-background">
            <div className="max-w-6xl mx-auto px-4 py-8">
                {/* Header */}
                <div className="flex items-center gap-4 mb-8">
                    <Button variant="ghost" size="sm" onClick={() => window.history.back()}>
                        Back
                    </Button>
                    <div>
                        <h1 className="text-3xl font-bold tracking-tight text-foreground">Academy Analytics</h1>
                        <p className="text-muted-foreground mt-1">Compare academy-to-first-team conversion rates across clubs</p>
                    </div>
                </div>

                {/* Bar Chart */}
                {chartData.length > 0 && (
                    <Card className="mb-8">
                        <CardHeader>
                            <CardTitle>First Team Conversion Rate by Club</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <ResponsiveContainer width="100%" height={400}>
                                <BarChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 60 }}>
                                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={CHART_GRID_COLOR} />
                                    <XAxis
                                        dataKey="team_name"
                                        tick={{ fontSize: 11, fill: CHART_AXIS_COLOR }}
                                        angle={-45}
                                        textAnchor="end"
                                        height={80}
                                        tickLine={false}
                                        axisLine={false}
                                    />
                                    <YAxis
                                        tick={{ fontSize: 11, fill: CHART_AXIS_COLOR }}
                                        tickLine={false}
                                        axisLine={false}
                                        unit="%"
                                    />
                                    <Tooltip
                                        formatter={(value) => [`${value}%`, 'Conversion Rate']}
                                        contentStyle={{ borderRadius: '8px', fontSize: '13px' }}
                                    />
                                    <Legend />
                                    <Bar
                                        dataKey="conversion_rate"
                                        fill={CONSTELLATION_STATUS_COLORS.first_team}
                                        radius={[4, 4, 0, 0]}
                                        name="Conversion Rate"
                                    />
                                </BarChart>
                            </ResponsiveContainer>
                        </CardContent>
                    </Card>
                )}

                {/* Comparison Table */}
                <Card>
                    <CardHeader>
                        <CardTitle>Club Comparison</CardTitle>
                    </CardHeader>
                    <CardContent>
                        {analytics.length === 0 ? (
                            <p className="text-center text-muted-foreground py-8">No analytics data available.</p>
                        ) : (
                            <div className="overflow-x-auto">
                                <table className="w-full text-sm text-left">
                                    <thead className="bg-secondary">
                                        <tr>
                                            <SortHeader field="team_name" label="Team" />
                                            <SortHeader field="total_players" label="Total Players" />
                                            <SortHeader field="players_first_team" label="First Team" />
                                            <SortHeader field="players_on_loan" label="On Loan" />
                                            <SortHeader field="players_still_academy" label="Academy" />
                                            <SortHeader field="players_released" label="Released" />
                                            <SortHeader field="conversion_rate" label="Conversion %" />
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-border">
                                        {sortedAnalytics().map((team, i) => (
                                            <tr key={team.team_name || i} className="hover:bg-secondary">
                                                <td className="p-3">
                                                    <div className="flex items-center gap-3">
                                                        {team.team_logo && (
                                                            <img
                                                                src={team.team_logo}
                                                                alt={team.team_name}
                                                                className="w-6 h-6 object-contain"
                                                            />
                                                        )}
                                                        <span className="font-medium text-foreground">{team.team_name}</span>
                                                    </div>
                                                </td>
                                                <td className="p-3 text-muted-foreground">{team.total_players || 0}</td>
                                                <td className="p-3">
                                                    <span className="text-emerald-700 font-medium">{team.players_first_team || 0}</span>
                                                </td>
                                                <td className="p-3">
                                                    <span className="text-amber-700">{team.players_on_loan || 0}</span>
                                                </td>
                                                <td className="p-3">
                                                    <span className="text-yellow-700">{team.players_still_academy || 0}</span>
                                                </td>
                                                <td className="p-3">
                                                    <span className="text-muted-foreground">{team.players_released || 0}</span>
                                                </td>
                                                <td className="p-3">
                                                    <Badge
                                                        className={
                                                            (team.conversion_rate || 0) >= 20
                                                                ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                                                                : (team.conversion_rate || 0) >= 10
                                                                ? 'bg-amber-50 text-amber-800 border-amber-200'
                                                                : 'bg-secondary text-foreground/80 border-border'
                                                        }
                                                    >
                                                        {team.conversion_rate || 0}%
                                                    </Badge>
                                                </td>
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
