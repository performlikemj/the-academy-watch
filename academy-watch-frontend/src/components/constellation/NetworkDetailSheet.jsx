import { useState, useEffect, useMemo } from 'react'
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet'
import { Drawer, DrawerContent, DrawerHeader, DrawerTitle, DrawerDescription } from '@/components/ui/drawer'
import { Badge } from '@/components/ui/badge'
import { PlayerCard } from '@/components/shared/PlayerCard'
import { motion } from 'framer-motion' // eslint-disable-line no-unused-vars

const LINK_TYPE_CONFIG = {
    loan: { label: 'Loan', className: 'bg-amber-500/20 text-amber-300 border-amber-500/30' },
    permanent: { label: 'Permanent', className: 'bg-slate-500/20 text-slate-300 border-slate-500/30' },
    return: { label: 'Return', className: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30' },
}

function DetailContent({ node, players }) {
    return (
        <div className="flex flex-col gap-4">
            <div className="flex items-start gap-3 px-4">
                {node.club_logo && (
                    <img
                        src={node.club_logo}
                        alt={node.club_name}
                        className="w-12 h-12 object-contain shrink-0"
                        onError={e => { e.target.style.display = 'none' }}
                    />
                )}
                <div className="flex-1 min-w-0">
                    <h3 className="text-lg font-semibold text-slate-100 truncate">
                        {node.club_name}
                    </h3>
                    {(node.city || node.country) && (
                        <p className="text-sm text-slate-400">
                            {[node.city, node.country].filter(Boolean).join(', ')}
                        </p>
                    )}
                </div>
            </div>

            <div className="flex items-center gap-2 flex-wrap px-4">
                <Badge className="bg-slate-700 text-slate-200 border-slate-600">
                    {node.player_count} {node.player_count === 1 ? 'player' : 'players'}
                </Badge>
                {node.total_appearances > 0 && (
                    <span className="text-sm text-slate-400">
                        {node.total_appearances} total appearances
                    </span>
                )}
            </div>

            {node.link_types?.length > 0 && (
                <div className="flex items-center gap-1.5 flex-wrap px-4">
                    {node.link_types.map(type => {
                        const config = LINK_TYPE_CONFIG[type]
                        if (!config) return null
                        return (
                            <Badge key={type} className={config.className}>
                                {config.label}
                            </Badge>
                        )
                    })}
                </div>
            )}

            <div className="max-h-[60vh] overflow-y-auto px-1">
                {players.length > 0 ? (
                    players.map((player, index) => (
                        <motion.div
                            key={player.player_api_id}
                            initial={{ opacity: 0, x: 20 }}
                            animate={{ opacity: 1, x: 0 }}
                            transition={{ delay: index * 0.04, duration: 0.25, ease: 'easeOut' }}
                        >
                            <PlayerCard
                                player={player}
                                highlightClubId={node.club_api_id}
                            />
                        </motion.div>
                    ))
                ) : (
                    <p className="text-sm text-slate-500 text-center py-8 px-4">
                        No player journey data available for this club.
                    </p>
                )}
            </div>
        </div>
    )
}

export function NetworkDetailSheet({ node, allPlayers, open, onClose }) {
    const [isDesktop, setIsDesktop] = useState(true)

    useEffect(() => {
        const mql = window.matchMedia('(min-width: 640px)')
        setIsDesktop(mql.matches)

        function handleChange(e) {
            setIsDesktop(e.matches)
        }

        mql.addEventListener('change', handleChange)
        return () => mql.removeEventListener('change', handleChange)
    }, [])

    const filteredPlayers = useMemo(() => {
        if (!node || !allPlayers) return []
        return allPlayers.filter(player =>
            player.journey_path?.some(stop => stop.club_api_id === node.club_api_id)
        )
    }, [node, allPlayers])

    if (!node) return null

    if (isDesktop) {
        return (
            <Sheet open={open} onOpenChange={val => { if (!val) onClose() }}>
                <SheetContent
                    side="right"
                    className="bg-slate-900 border-slate-700 text-slate-100 overflow-y-auto"
                >
                    <SheetHeader>
                        <SheetTitle className="text-slate-100">Club Detail</SheetTitle>
                        <SheetDescription className="text-slate-400">
                            Academy players linked to this destination club.
                        </SheetDescription>
                    </SheetHeader>
                    <DetailContent node={node} players={filteredPlayers} />
                </SheetContent>
            </Sheet>
        )
    }

    return (
        <Drawer open={open} onOpenChange={val => { if (!val) onClose() }}>
            <DrawerContent className="bg-slate-900 border-slate-700 text-slate-100">
                <DrawerHeader>
                    <DrawerTitle className="text-slate-100">Club Detail</DrawerTitle>
                    <DrawerDescription className="text-slate-400">
                        Academy players linked to this destination club.
                    </DrawerDescription>
                </DrawerHeader>
                <div className="pb-6">
                    <DetailContent node={node} players={filteredPlayers} />
                </div>
            </DrawerContent>
        </Drawer>
    )
}

export default NetworkDetailSheet
