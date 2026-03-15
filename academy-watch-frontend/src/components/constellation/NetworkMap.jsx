import { useRef, useEffect, useState, useMemo, useCallback } from 'react'
import {
    ComposableMap, Geographies, Geography, Marker, Line, ZoomableGroup,
} from 'react-simple-maps'
import { calculateView } from '@/lib/map-utils'
import { LINK_COLORS } from './constellation-utils'
import { ChevronRight } from 'lucide-react'

const GEO_URL = 'https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json'

// Dot colors by dominant link type
const DOT_COLORS = {
    loan: '#f59e0b',       // amber-500
    permanent: '#94a3b8',  // slate-400
    return: '#34d399',     // emerald-400
}

const ARC_COLORS = {
    loan: 'rgba(251,191,36,0.45)',
    permanent: 'rgba(148,163,184,0.35)',
    return: 'rgba(74,222,128,0.35)',
}

function getDotColor(node) {
    const types = node.link_types || []
    if (types.includes('loan')) return DOT_COLORS.loan
    if (types.includes('return')) return DOT_COLORS.return
    if (types.includes('permanent')) return DOT_COLORS.permanent
    return DOT_COLORS.loan
}

/**
 * "Mission Control" geographic network map.
 * Small radar-blip markers on a dark tactical map with faint arc trails.
 */
