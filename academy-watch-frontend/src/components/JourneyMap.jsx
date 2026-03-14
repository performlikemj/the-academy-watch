import React, { useState, useMemo } from 'react'
import {
    ComposableMap, Geographies, Geography, Marker, Line, ZoomableGroup,
} from 'react-simple-maps'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar'
import { Drawer, DrawerContent, DrawerHeader, DrawerTitle, DrawerDescription } from '@/components/ui/drawer'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Loader2, MapPin, Calendar } from 'lucide-react'
import { useJourney } from '@/contexts/JourneyContext'
import { LEVEL_COLORS } from '@/lib/journey-utils'

const GEO_URL = 'https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json'

/**
 * Calculate zoom center and level from an array of stops.
 * react-simple-maps coordinates are [lng, lat].
 */
function calculateView(stops) {
    const valid = stops.filter(s => s.lat && s.lng)
    if (valid.length === 0) return { center: [0, 30], zoom: 1 }

    const lats = valid.map(s => s.lat)
    const lngs = valid.map(s => s.lng)

    const centerLat = (Math.min(...lats) + Math.max(...lats)) / 2
    const centerLng = (Math.min(...lngs) + Math.max(...lngs)) / 2

    const span = Math.max(
        Math.max(...lats) - Math.min(...lats),
        Math.max(...lngs) - Math.min(...lngs),
        5,
    )

    let zoom = 1
    if (span < 5) zoom = 6
    else if (span < 15) zoom = 4
    else if (span < 30) zoom = 3
    else if (span < 60) zoom = 2

    return { center: [centerLng, centerLat], zoom }
}

