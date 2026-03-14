import { useState, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { APIService } from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar'
import { Loader2 } from 'lucide-react'
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet'
import { Drawer, DrawerContent, DrawerHeader, DrawerTitle, DrawerDescription } from '@/components/ui/drawer'
import { motion } from 'framer-motion' // eslint-disable-line no-unused-vars
import { OriginsHeader } from './OriginsHeader'
import { RadialOriginsChart } from './RadialOriginsChart'
import { OriginsList } from './OriginsList'

const CURRENT_SEASON = new Date().getFullYear() - (new Date().getMonth() < 7 ? 1 : 0)

export function SquadOriginsView({ teamApiId, teamLogo, teamName, initialSeason }) {
    const [season, setSeason] = useState(initialSeason || CURRENT_SEASON)
    const [origins, setOrigins] = useState(null)
    const [loading, setLoading] = useState(true)
    const [selectedAcademy, setSelectedAcademy] = useState(null)
    const [isDesktop, setIsDesktop] = useState(true)
    const fetchRef = useRef(0)

    useEffect(() => {
        const mql = window.matchMedia('(min-width: 640px)')
        setIsDesktop(mql.matches)
        const handler = (e) => setIsDesktop(e.matches)
        mql.addEventListener('change', handler)
        return () => mql.removeEventListener('change', handler)
    }, [])

    useEffect(() => {
        if (!teamApiId) return
        const id = ++fetchRef.current
        setLoading(true)
        setSelectedAcademy(null)
        APIService.getSquadOrigins(teamApiId, { season })
            .then(data => { if (fetchRef.current === id) setOrigins(data) })
            .catch(err => {
                console.error('Failed to load squad origins', err)
                if (fetchRef.current === id) setOrigins(null)
            })
            .finally(() => { if (fetchRef.current === id) setLoading(false) })
    }, [teamApiId, season])

    const handleAcademyClick = (group) => {
        setSelectedAcademy(prev =>
            prev?.academy?.api_id === group.academy.api_id ? null : group
        )
    }

    if (loading) {
        return (
            <div className="flex flex-col items-center justify-center py-16 gap-3">
                <Loader2 className="h-8 w-8 animate-spin text-amber-400/70" />
                <p className="text-sm text-slate-400">
                    Resolving academy origins...
                </p>
            </div>
        )
    }

    if (!origins || origins.squad_size === 0) {
        return (
            <div className="py-12 text-center rounded-xl bg-slate-800/50 border border-slate-700/50">
                <p className="text-slate-400">
                    No squad origins data available for this team. Try a different season.
                </p>
            </div>
        )
    }

    const { academy_breakdown, unknown_origin } = origins

    const detailContent = selectedAcademy && (
        <div className="space-y-4">
            {/* Header */}
            <div className="flex items-center gap-3">
                {selectedAcademy.academy.logo && (
                    <img
                        src={selectedAcademy.academy.logo}
                        alt={selectedAcademy.academy.name}
                        className="w-12 h-12 object-contain"
                    />
                )}
                <div>
                    <h3 className="text-lg font-semibold text-slate-100">
                        {selectedAcademy.academy.name}
                    </h3>
                    <div className="flex items-center gap-2 mt-1">
                        <span className="text-sm text-slate-400">
                            {selectedAcademy.count} player{selectedAcademy.count !== 1 ? 's' : ''}
                        </span>
                        {selectedAcademy.is_homegrown && (
                            <Badge className="bg-emerald-900/50 text-emerald-400 border-emerald-700/50 text-xs">
                                Homegrown
                            </Badge>
                        )}
                    </div>
                </div>
            </div>

            {/* Player list */}
            <div className="space-y-1 max-h-[60vh] overflow-y-auto">
                {selectedAcademy.players.map((player, index) => (
                    <motion.div
                        key={player.player_api_id}
                        initial={{ opacity: 0, x: 20 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: index * 0.04 }}
                    >
                        <Link
                            to={`/players/${player.player_api_id}`}
                            className="flex items-center gap-3 py-2.5 px-3 rounded-lg hover:bg-slate-700/50 transition-colors group"
                        >
                            <Avatar className="h-8 w-8 shrink-0">
                                <AvatarImage src={player.photo} alt={player.player_name} />
                                <AvatarFallback className="text-[10px] bg-slate-700 text-slate-300">
                                    {(player.player_name || '').split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()}
                                </AvatarFallback>
                            </Avatar>
                            <div className="flex-1 min-w-0">
                                <div className="text-sm font-medium text-slate-100 group-hover:text-amber-400 transition-colors truncate">
                                    {player.player_name}
                                </div>
                                <div className="text-xs text-slate-500">
                                    {player.position}{player.nationality ? ` — ${player.nationality}` : ''}
                                </div>
                            </div>
                            <div className="text-xs text-slate-400 shrink-0 text-right">
                                {player.appearances > 0 && <span>{player.appearances} apps</span>}
                                {player.goals > 0 && <span className="ml-1.5 text-emerald-400">{player.goals}G</span>}
                                {player.assists > 0 && <span className="ml-1 text-amber-400">{player.assists}A</span>}
                            </div>
                        </Link>
                    </motion.div>
                ))}
            </div>
        </div>
    )

    return (
        <div className="space-y-6">
            {/* Header with donut chart + stats + season selector */}
            <OriginsHeader
                origins={origins}
                season={season}
                onSeasonChange={setSeason}
            />

            {/* Radial visualization */}
            <RadialOriginsChart
                origins={origins}
                parentClub={{ name: teamName, logo: teamLogo }}
                onAcademyClick={handleAcademyClick}
                selectedAcademyId={selectedAcademy?.academy?.api_id}
            />

            {/* Collapsible feeder list */}
            <OriginsList
                academies={academy_breakdown}
                onAcademyClick={handleAcademyClick}
            />

            {/* Unknown origins */}
            {unknown_origin?.length > 0 && (
                <div className="space-y-2">
                    <h3 className="text-sm font-medium text-slate-400">
                        Unknown Origin
                        <Badge variant="outline" className="ml-2 border-slate-600 text-slate-500 text-xs">{unknown_origin.length}</Badge>
                    </h3>
                    <div className="bg-slate-800/50 rounded-lg border border-slate-700/50 divide-y divide-slate-700/50">
                        {unknown_origin.map((player) => (
                            <Link
                                key={player.player_api_id}
                                to={`/players/${player.player_api_id}`}
                                className="flex items-center gap-3 py-2.5 px-3 hover:bg-slate-700/50 transition-colors"
                            >
                                <Avatar className="h-7 w-7">
                                    <AvatarImage src={player.photo} alt={player.player_name} />
                                    <AvatarFallback className="text-[10px] bg-slate-700 text-slate-300">
                                        {(player.player_name || '').split(' ').map(n => n[0]).join('').slice(0, 2)}
                                    </AvatarFallback>
                                </Avatar>
                                <span className="text-sm text-slate-300">{player.player_name}</span>
                                <span className="text-xs text-slate-500">{player.position}</span>
                            </Link>
                        ))}
                    </div>
                </div>
            )}

            {/* Detail Sheet/Drawer */}
            {isDesktop ? (
                <Sheet open={!!selectedAcademy} onOpenChange={(open) => !open && setSelectedAcademy(null)}>
                    <SheetContent side="right" className="bg-slate-900 border-slate-700 text-slate-100 w-[400px] sm:w-[440px]">
                        <SheetHeader>
                            <SheetTitle className="text-slate-100">Academy Detail</SheetTitle>
                            <SheetDescription className="text-slate-400">Players from this feeder academy</SheetDescription>
                        </SheetHeader>
                        <div className="mt-4">
                            {detailContent}
                        </div>
                    </SheetContent>
                </Sheet>
            ) : (
                <Drawer open={!!selectedAcademy} onOpenChange={(open) => !open && setSelectedAcademy(null)}>
                    <DrawerContent className="bg-slate-900 border-slate-700 text-slate-100">
                        <DrawerHeader>
                            <DrawerTitle className="text-slate-100">Academy Detail</DrawerTitle>
                            <DrawerDescription className="text-slate-400">Players from this feeder academy</DrawerDescription>
                        </DrawerHeader>
                        <div className="p-4">
                            {detailContent}
                        </div>
                    </DrawerContent>
                </Drawer>
            )}
        </div>
    )
}

export default SquadOriginsView
