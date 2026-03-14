import { useRef, useEffect, useState, useMemo, useCallback } from 'react'
import {
    ComposableMap, Geographies, Geography, Marker, Line, ZoomableGroup,
} from 'react-simple-maps'
import { calculateView, arcControlPoint } from '@/lib/map-utils'
import { LINK_COLORS } from './constellation-utils'

const GEO_URL = 'https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json'

const ARC_COLORS = {
    loan: 'rgba(251,191,36,0.5)',
    permanent: 'rgba(148,163,184,0.4)',
    return: 'rgba(74,222,128,0.4)',
}

const ARC_DURATIONS = {
    loan: '3s',
    permanent: '4s',
    return: '4s',
}

/**
 * Geographic network map showing an academy's talent distribution.
 * Renders a world map with the parent club at its coordinates and
 * curved arcs connecting it to destination clubs.
 */
export function NetworkMap({ data, onNodeClick, selectedNode, statusFilter }) {
    const containerRef = useRef(null)
    const [dimensions, setDimensions] = useState({ width: 800, height: 500 })

    // Responsive sizing via ResizeObserver
    useEffect(() => {
        const el = containerRef.current
        if (!el) return
        const observer = new ResizeObserver((entries) => {
            const { width, height } = entries[0].contentRect
            if (width > 0) setDimensions({ width, height })
        })
        observer.observe(el)
        return () => observer.disconnect()
    }, [])

    // Split nodes into mappable (have lat/lng) and unmapped
    const { mappedNodes, unmappedCount } = useMemo(() => {
        if (!data?.nodes?.length) return { mappedNodes: [], unmappedCount: 0 }
        const mapped = []
        let unmapped = 0
        for (const node of data.nodes) {
            if (node.lat && node.lng) {
                mapped.push(node)
            } else {
                unmapped++
            }
        }
        return { mappedNodes: mapped, unmappedCount: unmapped }
    }, [data])

    // Calculate view to fit all mapped nodes
    const view = useMemo(() => {
        return calculateView(mappedNodes)
    }, [mappedNodes])

    // Build a lookup from original node index to mapped node data
    const nodeByIndex = useMemo(() => {
        if (!data?.nodes) return new Map()
        const map = new Map()
        data.nodes.forEach((node, i) => {
            if (node.lat && node.lng) map.set(i, node)
        })
        return map
    }, [data])

    // Build renderable arcs with SVG path strings and metadata
    const arcs = useMemo(() => {
        if (!data?.links?.length) return []
        return data.links
            .map((link) => {
                const sourceNode = nodeByIndex.get(link.source)
                const targetNode = nodeByIndex.get(link.target)
                if (!sourceNode || !targetNode) return null

                const from = [sourceNode.lng, sourceNode.lat]
                const to = [targetNode.lng, targetNode.lat]
                const cp = arcControlPoint(from, to, 0.2)

                return {
                    ...link,
                    from,
                    to,
                    cp,
                    sourceNode,
                    targetNode,
                }
            })
            .filter(Boolean)
    }, [data, nodeByIndex])

    // Find the parent node
    const parentNode = useMemo(() => {
        return mappedNodes.find((n) => n.is_parent) || null
    }, [mappedNodes])

    // Destination nodes (non-parent)
    const destNodes = useMemo(() => {
        return mappedNodes.filter((n) => !n.is_parent)
    }, [mappedNodes])

    const handleMarkerClick = useCallback(
        (node) => {
            if (onNodeClick) onNodeClick(node)
        },
        [onNodeClick],
    )

    // Build lookup: which club_api_ids have players with each status
    const statusClubMap = useMemo(() => {
        if (!data?.all_players) return {}
        const map = {} // status -> Set of club_api_ids
        for (const player of data.all_players) {
            if (!player.status) continue
            if (!map[player.status]) map[player.status] = new Set()
            // Add all clubs in the player's journey path
            for (const stop of (player.journey_path || [])) {
                map[player.status].add(stop.club_api_id)
            }
        }
        return map
    }, [data?.all_players])

    // Build lookup: which player_api_ids have each status
    const statusPlayerMap = useMemo(() => {
        if (!data?.all_players) return {}
        const map = {}
        for (const player of data.all_players) {
            if (!player.status) continue
            if (!map[player.status]) map[player.status] = new Set()
            map[player.status].add(player.player_api_id)
        }
        return map
    }, [data?.all_players])

    // Check if a node matches the current status filter
    const nodeMatchesFilter = useCallback(
        (node) => {
            if (!statusFilter) return true
            const clubSet = statusClubMap[statusFilter]
            return clubSet ? clubSet.has(node.club_api_id) : false
        },
        [statusFilter, statusClubMap],
    )

    const linkMatchesFilter = useCallback(
        (link) => {
            if (!statusFilter) return true
            const playerSet = statusPlayerMap[statusFilter]
            if (!playerSet) return false
            // Check if any player on this link has the matching status
            return link.players?.some(p => playerSet.has(p.player_api_id)) ?? false
        },
        [statusFilter, statusPlayerMap],
    )

    if (!data?.nodes?.length) return null

    return (
        <div
            ref={containerRef}
            className="relative w-full bg-slate-900 rounded-xl overflow-hidden h-[300px] sm:h-[450px] lg:h-[550px]"
        >
            <ComposableMap
                width={dimensions.width}
                height={dimensions.height}
                projectionConfig={{ scale: 160 }}
                style={{ width: '100%', height: '100%' }}
            >
                <ZoomableGroup center={view.center} zoom={view.zoom}>
                    <Geographies geography={GEO_URL}>
                        {({ geographies }) =>
                            geographies.map((geo) => (
                                <Geography
                                    key={geo.rsmKey}
                                    geography={geo}
                                    fill="#1e293b"
                                    stroke="#334155"
                                    strokeWidth={0.5}
                                    style={{
                                        default: { outline: 'none' },
                                        hover: { outline: 'none', fill: '#1e293b' },
                                        pressed: { outline: 'none' },
                                    }}
                                />
                            ))
                        }
                    </Geographies>

                    {/* Arc lines */}
                    {arcs.map((arc, i) => {
                        const matches = linkMatchesFilter(arc)
                        return (
                            <Line
                                key={`line-${i}`}
                                from={arc.from}
                                to={arc.to}
                                stroke={ARC_COLORS[arc.link_type] || ARC_COLORS.loan}
                                strokeWidth={Math.max(1, Math.min(3, arc.player_count * 0.7))}
                                strokeLinecap="round"
                                strokeDasharray={arc.link_type === 'loan' ? '6 3' : undefined}
                                strokeOpacity={statusFilter ? (matches ? 0.8 : 0.08) : 0.8}
                                style={{ transition: 'stroke-opacity 0.3s ease' }}
                            />
                        )
                    })}

                    {/* Destination markers */}
                    {destNodes.map((node) => {
                        const r = Math.max(6, Math.sqrt(node.player_count || 1) * 4)
                        const isSelected = selectedNode?.club_api_id === node.club_api_id
                        const matches = nodeMatchesFilter(node)
                        const clipId = `clip-dest-${node.club_api_id}`

                        return (
                            <Marker
                                key={`dest-${node.club_api_id}`}
                                coordinates={[node.lng, node.lat]}
                            >
                                <g
                                    onClick={() => handleMarkerClick(node)}
                                    style={{
                                        cursor: 'pointer',
                                        opacity: statusFilter ? (matches ? 1 : 0.15) : 1,
                                        transition: 'opacity 0.3s ease',
                                    }}
                                >
                                    {/* Selected highlight ring */}
                                    {isSelected && (
                                        <circle r={r + 4} fill="none" stroke="#fbbf24" strokeWidth={2.5} />
                                    )}

                                    {/* Border ring */}
                                    <circle r={r + 1} fill="#334155" />

                                    {/* Clip path for logo */}
                                    <defs>
                                        <clipPath id={clipId}>
                                            <circle r={r} />
                                        </clipPath>
                                    </defs>

                                    {/* Background circle */}
                                    <circle r={r} fill="#1e293b" />

                                    {/* Club logo */}
                                    {node.club_logo && (
                                        <image
                                            href={node.club_logo}
                                            x={-r}
                                            y={-r}
                                            width={r * 2}
                                            height={r * 2}
                                            clipPath={`url(#${clipId})`}
                                            preserveAspectRatio="xMidYMid slice"
                                        />
                                    )}

                                    {/* Player count badge */}
                                    {node.player_count > 1 && (
                                        <g transform={`translate(${r * 0.7}, ${-r * 0.7})`}>
                                            <circle r={Math.max(4, r * 0.4)} fill="#1e293b" stroke="#475569" strokeWidth={0.5} />
                                            <text
                                                textAnchor="middle"
                                                dominantBaseline="central"
                                                fill="#ffffff"
                                                fontSize={Math.max(3, r * 0.35)}
                                                fontWeight="bold"
                                            >
                                                {node.player_count}
                                            </text>
                                        </g>
                                    )}
                                </g>
                            </Marker>
                        )
                    })}

                    {/* Parent marker */}
                    {parentNode && (
                        <Marker coordinates={[parentNode.lng, parentNode.lat]}>
                            {/* Pulsing ring */}
                            <circle fill="none" stroke="#eab308" strokeWidth={1.5}>
                                <animate attributeName="r" from="14" to="22" dur="2s" repeatCount="indefinite" />
                                <animate attributeName="opacity" from="0.5" to="0" dur="2s" repeatCount="indefinite" />
                            </circle>

                            {/* Glow backdrop */}
                            <circle r={14} fill="rgba(234,179,8,0.15)" />

                            {/* Gold border */}
                            <circle r={12} fill="#eab308" stroke="#ca8a04" strokeWidth={1} />

                            {/* Clip path for parent logo */}
                            <defs>
                                <clipPath id="clip-parent">
                                    <circle r={12} />
                                </clipPath>
                            </defs>

                            {/* Parent logo */}
                            {parentNode.club_logo && (
                                <image
                                    href={parentNode.club_logo}
                                    x={-12}
                                    y={-12}
                                    width={24}
                                    height={24}
                                    clipPath="url(#clip-parent)"
                                    preserveAspectRatio="xMidYMid slice"
                                />
                            )}
                        </Marker>
                    )}
                </ZoomableGroup>
            </ComposableMap>

            {/* Legend */}
            <div className="absolute bottom-2 right-2 flex gap-3 text-[10px] text-slate-400 bg-slate-900/80 rounded px-2 py-1">
                <span className="flex items-center gap-1">
                    <svg width="18" height="6">
                        <line
                            x1="0"
                            y1="3"
                            x2="18"
                            y2="3"
                            stroke={LINK_COLORS.loan}
                            strokeWidth="2"
                            strokeDasharray="4 2"
                        />
                    </svg>
                    Loan
                </span>
                <span className="flex items-center gap-1">
                    <svg width="18" height="6">
                        <line
                            x1="0"
                            y1="3"
                            x2="18"
                            y2="3"
                            stroke={LINK_COLORS.permanent}
                            strokeWidth="2"
                        />
                    </svg>
                    Permanent
                </span>
                <span className="flex items-center gap-1">
                    <svg width="18" height="6">
                        <line
                            x1="0"
                            y1="3"
                            x2="18"
                            y2="3"
                            stroke={LINK_COLORS.return}
                            strokeWidth="1.5"
                        />
                    </svg>
                    Return
                </span>
            </div>

            {/* Unmapped clubs indicator */}
            {unmappedCount > 0 && (
                <div className="absolute bottom-2 left-2 text-[10px] text-slate-500">
                    {unmappedCount} club{unmappedCount !== 1 ? 's' : ''} not on
                    map
                </div>
            )}
        </div>
    )
}

export default NetworkMap
