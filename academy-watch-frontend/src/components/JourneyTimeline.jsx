import React, { useRef, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Loader2, MapPin, Star, Flag, TrendingUp } from 'lucide-react'
import { useJourney } from '@/contexts/JourneyContext'
import { LEVEL_COLORS } from '@/lib/journey-utils'

const LEVEL_ICONS = {
    'U18': '🌱',
    'U19': '🌿',
    'U21': '🌳',
    'U23': '🌲',
    'Reserve': '📋',
    'First Team': '⭐',
    'International': '🌍',
    'International Youth': '🏆',
}

export function JourneyTimeline({ journeyData, loading, error }) {
    const { progressionNodes, selectedNode, selectNode, isNodeVisited } = useJourney()
    const cardRefs = useRef({})

    // Auto-scroll to selected node
    useEffect(() => {
        if (selectedNode && cardRefs.current[selectedNode.id]) {
            cardRefs.current[selectedNode.id].scrollIntoView({
                behavior: 'smooth',
                block: 'center',
            })
        }
    }, [selectedNode])

    if (loading) {
        return (
            <Card className="w-full">
                <CardContent className="flex items-center justify-center py-8">
                    <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </CardContent>
            </Card>
        )
    }

    if (error) {
        return (
            <Card className="w-full">
                <CardContent className="flex items-center justify-center py-8">
                    <p className="text-muted-foreground">Failed to load journey data</p>
                </CardContent>
            </Card>
        )
    }

    if (!journeyData?.stops || journeyData.stops.length === 0) {
        return (
            <Card className="w-full">
                <CardContent className="flex items-center justify-center py-8">
                    <div className="text-center">
                        <MapPin className="h-12 w-12 text-muted-foreground mx-auto mb-2" />
                        <p className="text-muted-foreground">No journey data available</p>
                    </div>
                </CardContent>
            </Card>
        )
    }

    // Use progression nodes if available, fall back to raw stops
    const hasNodes = progressionNodes.length > 0

    return (
        <Card className="w-full">
            <CardHeader className="pb-2">
                <CardTitle className="text-lg flex items-center gap-2">
                    <TrendingUp className="h-5 w-5" />
                    Career Timeline
                </CardTitle>
            </CardHeader>
            <CardContent>
                <ScrollArea className="h-[400px] pr-4">
                    <div className="relative">
                        {/* Timeline line */}
                        <div className="absolute left-6 top-0 bottom-0 w-0.5 bg-border" />

                        {hasNodes ? (
                            /* Season-level progression nodes */
                            <div className="space-y-6">
                                {progressionNodes.map((node, index) => {
                                    const isFirst = index === 0
                                    const isLast = index === progressionNodes.length - 1
                                    const color = LEVEL_COLORS[node.primaryLevel] || '#6b7280'
                                    const visited = isNodeVisited(node)
                                    const isSelected = selectedNode?.id === node.id

                                    return (
                                        <div
                                            key={node.id}
                                            ref={el => { cardRefs.current[node.id] = el }}
                                            className="relative pl-16 cursor-pointer"
                                            onClick={() => selectNode(isSelected ? null : node)}
                                            style={{
                                                opacity: visited ? 1 : 0.3,
                                                transition: 'opacity 0.3s ease',
                                            }}
                                        >
                                            {/* Timeline dot */}
                                            <div
                                                className="absolute left-4 w-5 h-5 rounded-full border-2 border-white shadow-md flex items-center justify-center text-xs"
                                                style={{
                                                    backgroundColor: visited ? color : '#d1d5db',
                                                    transition: 'background-color 0.3s',
                                                }}
                                            >
                                                {isFirst && '1'}
                                                {isLast && !isFirst && '★'}
                                            </div>

                                            {/* Content card */}
                                            <div className={`p-3 rounded-lg border transition-[background-color,border-color,box-shadow] duration-300 ${
                                                isSelected
                                                    ? 'bg-primary/5 border-primary shadow-sm ring-1 ring-primary/20'
                                                    : isLast
                                                        ? 'bg-emerald-50 border-emerald-200 dark:bg-emerald-950/20 hover:border-border'
                                                        : 'bg-card hover:border-border'
                                            }`}>
                                                {/* Header */}
                                                <div className="flex items-start gap-3">
                                                    {node.clubLogo && (
                                                        <Avatar className="h-10 w-10">
                                                            <AvatarImage src={node.clubLogo} alt={node.clubName} />
                                                            <AvatarFallback>{node.clubName?.[0]}</AvatarFallback>
                                                        </Avatar>
                                                    )}
                                                    <div className="flex-1 min-w-0">
                                                        <div className="flex items-center gap-2 flex-wrap">
                                                            <h4 className="font-semibold truncate">{node.clubName}</h4>
                                                            {isFirst && (
                                                                <Badge variant="outline" className="text-xs">
                                                                    <Flag className="h-3 w-3 mr-1" />
                                                                    Origin
                                                                </Badge>
                                                            )}
                                                            {isLast && (
                                                                <Badge className="bg-green-500 text-xs">
                                                                    <Star className="h-3 w-3 mr-1" />
                                                                    Current
                                                                </Badge>
                                                            )}
                                                        </div>
                                                        <p className="text-sm text-muted-foreground">
                                                            {node.years}
                                                            {node.city && ` \u2022 ${node.city}`}
                                                        </p>
                                                    </div>
                                                </div>

                                                {/* Level badges */}
                                                <div className="flex flex-wrap gap-1 mt-2">
                                                    {node.levels?.map(level => (
                                                        <Badge
                                                            key={level}
                                                            variant="secondary"
                                                            className="text-xs"
                                                            style={{
                                                                backgroundColor: `${LEVEL_COLORS[level]}20`,
                                                                color: LEVEL_COLORS[level],
                                                                borderColor: LEVEL_COLORS[level]
                                                            }}
                                                        >
                                                            {LEVEL_ICONS[level]} {level}
                                                        </Badge>
                                                    ))}
                                                    {node.entryTypes?.includes('development') && (
                                                        <Badge variant="secondary" className="text-xs bg-orange-50 text-orange-700 border-orange-300">
                                                            Development
                                                        </Badge>
                                                    )}
                                                    {node.entryTypes?.includes('integration') && (
                                                        <Badge variant="secondary" className="text-xs bg-cyan-50 text-cyan-700 border-cyan-300">
                                                            New Signing
                                                        </Badge>
                                                    )}
                                                </div>

                                                {/* Stats */}
                                                <div className="flex gap-4 mt-2 text-sm">
                                                    <span>
                                                        <strong>{node.stats.apps}</strong> apps
                                                    </span>
                                                    <span>
                                                        <strong>{node.stats.goals}</strong> goals
                                                    </span>
                                                    <span>
                                                        <strong>{node.stats.assists}</strong> assists
                                                    </span>
                                                </div>

                                                {/* Competitions (collapsed) */}
                                                {node.competitions?.length > 0 && (
                                                    <details className="mt-2" onClick={e => e.stopPropagation()}>
                                                        <summary className="text-xs text-muted-foreground cursor-pointer hover:text-foreground">
                                                            {node.competitions.length} competition{node.competitions.length !== 1 ? 's' : ''}
                                                        </summary>
                                                        <div className="mt-2 space-y-1">
                                                            {node.competitions.map((comp, idx) => (
                                                                <div key={idx} className="flex items-center justify-between text-xs p-1 bg-muted/50 rounded">
                                                                    <span className="font-medium">{comp.league}</span>
                                                                    <span>
                                                                        {comp.apps} apps &bull; {comp.goals}G &bull; {comp.assists}A
                                                                    </span>
                                                                </div>
                                                            ))}
                                                        </div>
                                                    </details>
                                                )}
                                            </div>
                                        </div>
                                    )
                                })}
                            </div>
                        ) : (
                            /* Fallback: original stops-based timeline */
                            <div className="space-y-6">
                                {journeyData.stops.map((stop, index) => {
                                    const isFirst = index === 0
                                    const isLast = index === journeyData.stops.length - 1
                                    const primaryLevel = stop.levels?.[0] || 'First Team'
                                    const color = LEVEL_COLORS[primaryLevel] || '#6b7280'

                                    return (
                                        <div key={stop.club_id} className="relative pl-16">
                                            <div
                                                className="absolute left-4 w-5 h-5 rounded-full border-2 border-white shadow-md flex items-center justify-center text-xs"
                                                style={{ backgroundColor: color }}
                                            >
                                                {isFirst && '1'}
                                                {isLast && !isFirst && '★'}
                                            </div>

                                            <div className={`p-3 rounded-lg border ${isLast ? 'bg-emerald-50 border-emerald-200 dark:bg-emerald-950/20' : 'bg-card'}`}>
                                                <div className="flex items-start gap-3">
                                                    {stop.club_logo && (
                                                        <Avatar className="h-10 w-10">
                                                            <AvatarImage src={stop.club_logo} alt={stop.club_name} />
                                                            <AvatarFallback>{stop.club_name?.[0]}</AvatarFallback>
                                                        </Avatar>
                                                    )}
                                                    <div className="flex-1 min-w-0">
                                                        <div className="flex items-center gap-2 flex-wrap">
                                                            <h4 className="font-semibold truncate">{stop.club_name}</h4>
                                                            {isFirst && (
                                                                <Badge variant="outline" className="text-xs">
                                                                    <Flag className="h-3 w-3 mr-1" />
                                                                    Origin
                                                                </Badge>
                                                            )}
                                                            {isLast && (
                                                                <Badge className="bg-green-500 text-xs">
                                                                    <Star className="h-3 w-3 mr-1" />
                                                                    Current
                                                                </Badge>
                                                            )}
                                                        </div>
                                                        <p className="text-sm text-muted-foreground">
                                                            {stop.years}
                                                            {stop.city && ` \u2022 ${stop.city}`}
                                                        </p>
                                                    </div>
                                                </div>

                                                <div className="flex flex-wrap gap-1 mt-2">
                                                    {stop.levels?.map(level => (
                                                        <Badge
                                                            key={level}
                                                            variant="secondary"
                                                            className="text-xs"
                                                            style={{
                                                                backgroundColor: `${LEVEL_COLORS[level]}20`,
                                                                color: LEVEL_COLORS[level],
                                                                borderColor: LEVEL_COLORS[level]
                                                            }}
                                                        >
                                                            {LEVEL_ICONS[level]} {level}
                                                        </Badge>
                                                    ))}
                                                    {stop.entry_types?.includes('development') && (
                                                        <Badge variant="secondary" className="text-xs bg-orange-50 text-orange-700 border-orange-300">
                                                            Development
                                                        </Badge>
                                                    )}
                                                    {stop.entry_types?.includes('integration') && (
                                                        <Badge variant="secondary" className="text-xs bg-cyan-50 text-cyan-700 border-cyan-300">
                                                            New Signing
                                                        </Badge>
                                                    )}
                                                </div>

                                                <div className="flex gap-4 mt-2 text-sm">
                                                    <span><strong>{stop.total_apps}</strong> apps</span>
                                                    <span><strong>{stop.total_goals}</strong> goals</span>
                                                    <span><strong>{stop.total_assists}</strong> assists</span>
                                                </div>
                                            </div>
                                        </div>
                                    )
                                })}
                            </div>
                        )}
                    </div>
                </ScrollArea>
            </CardContent>
        </Card>
    )
}

export default JourneyTimeline
