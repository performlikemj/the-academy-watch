import React, { useRef, useEffect, useState, useCallback } from 'react'
// eslint-disable-next-line no-unused-vars
import { motion } from 'framer-motion'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar'
import { HoverCard, HoverCardTrigger, HoverCardContent } from '@/components/ui/hover-card'
import { Badge } from '@/components/ui/badge'
import { useJourney } from '@/contexts/JourneyContext'
import { useHasHover } from '@/hooks/use-has-hover'
import { LEVEL_COLORS } from '@/lib/journey-utils'

/**
 * Horizontal strip of club logos representing career progression nodes.
 * Renders below the player header badges. Logos are connected by lines,
 * show HoverCard previews on desktop, and are clickable to "time travel".
 */
export function MiniProgressBar() {
    const { progressionNodes, selectedNode, selectNode, isNodeVisited } = useJourney()
    const hasHover = useHasHover()
    const scrollRef = useRef(null)
    const selectedLogoRef = useRef(null)
    const [canScrollLeft, setCanScrollLeft] = useState(false)
    const [canScrollRight, setCanScrollRight] = useState(false)

    const updateScrollIndicators = useCallback(() => {
        const el = scrollRef.current
        if (!el) return
        setCanScrollLeft(el.scrollLeft > 4)
        setCanScrollRight(el.scrollLeft < el.scrollWidth - el.clientWidth - 4)
    }, [])

    // Auto-scroll to the selected (or last) logo
    useEffect(() => {
        if (selectedLogoRef.current && scrollRef.current) {
            selectedLogoRef.current.scrollIntoView({
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
    }, [progressionNodes?.length, updateScrollIndicators])

    if (!progressionNodes || progressionNodes.length === 0) return null

    const activeIndex = selectedNode
        ? progressionNodes.findIndex(n => n.id === selectedNode.id)
        : progressionNodes.length - 1

    return (
        <div className="mt-2">
            <div className="relative">
                {canScrollLeft && (
                    <div className="absolute left-0 top-0 bottom-0 w-4 bg-gradient-to-r from-card to-transparent z-10 pointer-events-none" />
                )}
                {canScrollRight && (
                    <div className="absolute right-0 top-0 bottom-0 w-4 bg-gradient-to-l from-card to-transparent z-10 pointer-events-none" />
                )}
                <div
                    ref={scrollRef}
                    className="flex items-center gap-0 overflow-x-auto scrollbar-hide py-1 px-1"
                    style={{ scrollSnapType: 'x mandatory' }}
                >
                    {progressionNodes.map((node, i) => {
                        const color = LEVEL_COLORS[node.primaryLevel] || '#6b7280'
                        const isSelected = selectedNode ? node.id === selectedNode.id : i === progressionNodes.length - 1
                        const visited = isNodeVisited(node)

                        const logoButton = (
                            <button
                                ref={isSelected ? selectedLogoRef : null}
                                onClick={() => selectNode(isSelected && selectedNode ? null : node)}
                                className="relative flex-shrink-0 p-1 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none rounded-full"
                                aria-label={`${node.clubName} ${node.years}`}
                            >
                                <motion.div
                                    animate={{
                                        scale: isSelected ? 1.2 : 1,
                                    }}
                                    transition={{ type: 'spring', stiffness: 400, damping: 25 }}
                                    className={`${isSelected ? 'ring-2 ring-ring ring-offset-1' : ''} rounded-full`}
                                >
                                    <Avatar className={`h-5 w-5 md:h-6 md:w-6 transition-opacity duration-300 ${visited ? 'opacity-100' : 'opacity-40'}`}>
                                        <AvatarImage src={node.clubLogo} alt={node.clubName} />
                                        <AvatarFallback
                                            className="text-[8px] md:text-[10px] font-bold text-white"
                                            style={{ backgroundColor: color }}
                                        >
                                            {node.clubName?.charAt(0) || '?'}
                                        </AvatarFallback>
                                    </Avatar>
                                </motion.div>
                            </button>
                        )

                        return (
                            <div
                                key={node.id}
                                className="flex items-center flex-shrink-0"
                                style={{ scrollSnapAlign: 'center' }}
                            >
                                {/* Connecting line before this logo (skip for first) */}
                                {i > 0 && (
                                    <div
                                        className="h-0.5 transition-colors duration-300"
                                        style={{
                                            width: '16px',
                                            backgroundColor: i <= activeIndex ? '#d97706' : '#d6d3d1',
                                            opacity: i <= activeIndex ? 0.8 : 0.4,
                                        }}
                                    />
                                )}

                                {/* Logo with optional HoverCard */}
                                {hasHover ? (
                                    <HoverCard openDelay={200} closeDelay={100}>
                                        <HoverCardTrigger asChild>
                                            {logoButton}
                                        </HoverCardTrigger>
                                        <HoverCardContent className="w-56 p-3" side="bottom" align="center">
                                            <div className="space-y-2">
                                                {/* Club header */}
                                                <div className="flex items-center gap-2">
                                                    <Avatar className="h-8 w-8">
                                                        <AvatarImage src={node.clubLogo} alt={node.clubName} />
                                                        <AvatarFallback
                                                            className="text-xs font-bold text-white"
                                                            style={{ backgroundColor: color }}
                                                        >
                                                            {node.clubName?.charAt(0) || '?'}
                                                        </AvatarFallback>
                                                    </Avatar>
                                                    <div className="flex-1 min-w-0">
                                                        <div className="font-semibold text-sm truncate">{node.clubName}</div>
                                                        <div className="text-xs text-muted-foreground">{node.years}</div>
                                                    </div>
                                                </div>
                                                {/* Level badges */}
                                                <div className="flex flex-wrap gap-1">
                                                    {(node.levels || [node.primaryLevel]).map((level, idx) => (
                                                        <Badge
                                                            key={idx}
                                                            className="text-[10px] text-white px-1.5 py-0"
                                                            style={{ backgroundColor: LEVEL_COLORS[level] || '#6b7280' }}
                                                        >
                                                            {level}
                                                        </Badge>
                                                    ))}
                                                </div>
                                                {/* Stats */}
                                                <div className="grid grid-cols-3 gap-2 text-center">
                                                    <div className="bg-secondary rounded p-1.5">
                                                        <div className="text-sm font-bold tabular-nums">{node.stats.apps}</div>
                                                        <div className="text-[10px] text-muted-foreground">Apps</div>
                                                    </div>
                                                    <div className="bg-secondary rounded p-1.5">
                                                        <div className="text-sm font-bold text-emerald-600 tabular-nums">{node.stats.goals}</div>
                                                        <div className="text-[10px] text-muted-foreground">Goals</div>
                                                    </div>
                                                    <div className="bg-secondary rounded p-1.5">
                                                        <div className="text-sm font-bold text-amber-600 tabular-nums">{node.stats.assists}</div>
                                                        <div className="text-[10px] text-muted-foreground">Assists</div>
                                                    </div>
                                                </div>
                                                {/* Hint */}
                                                <p className="text-[10px] text-muted-foreground/70 text-center">Click to explore</p>
                                            </div>
                                        </HoverCardContent>
                                    </HoverCard>
                                ) : (
                                    logoButton
                                )}
                            </div>
                        )
                    })}
                </div>
            </div>

            {/* Season labels (sparse — show first, last, and selected) */}
            <div className="flex justify-between text-[10px] text-muted-foreground/70 mt-0.5 px-1">
                <span>{progressionNodes[0]?.years}</span>
                {selectedNode && (
                    <span className="text-primary font-medium">{selectedNode.years}</span>
                )}
                <span>{progressionNodes[progressionNodes.length - 1]?.years}</span>
            </div>
        </div>
    )
}

export default MiniProgressBar
