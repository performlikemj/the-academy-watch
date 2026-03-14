import React, { useRef, useEffect, useState, useCallback } from 'react'
import { ArrowRight, Star } from 'lucide-react'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useJourney } from '@/contexts/JourneyContext'
import { LEVEL_COLORS } from '@/lib/journey-utils'

/**
 * Horizontal career journey strip — replaces JourneyMap.
 * Shows one node per club (stop-level, not season-level) with logos,
 * names, years, level badges, and stats connected by colored lines.
 * Reads from JourneyContext directly (no props needed).
 */
export function JourneyStrip() {
    const { journeyData, progressionNodes, selectedNode, selectNode } = useJourney()
    const scrollRef = useRef(null)
    const selectedStopRef = useRef(null)
    const [canScrollLeft, setCanScrollLeft] = useState(false)
    const [canScrollRight, setCanScrollRight] = useState(false)

    const stops = journeyData?.stops || []

    const updateScrollIndicators = useCallback(() => {
        const el = scrollRef.current
        if (!el) return
        setCanScrollLeft(el.scrollLeft > 4)
        setCanScrollRight(el.scrollLeft < el.scrollWidth - el.clientWidth - 4)
    }, [])

    // Auto-scroll to the selected stop
    useEffect(() => {
        if (selectedStopRef.current && scrollRef.current) {
            selectedStopRef.current.scrollIntoView({
                behavior: 'smooth',
                inline: 'center',
                block: 'nearest',
            })
        }
    }, [selectedNode])

    // Track scroll position for fade indicators
    useEffect(() => {
        const el = scrollRef.current
        if (!el) return
        updateScrollIndicators()
        el.addEventListener('scroll', updateScrollIndicators, { passive: true })
        const ro = new ResizeObserver(updateScrollIndicators)
        ro.observe(el)
        return () => {
            el.removeEventListener('scroll', updateScrollIndicators)
            ro.disconnect()
        }
    }, [stops.length, updateScrollIndicators])

    if (!stops.length) return null

    /** Which stop index is currently selected? */
    const selectedStopIndex = selectedNode?.stopIndex ?? null

    /** Is a stop at or before the selected node? */
    const isStopVisited = (stopIndex) => {
        if (selectedStopIndex == null) return true
        return stopIndex <= selectedStopIndex
    }

    /** Click handler — find the first progressionNode matching this stop and select it. */
    const handleStopClick = (stopIndex) => {
        const isAlreadySelected = selectedStopIndex === stopIndex
        if (isAlreadySelected && selectedNode) {
            selectNode(null)
            return
        }
        const matchNode = progressionNodes.find(n => n.stopIndex === stopIndex)
        if (matchNode) selectNode(matchNode)
    }

    // Collect unique levels across all stops for the legend
    const allLevels = [...new Set(stops.flatMap(s => s.levels || []))]
    const legendLevels = allLevels.filter(l => LEVEL_COLORS[l])

    return (
        <Card className="w-full max-w-full overflow-hidden">
            <CardHeader className="pb-2">
                <CardTitle className="text-lg flex items-center gap-2">
                    <ArrowRight className="h-5 w-5" />
                    Career Journey
                    {selectedNode && (
                        <Badge variant="outline" className="text-xs ml-2 bg-primary/5 text-primary border-primary/20">
                            {selectedNode.years} — {selectedNode.clubName}
                        </Badge>
                    )}
                </CardTitle>
            </CardHeader>
            <CardContent className="pb-4">
                {/* Scrollable strip with fade indicators */}
                <div className="relative">
                    {canScrollLeft && (
                        <div className="absolute left-0 top-0 bottom-0 w-6 bg-gradient-to-r from-card to-transparent z-10 pointer-events-none" />
                    )}
                    {canScrollRight && (
                        <div className="absolute right-0 top-0 bottom-0 w-6 bg-gradient-to-l from-card to-transparent z-10 pointer-events-none" />
                    )}
                    <div
                        ref={scrollRef}
                        className="flex items-start gap-0 overflow-x-auto scrollbar-hide pb-2"
                    >
                        {stops.map((stop, index) => {
                            const isFirst = index === 0
                            const isLast = index === stops.length - 1
                            const isSelected = selectedStopIndex === index
                            const visited = isStopVisited(index)
                            const primaryLevel = stop.levels?.[0] || 'First Team'
                            const color = LEVEL_COLORS[primaryLevel] || '#6b7280'

                            // Line color is based on the destination stop's primary level
                            const nextStop = stops[index + 1]
                            const nextLevel = nextStop?.levels?.[0] || 'First Team'
                            const lineColor = LEVEL_COLORS[nextLevel] || '#6b7280'

                            const totalApps = stop.total_apps || 0
                            const totalGoals = stop.total_goals || 0
                            const totalAssists = stop.total_assists || 0

                            return (
                                <div key={`${stop.club_id}-${index}`} className="flex items-start flex-shrink-0">
                                    {/* Stop node */}
                                    <button
                                        ref={isSelected ? selectedStopRef : null}
                                        onClick={() => handleStopClick(index)}
                                        aria-label={`${stop.club_name} (${stop.years}) — ${totalApps} apps, ${totalGoals} goals, ${totalAssists} assists`}
                                        className={`flex flex-col items-center text-center min-w-[80px] sm:min-w-[110px] max-w-[110px] sm:max-w-[130px] px-1.5 sm:px-2 py-2 rounded-lg transition-[background-color,box-shadow,opacity] duration-200 cursor-pointer focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none ${
                                            isSelected
                                                ? 'bg-primary/5 ring-2 ring-primary/20 ring-offset-1'
                                                : visited
                                                    ? 'hover:bg-secondary'
                                                    : 'opacity-40 hover:opacity-60'
                                        }`}
                                    >
                                        {/* Logo */}
                                        <div className="relative">
                                            <Avatar className="h-8 w-8 sm:h-10 sm:w-10 mb-1.5">
                                                <AvatarImage src={stop.club_logo} alt={stop.club_name} />
                                                <AvatarFallback
                                                    className="text-xs font-bold text-white"
                                                    style={{ backgroundColor: color }}
                                                >
                                                    {stop.club_name?.charAt(0) || '?'}
                                                </AvatarFallback>
                                            </Avatar>
                                            {isLast && (
                                                <Star className="absolute -top-1 -right-1 h-3.5 w-3.5 text-amber-500 fill-amber-500" />
                                            )}
                                        </div>

                                        {/* Club name */}
                                        <span className="text-[11px] sm:text-xs font-semibold leading-tight truncate w-full">
                                            {stop.club_name}
                                        </span>

                                        {/* Years */}
                                        <span className="text-[10px] text-muted-foreground mt-0.5">
                                            {stop.years}
                                        </span>

                                        {/* Level badges */}
                                        <div className="flex flex-wrap justify-center gap-0.5 mt-1">
                                            {(stop.levels || [primaryLevel]).map((level, idx) => (
                                                <Badge
                                                    key={idx}
                                                    className="text-[9px] text-white px-1 py-0 leading-tight"
                                                    style={{ backgroundColor: LEVEL_COLORS[level] || '#6b7280' }}
                                                >
                                                    {level}
                                                </Badge>
                                            ))}
                                            {stop.entry_types?.includes('development') && (
                                                <Badge className="text-[9px] px-1 py-0 leading-tight bg-orange-100 text-orange-700 border border-orange-300">
                                                    Dev
                                                </Badge>
                                            )}
                                            {stop.entry_types?.includes('integration') && (
                                                <Badge className="text-[9px] px-1 py-0 leading-tight bg-cyan-100 text-cyan-700 border border-cyan-300">
                                                    New Signing
                                                </Badge>
                                            )}
                                        </div>

                                        {/* Stats */}
                                        <span className="text-[10px] text-muted-foreground mt-1 tabular-nums">
                                            {totalApps} apps
                                            {totalGoals > 0 && <> &middot; {totalGoals}G</>}
                                            {totalAssists > 0 && <> &middot; {totalAssists}A</>}
                                        </span>

                                        {/* Origin / Current badge */}
                                        {isFirst && (
                                            <Badge variant="outline" className="text-[9px] mt-1 px-1 py-0 border-purple-300 text-purple-600">
                                                Origin
                                            </Badge>
                                        )}
                                        {isLast && !isFirst && (
                                            <Badge variant="outline" className="text-[9px] mt-1 px-1 py-0 border-green-300 text-green-600">
                                                Current
                                            </Badge>
                                        )}
                                    </button>

                                    {/* Connecting line to next stop */}
                                    {!isLast && (
                                        <div className="flex items-center self-center mt-5">
                                            <div
                                                className="h-0.5 w-5 sm:w-8 transition-colors duration-300"
                                                style={isStopVisited(index + 1)
                                                    ? { backgroundColor: lineColor, opacity: 0.8 }
                                                    : { backgroundImage: `repeating-linear-gradient(90deg, #d6d3d1 0px, #d6d3d1 4px, transparent 4px, transparent 8px)`, opacity: 0.5 }
                                                }
                                            />
                                        </div>
                                    )}
                                </div>
                            )
                        })}
                    </div>
                </div>

                {/* Legend */}
                {legendLevels.length > 0 && (
                    <div className="flex flex-wrap gap-3 mt-2 pt-2 border-t border-border text-xs text-muted-foreground">
                        {legendLevels.map(level => (
                            <div key={level} className="flex items-center gap-1">
                                <div
                                    className="w-3 h-0.5 rounded"
                                    style={{ backgroundColor: LEVEL_COLORS[level] }}
                                />
                                <span>{level}</span>
                            </div>
                        ))}
                    </div>
                )}
            </CardContent>
        </Card>
    )
}

export default JourneyStrip