export function NetworkMap({ data, onNodeClick, selectedNode, statusFilter }) {
    const containerRef = useRef(null)
    const [dimensions, setDimensions] = useState({ width: 800, height: 500 })
    const [hoveredNode, setHoveredNode] = useState(null)
    const [tooltipPos, setTooltipPos] = useState(null)
    const [selectedCountry, setSelectedCountry] = useState(null)

    // Responsive sizing
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

    // Split nodes into mappable (have coordinates) and unmapped
    const mappedNodes = useMemo(() => {
        if (!data?.nodes?.length) return []
        return data.nodes.filter(n => n.lat && n.lng)
    }, [data])

    const view = useMemo(() => calculateView(mappedNodes), [mappedNodes])

    // Build lookup from node index to mapped node
    const nodeByIndex = useMemo(() => {
        if (!data?.nodes) return new Map()
        const map = new Map()
        data.nodes.forEach((node, i) => {
            if (node.lat && node.lng) map.set(i, node)
        })
        return map
    }, [data])

    // Build renderable arcs
    const arcs = useMemo(() => {
        if (!data?.links?.length) return []
        return data.links
            .map((link) => {
                const sourceNode = nodeByIndex.get(link.source)
                const targetNode = nodeByIndex.get(link.target)
                if (!sourceNode || !targetNode) return null
                return {
                    ...link,
                    from: [sourceNode.lng, sourceNode.lat],
                    to: [targetNode.lng, targetNode.lat],
                }
            })
            .filter(Boolean)
    }, [data, nodeByIndex])

    const parentNode = useMemo(() => mappedNodes.find(n => n.is_parent) || null, [mappedNodes])
    const destNodes = useMemo(() => mappedNodes.filter(n => !n.is_parent), [mappedNodes])

    const handleMarkerClick = useCallback((node) => {
        if (onNodeClick) onNodeClick(node)
    }, [onNodeClick])

    // Tooltip positioning via mouse event
    const handleMouseEnter = useCallback((node, e) => {
        setHoveredNode(node)
        const rect = containerRef.current?.getBoundingClientRect()
        if (rect) {
            setTooltipPos({
                x: e.clientX - rect.left,
                y: e.clientY - rect.top,
            })
        }
    }, [])

    const handleMouseLeave = useCallback(() => {
        setHoveredNode(null)
        setTooltipPos(null)
    }, [])

    // Status filter lookups
    const statusClubMap = useMemo(() => {
        if (!data?.all_players) return {}
        const map = {}
        for (const player of data.all_players) {
            if (!player.status) continue
            if (!map[player.status]) map[player.status] = new Set()
            for (const stop of (player.journey_path || [])) {
                map[player.status].add(stop.club_api_id)
            }
        }
        return map
    }, [data?.all_players])

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

    const nodeMatchesFilter = useCallback((node) => {
        if (!statusFilter) return true
        const clubSet = statusClubMap[statusFilter]
        return clubSet ? clubSet.has(node.club_api_id) : false
    }, [statusFilter, statusClubMap])

    const linkMatchesFilter = useCallback((link) => {
        if (!statusFilter) return true
        const playerSet = statusPlayerMap[statusFilter]
        if (!playerSet) return false
        return link.players?.some(p => playerSet.has(p.player_api_id)) ?? false
    }, [statusFilter, statusPlayerMap])

    // Group ALL non-parent nodes by country for the country browser
    const countryGroups = useMemo(() => {
        if (!data?.nodes) return []
        const groups = {}
        for (const node of data.nodes) {
            if (node.is_parent) continue
            const country = node.country || 'Unknown'
            if (!groups[country]) groups[country] = { country, clubs: [], totalPlayers: 0 }
            groups[country].clubs.push(node)
            groups[country].totalPlayers += node.player_count || 0
        }
        return Object.values(groups).sort((a, b) => b.totalPlayers - a.totalPlayers)
    }, [data?.nodes])

    // Clubs for the selected country
    const selectedCountryClubs = useMemo(() => {
        if (!selectedCountry) return []
        const group = countryGroups.find(g => g.country === selectedCountry)
        return (group?.clubs || []).sort((a, b) => (b.player_count || 0) - (a.player_count || 0))
    }, [selectedCountry, countryGroups])

    if (!data?.nodes?.length) return null

    return (
        <div className="space-y-0">
            {/* Map container */}
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

                        {/* Arc lines — thin, faint trails */}
                        {arcs.map((arc, i) => {
                            const matches = linkMatchesFilter(arc)
                            return (
                                <Line
                                    key={`line-${i}`}
                                    from={arc.from}
                                    to={arc.to}
                                    stroke={ARC_COLORS[arc.link_type] || ARC_COLORS.loan}
                                    strokeWidth={Math.max(0.5, Math.min(2, arc.player_count * 0.5))}
                                    strokeLinecap="round"
                                    strokeDasharray={arc.link_type === 'loan' ? '4 2' : undefined}
                                    strokeOpacity={statusFilter ? (matches ? 0.7 : 0.06) : 0.7}
                                    style={{ transition: 'stroke-opacity 0.3s ease' }}
                                />
                            )
                        })}

                        {/* Destination markers — small colored dots */}
                        {destNodes.map((node) => {
                            const r = Math.max(3, Math.min(6, Math.sqrt(node.player_count || 1) * 2))
                            const isSelected = selectedNode?.club_api_id === node.club_api_id
                            const matches = nodeMatchesFilter(node)
                            const color = getDotColor(node)

                            return (
                                <Marker
                                    key={`dest-${node.club_api_id}`}
                                    coordinates={[node.lng, node.lat]}
                                >
                                    <g
                                        onClick={() => handleMarkerClick(node)}
                                        onMouseEnter={(e) => handleMouseEnter(node, e.nativeEvent)}
                                        onMouseLeave={handleMouseLeave}
                                        style={{
                                            cursor: 'pointer',
                                            opacity: statusFilter ? (matches ? 1 : 0.12) : 1,
                                            transition: 'opacity 0.3s ease',
                                        }}
                                    >
                                        {/* Selected ring */}
                                        {isSelected && (
                                            <circle r={r + 3} fill="none" stroke="#fbbf24" strokeWidth={1.5} />
                                        )}
                                        {/* Glow */}
                                        <circle r={r + 1.5} fill={color} opacity={0.2} />
                                        {/* Dot */}
                                        <circle r={r} fill={color} />
                                    </g>
                                </Marker>
                            )
                        })}

                        {/* Parent marker — golden radar hub */}
                        {parentNode && (
                            <Marker coordinates={[parentNode.lng, parentNode.lat]}>
                                <g
                                    onClick={() => handleMarkerClick(parentNode)}
                                    onMouseEnter={(e) => handleMouseEnter(parentNode, e.nativeEvent)}
                                    onMouseLeave={handleMouseLeave}
                                    style={{ cursor: 'pointer' }}
                                >
                                    {/* Double radar pulse — pointer-events none so clicks pass through to hub dot */}
                                    <circle fill="none" stroke="#eab308" strokeWidth={1} pointerEvents="none">
                                        <animate attributeName="r" from="8" to="20" dur="2.5s" repeatCount="indefinite" />
                                        <animate attributeName="opacity" from="0.4" to="0" dur="2.5s" repeatCount="indefinite" />
                                    </circle>
                                    <circle fill="none" stroke="#eab308" strokeWidth={0.8} pointerEvents="none">
                                        <animate attributeName="r" from="8" to="20" dur="2.5s" begin="1.25s" repeatCount="indefinite" />
                                        <animate attributeName="opacity" from="0.3" to="0" dur="2.5s" begin="1.25s" repeatCount="indefinite" />
                                    </circle>
                                    {/* Glow */}
                                    <circle r={7} fill="rgba(234,179,8,0.15)" />
                                    {/* Hub dot */}
                                    <circle r={6} fill="#eab308" />
                                </g>
                            </Marker>
                        )}
                    </ZoomableGroup>
                </ComposableMap>

                {/* Hover tooltip */}
                {hoveredNode && tooltipPos && (
                    <div
                        className="absolute pointer-events-none z-20 bg-slate-800 border border-slate-600 text-white text-xs rounded-lg px-3 py-2 shadow-xl"
                        style={{
                            left: tooltipPos.x,
                            top: tooltipPos.y - 48,
                            transform: 'translateX(-50%)',
                        }}
                    >
                        <div className="font-semibold text-slate-100">{hoveredNode.club_name}</div>
                        <div className="text-slate-400">
                            {hoveredNode.player_count} player{hoveredNode.player_count !== 1 ? 's' : ''}
                            {hoveredNode.city && ` · ${hoveredNode.city}`}
                        </div>
                    </div>
                )}

                {/* Legend */}
                <div className="absolute bottom-2 right-2 flex gap-3 text-[10px] text-slate-400 bg-slate-900/80 rounded px-2 py-1">
                    <span className="flex items-center gap-1">
                        <span className="inline-block w-2 h-2 rounded-full" style={{ backgroundColor: DOT_COLORS.loan }} />
                        Loan
                    </span>
                    <span className="flex items-center gap-1">
                        <span className="inline-block w-2 h-2 rounded-full" style={{ backgroundColor: DOT_COLORS.permanent }} />
                        Permanent
                    </span>
                    <span className="flex items-center gap-1">
                        <span className="inline-block w-2 h-2 rounded-full" style={{ backgroundColor: DOT_COLORS.return }} />
                        Return
                    </span>
                </div>
            </div>

            {/* Country browser */}
            {countryGroups.length > 0 && (
                <div className="mt-3 space-y-2">
                    {/* Country chips */}
                    <div className="flex gap-1.5 overflow-x-auto pb-1 [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">
                        {countryGroups.map(group => (
                            <button
                                key={group.country}
                                type="button"
                                onClick={() => setSelectedCountry(prev => prev === group.country ? null : group.country)}
                                className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium whitespace-nowrap transition-colors border ${
                                    selectedCountry === group.country
                                        ? 'bg-slate-700 text-white border-slate-500'
                                        : 'bg-slate-800/50 text-slate-400 border-slate-700/50 hover:bg-slate-700/50'
                                }`}
                            >
                                {group.country}
                                <span className="opacity-60">({group.clubs.length})</span>
                            </button>
                        ))}
                    </div>

                    {/* Clubs list for selected country */}
                    {selectedCountry && selectedCountryClubs.length > 0 && (
                        <div className="bg-slate-800/30 rounded-lg border border-slate-700/50 max-h-[240px] overflow-y-auto">
                            {selectedCountryClubs.map(node => {
                                const isSelected = selectedNode?.club_api_id === node.club_api_id
                                return (
                                    <button
                                        key={node.club_api_id}
                                        type="button"
                                        onClick={() => handleMarkerClick(node)}
                                        className={`flex items-center gap-2.5 w-full px-3 py-2 text-left text-xs transition-colors border-b border-slate-700/30 last:border-b-0 ${
                                            isSelected
                                                ? 'bg-slate-700/50 text-white'
                                                : 'hover:bg-slate-700/30 text-slate-300'
                                        }`}
                                    >
                                        <span
                                            className="w-2 h-2 rounded-full shrink-0"
                                            style={{ backgroundColor: getDotColor(node) }}
                                        />
                                        <span className="flex-1 truncate">
                                            {node.club_name}
                                        </span>
                                        <span className="text-slate-500 shrink-0 tabular-nums">
                                            {node.player_count} {node.player_count === 1 ? 'player' : 'players'}
                                        </span>
                                        <ChevronRight className="h-3 w-3 text-slate-600 shrink-0" />
                                    </button>
                                )
                            })}
                        </div>
                    )}
                </div>
            )}
        </div>
    )
}

export default NetworkMap
