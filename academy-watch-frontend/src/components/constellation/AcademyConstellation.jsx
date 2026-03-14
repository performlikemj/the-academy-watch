import { useState, useEffect, useCallback } from 'react'
import { Loader2, TrendingUp } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { APIService } from '@/lib/api'
import { ConstellationGraph } from './ConstellationGraph'
import { ConstellationSummary } from './ConstellationSummary'
import { NodeDetailPanel } from './NodeDetailPanel'

export function AcademyConstellation({ teamApiId }) {
    const [data, setData] = useState(null)
    const [loading, setLoading] = useState(false)
    const [loaded, setLoaded] = useState(false)
    const [error, setError] = useState(null)
    const [selectedNode, setSelectedNode] = useState(null)

    const loadNetwork = useCallback(async () => {
        if (loaded || loading || !teamApiId) return
        setLoading(true)
        setError(null)
        try {
            const result = await APIService.getAcademyNetwork(teamApiId, { years: 4 })
            setData(result)
        } catch (err) {
            console.error('Failed to load academy network:', err)
            setError('Failed to load academy network data.')
        } finally {
            setLoading(false)
            setLoaded(true)
        }
    }, [teamApiId, loaded, loading])

    useEffect(() => {
        loadNetwork()
    }, [loadNetwork])

    if (loading) {
        return (
            <div className="flex items-center justify-center py-16">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground/70 mr-2" />
                <span className="text-sm text-muted-foreground">Loading academy network...</span>
            </div>
        )
    }

    if (error) {
        return (
            <Card>
                <CardContent className="py-12 text-center">
                    <p className="text-red-500 text-sm">{error}</p>
                </CardContent>
            </Card>
        )
    }

    if (loaded && (!data || data.total_academy_players === 0)) {
        return (
            <Card>
                <CardContent className="py-12 text-center">
                    <TrendingUp className="h-12 w-12 mx-auto text-muted-foreground/50 mb-4" />
                    <p className="text-muted-foreground">No academy network data available yet</p>
                    <p className="text-sm text-muted-foreground/70 mt-1">
                        Journey data needs to be synced for this team's academy players.
                    </p>
                </CardContent>
            </Card>
        )
    }

    if (!data) return null

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h3 className="text-base font-semibold text-foreground">
                        Academy Network
                    </h3>
                    <p className="text-sm text-muted-foreground">
                        {data.total_academy_players} academy player{data.total_academy_players !== 1 ? 's' : ''} tracked
                        {data.season_range && (
                            <span> · {data.season_range[0]}/{String(data.season_range[0] + 1).slice(-2)} – {data.season_range[1]}/{String(data.season_range[1] + 1).slice(-2)}</span>
                        )}
                    </p>
                </div>
            </div>

            {/* Constellation graph */}
            {data.nodes?.length > 1 && (
                <ConstellationGraph
                    data={data}
                    selectedNode={selectedNode}
                    onNodeClick={(node) => {
                        setSelectedNode(prev =>
                            prev?.club_api_id === node.club_api_id ? null : node
                        )
                    }}
                />
            )}

            {/* Node detail panel */}
            {selectedNode && (
                <NodeDetailPanel
                    node={selectedNode}
                    allPlayers={data.all_players || []}
                    onClose={() => setSelectedNode(null)}
                />
            )}

            {/* Player summary by status */}
            <ConstellationSummary data={data} parentTeamName={data.team_name} />
        </div>
    )
}

export default AcademyConstellation
