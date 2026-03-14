import React from 'react'
// eslint-disable-next-line no-unused-vars
import { motion, AnimatePresence } from 'framer-motion'
import { ArrowLeft } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { useJourney } from '@/contexts/JourneyContext'
import { LEVEL_COLORS } from '@/lib/journey-utils'

/**
 * Slides in above the map when a non-current node is selected,
 * showing season-specific stats for that "memory".
 */
export function SeasonStatsPanel() {
    const { selectedNode, selectNode, progressionNodes } = useJourney()

    const isLatest = selectedNode && selectedNode.id === progressionNodes[progressionNodes.length - 1]?.id

    return (
        <AnimatePresence>
            {selectedNode && !isLatest && (
                <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.25, ease: 'easeInOut' }}
                    className="overflow-hidden"
                >
                    <div className="bg-primary/5 border border-primary/20 rounded-lg p-3 sm:p-4 mb-4">
                        {/* Header row */}
                        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-3">
                            <button
                                onClick={() => selectNode(null)}
                                aria-label="Back to present"
                                className="flex items-center gap-1 text-sm text-primary hover:text-primary/90 transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none rounded"
                            >
                                <ArrowLeft className="h-4 w-4" />
                                Back to Present
                            </button>
                            <div className="flex items-center gap-2 flex-wrap">
                                <span className="text-sm font-semibold text-foreground">
                                    {selectedNode.years}
                                </span>
                                <span className="text-sm text-muted-foreground">at</span>
                                <div className="flex items-center gap-1.5 min-w-0">
                                    {selectedNode.clubLogo && (
                                        <img src={selectedNode.clubLogo} alt="" width={20} height={20} className="w-5 h-5 rounded-full object-cover" />
                                    )}
                                    <span className="text-sm font-medium text-foreground truncate">
                                        {selectedNode.clubName}
                                    </span>
                                </div>
                                <Badge
                                    className="text-xs text-white"
                                    style={{ backgroundColor: LEVEL_COLORS[selectedNode.primaryLevel] || '#6b7280' }}
                                >
                                    {selectedNode.primaryLevel}
                                </Badge>
                            </div>
                        </div>

                        {/* Stats summary */}
                        <div className="grid grid-cols-3 gap-2 sm:gap-4 mb-3">
                            <div className="text-center p-2 bg-card rounded-lg">
                                <div className="text-xl font-bold text-foreground tabular-nums">{selectedNode.stats.apps}</div>
                                <div className="text-xs text-muted-foreground">Apps</div>
                            </div>
                            <div className="text-center p-2 bg-card rounded-lg">
                                <div className="text-xl font-bold text-emerald-600 tabular-nums">{selectedNode.stats.goals}</div>
                                <div className="text-xs text-muted-foreground">Goals</div>
                            </div>
                            <div className="text-center p-2 bg-card rounded-lg">
                                <div className="text-xl font-bold text-amber-600 tabular-nums">{selectedNode.stats.assists}</div>
                                <div className="text-xs text-muted-foreground">Assists</div>
                            </div>
                        </div>

                        {/* Competition breakdown */}
                        {selectedNode.competitions?.length > 0 && (
                            <div>
                                <h4 className="text-xs font-medium text-muted-foreground mb-1.5">Competitions</h4>
                                <div className="space-y-1">
                                    {selectedNode.competitions.map((comp, idx) => (
                                        <div
                                            key={idx}
                                            className="flex items-center justify-between text-sm bg-white rounded px-3 py-1.5"
                                        >
                                            <span className="font-medium text-foreground/80">{comp.league}</span>
                                            <span className="text-muted-foreground">
                                                {comp.apps} apps, {comp.goals}G {comp.assists}A
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                </motion.div>
            )}
        </AnimatePresence>
    )
}

export default SeasonStatsPanel
