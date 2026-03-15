import { useRef, useEffect, useState, useMemo, useCallback } from 'react'
import {
    ComposableMap, Geographies, Geography, Marker, Line, ZoomableGroup,
} from 'react-simple-maps'
import { calculateView } from '@/lib/map-utils'
import { ChevronRight } from 'lucide-react'

const GEO_URL = 'https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json'

const ARC_COLOR = 'rgba(251,191,36,0.35)'

function getDotColor(node) {
    const types = node.link_types || []
    if (types.includes('loan')) return '#f59e0b'
    if (types.includes('return')) return '#34d399'
    if (types.includes('permanent')) return '#94a3b8'
    return '#f59e0b'
}

/**
 * Geographic network map with country-level markers.
 * One dot per country, clickable to browse clubs within that country.
 */
export function NetworkMap({ data, onNodeClick, selectedNode }) {
    const containerRef = useRef(null)
    const [dimensions, setDimensions] = useState({ width: 800, height: 500 })
    const [hoveredCountry, setHoveredCountry] = useState(null)
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

    // Parent node
    const parentNode = useMemo(() => {
        if (!data?.nodes) return null
        return data.nodes.find(n => n.is_parent && n.lat && n.lng) || null
    }, [data])

    // Group ALL non-parent nodes by country
    const countryGroups = useMemo(() => {
        if (!data?.nodes) return []
        const groups = {}
        for (const node of data.nodes) {
            if (node.is_parent) continue
            const country = node.country || 'Unknown'
            if (!groups[country]) groups[country] = { country, clubs: [], totalPlayers: 0, lats: [], lngs: [] }
            groups[country].clubs.push(node)
            groups[country].totalPlayers += node.player_count || 0
            if (node.lat && node.lng) {
                groups[country].lats.push(node.lat)
                groups[country].lngs.push(node.lng)
            }
        }
        return Object.values(groups).sort((a, b) => b.totalPlayers - a.totalPlayers)
    }, [data?.nodes])

    // Country markers for the map (only those with at least one geocoded club)
    const countryMapMarkers = useMemo(() => {
        return countryGroups
            .filter(g => g.lats.length > 0)
            .map(g => ({
                country: g.country,
                clubs: g.clubs.length,
                players: g.totalPlayers,
                lat: g.lats.reduce((a, b) => a + b, 0) / g.lats.length,
                lng: g.lngs.reduce((a, b) => a + b, 0) / g.lngs.length,
            }))
    }, [countryGroups])

    // View to fit all country centroids + parent
    const view = useMemo(() => {
        const points = countryMapMarkers.map(c => ({ lat: c.lat, lng: c.lng }))
        if (parentNode) points.push({ lat: parentNode.lat, lng: parentNode.lng })
        return calculateView(points)
    }, [countryMapMarkers, parentNode])

    // Clubs for the selected country
    const selectedCountryClubs = useMemo(() => {
        if (!selectedCountry) return []
        const group = countryGroups.find(g => g.country === selectedCountry)
        return (group?.clubs || []).sort((a, b) => (b.player_count || 0) - (a.player_count || 0))
    }, [selectedCountry, countryGroups])

    const handleMarkerClick = useCallback((node) => {
        if (onNodeClick) onNodeClick(node)
    }, [onNodeClick])

    const handleCountryHover = useCallback((cd, e) => {
        setHoveredCountry(cd)
        const rect = containerRef.current?.getBoundingClientRect()
        if (rect) {
            setTooltipPos({ x: e.clientX - rect.left, y: e.clientY - rect.top })
        }
    }, [])

    const handleCountryLeave = useCallback(() => {
        setHoveredCountry(null)
        setTooltipPos(null)
    }, [])

    if (!data?.nodes?.length) return null

    return (
        <div className="space-y-0">
            {/* Map */}
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

                        {/* Arc lines — one per country, from parent to country centroid */}
                        {parentNode && countryMapMarkers.map((cd) => (
                            <Line
                                key={`arc-${cd.country}`}
                                from={[parentNode.lng, parentNode.lat]}
                                to={[cd.lng, cd.lat]}
                                stroke={ARC_COLOR}
                                strokeWidth={Math.max(0.5, Math.min(2, Math.sqrt(cd.players) * 0.4))}
                                strokeLinecap="round"
                                strokeDasharray="4 2"
                                strokeOpacity={selectedCountry ? (selectedCountry === cd.country ? 0.7 : 0.08) : 0.5}
                                style={{ transition: 'stroke-opacity 0.3s ease' }}
                            />
                        ))}

                        {/* Country markers */}
                        {countryMapMarkers.map((cd) => {
                            const r = Math.max(4, Math.min(8, Math.sqrt(cd.clubs) * 1.2))
                            const isActive = selectedCountry === cd.country

                            return (
                                <Marker key={`country-${cd.country}`} coordinates={[cd.lng, cd.lat]}>
                                    <g
                                        onClick={() => setSelectedCountry(prev => prev === cd.country ? null : cd.country)}
                                        onMouseEnter={(e) => handleCountryHover(cd, e.nativeEvent)}
                                        onMouseLeave={handleCountryLeave}
                                        style={{
                                            cursor: 'pointer',
                                            opacity: selectedCountry ? (isActive ? 1 : 0.25) : 1,
                                            transition: 'opacity 0.3s ease',
                                        }}
                                    >
                                        {/* Active ring */}
                                        {isActive && (
                                            <circle r={r + 3} fill="none" stroke="#fbbf24" strokeWidth={1.5} />
                                        )}
                                        {/* Glow */}
                                        <circle r={r + 1.5} fill="#f59e0b" opacity={0.15} />
                                        {/* Dot */}
                                        <circle r={r} fill="#f59e0b" opacity={0.85} />
                                        {/* Country label */}
                                        <text
                                            y={r + 10}
                                            textAnchor="middle"
                                            fill="#94a3b8"
                                            fontSize={7}
                                            fontWeight="500"
                                            pointerEvents="none"
                                        >
                                            {cd.country}
                                        </text>
                                    </g>
                                </Marker>
                            )
                        })}

                        {/* Parent marker — golden radar hub */}
                        {parentNode && (
                            <Marker coordinates={[parentNode.lng, parentNode.lat]}>
                                <g
                                    onClick={() => handleMarkerClick(parentNode)}
                                    style={{ cursor: 'pointer' }}
                                >
                                    {/* Double radar pulse */}
                                    <circle fill="none" stroke="#eab308" strokeWidth={1} pointerEvents="none">
                                        <animate attributeName="r" from="8" to="18" dur="2.5s" repeatCount="indefinite" />
                                        <animate attributeName="opacity" from="0.4" to="0" dur="2.5s" repeatCount="indefinite" />
                                    </circle>
                                    <circle fill="none" stroke="#eab308" strokeWidth={0.8} pointerEvents="none">
                                        <animate attributeName="r" from="8" to="18" dur="2.5s" begin="1.25s" repeatCount="indefinite" />
                                        <animate attributeName="opacity" from="0.3" to="0" dur="2.5s" begin="1.25s" repeatCount="indefinite" />
                                    </circle>
                                    {/* Glow */}
                                    <circle r={7} fill="rgba(234,179,8,0.15)" />
                                    {/* Hub dot */}
                                    <circle r={5} fill="#eab308" />
                                </g>
                            </Marker>
                        )}
                    </ZoomableGroup>
                </ComposableMap>

                {/* Hover tooltip */}
                {hoveredCountry && tooltipPos && (
                    <div
                        className="absolute pointer-events-none z-20 bg-slate-800 border border-slate-600 text-white text-xs rounded-lg px-3 py-2 shadow-xl"
                        style={{
                            left: tooltipPos.x,
                            top: tooltipPos.y - 48,
                            transform: 'translateX(-50%)',
                        }}
                    >
                        <div className="font-semibold text-slate-100">{hoveredCountry.country}</div>
                        <div className="text-slate-400">
                            {hoveredCountry.clubs} club{hoveredCountry.clubs !== 1 ? 's' : ''}
                            {' · '}
                            {hoveredCountry.players} player{hoveredCountry.players !== 1 ? 's' : ''}
                        </div>
                    </div>
                )}
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
                                const isNodeSelected = selectedNode?.club_api_id === node.club_api_id
                                return (
                                    <button
                                        key={node.club_api_id}
                                        type="button"
                                        onClick={() => handleMarkerClick(node)}
                                        className={`flex items-center gap-2.5 w-full px-3 py-2 text-left text-xs transition-colors border-b border-slate-700/30 last:border-b-0 ${
                                            isNodeSelected
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