export function JourneyMap({ journeyData, loading, error }) {
    const [drawerStop, setDrawerStop] = useState(null)
    const { progressionNodes, selectedNode, selectNode } = useJourney()

    const { stops, pathPairs, view } = useMemo(() => {
        if (!journeyData?.stops) {
            return { stops: [], pathPairs: [], view: { center: [0, 30], zoom: 1 } }
        }

        const validStops = journeyData.stops.filter(s => s.lat && s.lng)

        const pairs = []
        for (let i = 0; i < validStops.length - 1; i++) {
            pairs.push({
                from: [validStops[i].lng, validStops[i].lat],
                to: [validStops[i + 1].lng, validStops[i + 1].lat],
                fromIndex: i,
                toIndex: i + 1,
            })
        }

        return {
            stops: journeyData.stops,
            pathPairs: pairs,
            view: calculateView(validStops),
        }
    }, [journeyData])

    /**
     * Determine if a path segment (between two stop indices) is "visited"
     * based on the selected progression node.
     */
    const isPathVisited = (fromStopIndex, toStopIndex) => {
        if (!selectedNode) return true // no selection = all visited
        // The path is visited if both stops are at or before the selected node's stopIndex
        return fromStopIndex <= selectedNode.stopIndex && toStopIndex <= selectedNode.stopIndex
    }

    /** Is this stop at/before the selected node in the journey? */
    const isStopVisited = (stopIndex) => {
        if (!selectedNode) return true
        return stopIndex <= selectedNode.stopIndex
    }

    /** Is this the stop that the selected node belongs to? */
    const isStopSelected = (stopIndex) => {
        if (!selectedNode) return false
        return stopIndex === selectedNode.stopIndex
    }

    if (loading) {
        return (
            <Card className="w-full h-[400px] flex items-center justify-center">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </Card>
        )
    }

    if (error) {
        return (
            <Card className="w-full h-[400px] flex items-center justify-center">
                <p className="text-muted-foreground">Failed to load journey data</p>
            </Card>
        )
    }

    if (!journeyData || stops.length === 0) {
        return (
            <Card className="w-full h-[400px] flex items-center justify-center">
                <div className="text-center">
                    <MapPin className="h-12 w-12 text-muted-foreground mx-auto mb-2" />
                    <p className="text-muted-foreground">No journey data available</p>
                </div>
            </Card>
        )
    }

    const validStops = stops.filter(s => s.lat && s.lng)

    return (
        <>
            <Card className="w-full overflow-hidden">
                <CardHeader className="pb-2">
                    <CardTitle className="text-lg flex items-center gap-2">
                        <MapPin className="h-5 w-5" />
                        Career Journey
                        {selectedNode && (
                            <Badge variant="outline" className="text-xs ml-2 bg-primary/5 text-primary border-primary/20">
                                {selectedNode.years} — {selectedNode.clubName}
                            </Badge>
                        )}
                    </CardTitle>
                </CardHeader>
                <CardContent className="p-0">
                    <div className="h-[400px] w-full relative">
                        <ComposableMap
                            projection="geoMercator"
                            projectionConfig={{ scale: 150 }}
                            style={{ width: '100%', height: '100%' }}
                        >
                            <ZoomableGroup center={view.center} zoom={view.zoom}>
                                <Geographies geography={GEO_URL}>
                                    {({ geographies }) =>
                                        geographies.map((geo) => (
                                            <Geography
                                                key={geo.rsmKey}
                                                geography={geo}
                                                fill="#e5e7eb"
                                                stroke="#d1d5db"
                                                strokeWidth={0.5}
                                                style={{
                                                    default: { outline: 'none' },
                                                    hover: { outline: 'none', fill: '#d1d5db' },
                                                    pressed: { outline: 'none' },
                                                }}
                                            />
                                        ))
                                    }
                                </Geographies>

                                {/* Journey path lines — trail vs future */}
                                {pathPairs.map((pair, i) => {
                                    const visited = isPathVisited(pair.fromIndex, pair.toIndex)
                                    return (
                                        <Line
                                            key={i}
                                            from={pair.from}
                                            to={pair.to}
                                            stroke={visited ? '#3b82f6' : '#d1d5db'}
                                            strokeWidth={2}
                                            strokeLinecap="round"
                                            strokeDasharray={visited ? 'none' : '5,5'}
                                            strokeOpacity={visited ? 0.8 : 0.3}
                                        />
                                    )
                                })}

                                {/* Club markers */}
                                {validStops.map((stop, index) => {
                                    const isOrigin = index === 0
                                    const isCurrent = index === validStops.length - 1
                                    const primaryLevel = stop.levels?.[0] || 'First Team'
                                    const color = LEVEL_COLORS[primaryLevel] || '#6b7280'

                                    const visited = isStopVisited(index)
                                    const selected = isStopSelected(index)
                                    const r = selected ? 10 : isCurrent ? 8 : isOrigin ? 7 : 5

                                    return (
                                        <Marker
                                            key={`${stop.club_id}-${index}`}
                                            coordinates={[stop.lng, stop.lat]}
                                        >
                                            {/* Pulse ring for selected */}
                                            {selected && (
                                                <circle
                                                    r={14}
                                                    fill="none"
                                                    stroke={color}
                                                    strokeWidth={2}
                                                    opacity={0.4}
                                                >
                                                    <animate
                                                        attributeName="r"
                                                        from="10"
                                                        to="18"
                                                        dur="1.5s"
                                                        repeatCount="indefinite"
                                                    />
                                                    <animate
                                                        attributeName="opacity"
                                                        from="0.5"
                                                        to="0"
                                                        dur="1.5s"
                                                        repeatCount="indefinite"
                                                    />
                                                </circle>
                                            )}
                                            <circle
                                                r={r}
                                                fill={visited ? color : '#d1d5db'}
                                                stroke="white"
                                                strokeWidth={2}
                                                opacity={visited ? 1 : 0.4}
                                                style={{ cursor: 'pointer', transition: 'r 0.2s, opacity 0.3s' }}
                                                onClick={() => {
                                                    // Find a progression node for this stop
                                                    const matchNode = progressionNodes.find(n => n.stopIndex === index)
                                                    if (matchNode) {
                                                        // Toggle: deselect if clicking the already-selected stop
                                                        if (selected && selectedNode) {
                                                            selectNode(null)
                                                        } else {
                                                            selectNode(matchNode)
                                                        }
                                                    }
                                                    setDrawerStop(stop)
                                                }}
                                            />
                                            {isOrigin && visited && (
                                                <text
                                                    textAnchor="middle"
                                                    y={4}
                                                    style={{ fontSize: '7px', fill: 'white', fontWeight: 'bold', pointerEvents: 'none' }}
                                                >
                                                    1
                                                </text>
                                            )}
                                            {isCurrent && visited && (
                                                <text
                                                    textAnchor="middle"
                                                    y={3}
                                                    style={{ fontSize: '7px', fill: 'white', pointerEvents: 'none' }}
                                                >
                                                    ★
                                                </text>
                                            )}
                                        </Marker>
                                    )
                                })}
                            </ZoomableGroup>
                        </ComposableMap>

                        {/* Legend */}
                        <div className="absolute bottom-2 left-2 bg-card/90 rounded-lg p-2 text-xs shadow-md z-10">
                            <div className="flex flex-wrap gap-2">
                                <div className="flex items-center gap-1">
                                    <div className="w-3 h-3 rounded-full bg-purple-500" />
                                    <span>Youth</span>
                                </div>
                                <div className="flex items-center gap-1">
                                    <div className="w-3 h-3 rounded-full bg-green-500" />
                                    <span>First Team</span>
                                </div>
                                <div className="flex items-center gap-1">
                                    <div className="w-3 h-3 rounded-full bg-amber-500" />
                                    <span>International</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </CardContent>
            </Card>

            {/* Stop Detail Drawer */}
            <Drawer open={!!drawerStop} onOpenChange={(open) => !open && setDrawerStop(null)}>
                <DrawerContent>
                    <DrawerHeader>
                        <div className="flex items-center gap-3">
                            {drawerStop?.club_logo && (
                                <Avatar className="h-12 w-12">
                                    <AvatarImage src={drawerStop.club_logo} alt={drawerStop?.club_name} />
                                    <AvatarFallback>{drawerStop?.club_name?.[0]}</AvatarFallback>
                                </Avatar>
                            )}
                            <div>
                                <DrawerTitle>{drawerStop?.club_name}</DrawerTitle>
                                <DrawerDescription className="flex items-center gap-1">
                                    <Calendar className="h-3 w-3" />
                                    {selectedNode ? selectedNode.years : drawerStop?.years}
                                    {drawerStop?.city && ` \u2022 ${drawerStop.city}`}
                                    {drawerStop?.country && `, ${drawerStop.country}`}
                                </DrawerDescription>
                            </div>
                        </div>
                    </DrawerHeader>

                    <div className="p-4 space-y-4">
                        {/* Levels */}
                        <div>
                            <h4 className="text-sm font-medium text-muted-foreground mb-2">Levels</h4>
                            <div className="flex flex-wrap gap-2">
                                {drawerStop?.levels?.map(level => (
                                    <Badge
                                        key={level}
                                        style={{ backgroundColor: LEVEL_COLORS[level] || '#6b7280' }}
                                        className="text-white"
                                    >
                                        {level}
                                    </Badge>
                                ))}
                            </div>
                        </div>

                        {/* Stats Summary — show season stats if a node is selected */}
                        <div className="grid grid-cols-3 gap-4">
                            <div className="text-center p-3 bg-muted rounded-lg">
                                <div className="text-2xl font-bold">{selectedNode ? selectedNode.stats.apps : (drawerStop?.total_apps || 0)}</div>
                                <div className="text-xs text-muted-foreground">Appearances</div>
                            </div>
                            <div className="text-center p-3 bg-muted rounded-lg">
                                <div className="text-2xl font-bold">{selectedNode ? selectedNode.stats.goals : (drawerStop?.total_goals || 0)}</div>
                                <div className="text-xs text-muted-foreground">Goals</div>
                            </div>
                            <div className="text-center p-3 bg-muted rounded-lg">
                                <div className="text-2xl font-bold">{selectedNode ? selectedNode.stats.assists : (drawerStop?.total_assists || 0)}</div>
                                <div className="text-xs text-muted-foreground">Assists</div>
                            </div>
                        </div>

                        {/* Level Breakdown */}
                        {!selectedNode && drawerStop?.breakdown && Object.keys(drawerStop.breakdown).length > 0 && (
                            <div>
                                <h4 className="text-sm font-medium text-muted-foreground mb-2">By Level</h4>
                                <div className="space-y-2">
                                    {Object.entries(drawerStop.breakdown)
                                        .sort(([a], [b]) => (LEVEL_COLORS[b] ? 1 : 0) - (LEVEL_COLORS[a] ? 1 : 0))
                                        .map(([level, stats]) => (
                                            <div key={level} className="flex items-center justify-between p-2 bg-muted/50 rounded">
                                                <Badge
                                                    variant="outline"
                                                    style={{ borderColor: LEVEL_COLORS[level] || '#6b7280', color: LEVEL_COLORS[level] || '#6b7280' }}
                                                >
                                                    {level}
                                                </Badge>
                                                <span className="text-sm">
                                                    {stats.apps} apps &bull; {stats.goals}G &bull; {stats.assists}A
                                                </span>
                                            </div>
                                        ))
                                    }
                                </div>
                            </div>
                        )}

                        {/* Competitions — filtered to selected season when applicable */}
                        {(() => {
                            const comps = selectedNode
                                ? selectedNode.competitions
                                : drawerStop?.competitions
                            if (!comps || comps.length === 0) return null
                            return (
                                <div>
                                    <h4 className="text-sm font-medium text-muted-foreground mb-2">
                                        Competitions{selectedNode ? ` (${selectedNode.years})` : ''}
                                    </h4>
                                    <ScrollArea className="h-[200px]">
                                        <div className="space-y-2">
                                            {comps.map((comp, idx) => (
                                                <div key={idx} className="flex items-center justify-between p-2 border rounded text-sm">
                                                    <div>
                                                        <div className="font-medium">{comp.league}</div>
                                                        <div className="text-xs text-muted-foreground">{comp.season}/{comp.season + 1}</div>
                                                    </div>
                                                    <div className="text-right">
                                                        <div>{comp.apps} apps</div>
                                                        <div className="text-xs text-muted-foreground">
                                                            {comp.goals}G {comp.assists}A
                                                        </div>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    </ScrollArea>
                                </div>
                            )
                        })()}
                    </div>
                </DrawerContent>
            </Drawer>
        </>
    )
}

export default JourneyMap
