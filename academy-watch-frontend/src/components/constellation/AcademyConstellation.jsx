import { useState, useEffect, useCallback } from 'react'
import { Loader2, TrendingUp } from 'lucide-react'
import { APIService } from '@/lib/api'
import { NetworkMap } from './NetworkMap'
import { NetworkMapHeader } from './NetworkMapHeader'
import { NetworkStatusBar } from './NetworkStatusBar'
import { NetworkDetailSheet } from './NetworkDetailSheet'

export function AcademyConstellation({ teamApiId }) {
    const [data, setData] = useState(null)
    const [loading, setLoading] = useState(false)
    const [loaded, setLoaded] = useState(false)
    const [error, setError] = useState(null)
    const [selectedNode, setSelectedNode] = useState(null)
    const [statusFilter, setStatusFilter] = useState(null)

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
                <Loader2 className="h-6 w-6 animate-spin text-amber-400/70 mr-2" />
                <span className="text-sm text-slate-400">Loading academy network...</span>
            </div>
        )
    }

    if (error) {
        return (
            <div className="py-12 text-center rounded-xl bg-slate-800/50 border border-slate-700/50">
                <p className="text-red-400 text-sm">{error}</p>
            </div>
        )
    }

    if (loaded && (!data || data.total_academy_players === 0)) {
        return (
            <div className="py-12 text-center rounded-xl bg-slate-800/50 border border-slate-700/50">
                <TrendingUp className="h-12 w-12 mx-auto text-slate-600 mb-4" />
                <p className="text-slate-400">No academy network data available yet</p>
                <p className="text-sm text-slate-500 mt-1">
                    Journey data needs to be synced for this team's academy players.
                </p>
            </div>
        )
    }

    if (!data) return null

    return (
        <div className="space-y-4">
            {/* Stats header */}
            <NetworkMapHeader data={data} />

            {/* Geographic network map */}
            {data.nodes?.length > 1 && (
                <NetworkMap
                    data={data}
                    selectedNode={selectedNode}
                    statusFilter={statusFilter}
                    onNodeClick={(node) => {
                        setSelectedNode(prev =>
                            prev?.club_api_id === node.club_api_id ? null : node
                        )
                    }}
                />
            )}

            {/* Status filter bar */}
            <NetworkStatusBar
                summary={data.summary || {}}
                activeFilter={statusFilter}
                onFilterChange={setStatusFilter}
                parentTeamName={data.team_name}
            />

            {/* Club detail sheet */}
            <NetworkDetailSheet
                node={selectedNode}
                allPlayers={data.all_players || []}
                open={!!selectedNode}
                onClose={() => setSelectedNode(null)}
            />
        </div>
    )
}

export default AcademyConstellation
