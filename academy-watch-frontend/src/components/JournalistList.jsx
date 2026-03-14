import React, { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from '@/components/ui/card.jsx'
import { Button } from '@/components/ui/button.jsx'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar.jsx'
import { Badge } from '@/components/ui/badge.jsx'
import { Input } from '@/components/ui/input.jsx'
import TeamMultiSelect from '@/components/ui/TeamMultiSelect.jsx'
import { Loader2, UserPlus, UserCheck, Search, Users, ExternalLink } from 'lucide-react'


import { APIService } from '@/lib/api'

export function JournalistList({ apiService = APIService }) {
    const navigate = useNavigate()
    const [journalists, setJournalists] = useState([])
    const [subscriptions, setSubscriptions] = useState([])
    const [journalistStats, setJournalistStats] = useState({}) // Store stats by journalist ID
    const [loading, setLoading] = useState(true)
    const [subscribing, setSubscribing] = useState({})

    // Search & Filter states
    const [searchName, setSearchName] = useState('')
    const [selectedTeamIds, setSelectedTeamIds] = useState([])

    useEffect(() => {
        loadData()
    }, [])

    const loadData = async () => {
        try {
            setLoading(true)
            const [journalistsData, subsData] = await Promise.all([
                apiService.request('/journalists'),
                apiService.request('/my-subscriptions').catch(() => []) // Handle unauth gracefully
            ])
            setJournalists(journalistsData)
            setSubscriptions(subsData)

            // Load stats for each journalist
            const statsPromises = journalistsData.map(j =>
                apiService.getJournalistPublicStats(j.id).catch(() => null)
            )
            const statsResults = await Promise.all(statsPromises)

            // Create stats lookup by journalist ID
            const statsMap = {}
            statsResults.forEach((stats, index) => {
                if (stats) {
                    statsMap[journalistsData[index].id] = stats
                }
            })
            setJournalistStats(statsMap)
        } catch (error) {
            console.error('Failed to load journalists:', error)
        } finally {
            setLoading(false)
        }
    }

    const handleSubscribe = async (journalistId) => {
        try {
            setSubscribing(prev => ({ ...prev, [journalistId]: true }))
            await apiService.request(`/journalists/${journalistId}/subscribe`, { method: 'POST' })
            await loadData() // Reload to update state
        } catch (error) {
            console.error('Failed to subscribe:', error)
            alert('Failed to subscribe. Please try again.')
        } finally {
            setSubscribing(prev => ({ ...prev, [journalistId]: false }))
        }
    }

    const handleUnsubscribe = async (journalistId) => {
        if (!confirm('Are you sure you want to unsubscribe?')) return

        try {
            setSubscribing(prev => ({ ...prev, [journalistId]: true }))
            await apiService.request(`/journalists/${journalistId}/unsubscribe`, { method: 'POST' })
            await loadData()
        } catch (error) {
            console.error('Failed to unsubscribe:', error)
        } finally {
            setSubscribing(prev => ({ ...prev, [journalistId]: false }))
        }
    }

    const isSubscribed = (journalistId) => {
        return subscriptions.some(sub => sub.id === journalistId || sub.journalist_user_id === journalistId)
    }

    // Derived state for filters
    const availableTeams = useMemo(() => {
        const teamsMap = new Map();
        journalists.forEach(j => {
            j.assigned_teams?.forEach(t => {
                // Use API Team ID (team_id) instead of DB ID to handle cross-season teams
                if (!teamsMap.has(t.team_id)) {
                    teamsMap.set(t.team_id, t);
                }
            });
        });
        return Array.from(teamsMap.values()).sort((a, b) => a.name.localeCompare(b.name));
    }, [journalists]);

    const filteredJournalists = useMemo(() => {
        return journalists.filter(j => {
            const matchesName = j.display_name.toLowerCase().includes(searchName.toLowerCase());

            let matchesTeam = true;
            if (selectedTeamIds.length > 0) {
                // Use API Team ID (team_id) for matching to handle cross-season compatibility
                const journalistTeamIds = j.assigned_teams?.map(t => t.team_id) || [];
                // Match if journalist covers ANY of the selected teams
                matchesTeam = selectedTeamIds.some(id => journalistTeamIds.includes(id));
            }

            return matchesName && matchesTeam;
        });
    }, [journalists, searchName, selectedTeamIds]);

    if (loading) {
        return <div className="flex justify-center p-8"><Loader2 className="h-8 w-8 animate-spin" /></div>
    }

    return (
        <div className="space-y-6 p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto">
            <div className="flex flex-col gap-4 md:flex-row md:justify-between md:items-center">
                <div>
                    <h2 className="text-3xl font-bold tracking-tight">Journalists & Scouts</h2>
                    <p className="text-muted-foreground mt-1">
                        Discover and subscribe to expert analysis on your favorite teams.
                    </p>
                </div>
            </div>

            {/* Filters */}
            <div className="flex flex-col md:flex-row gap-4 items-end md:items-center bg-card p-4 rounded-lg border shadow-sm">
                <div className="w-full md:w-1/3 relative">
                    <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
                    <Input
                        placeholder="Search journalists..."
                        value={searchName}
                        onChange={(e) => setSearchName(e.target.value)}
                        className="pl-8"
                    />
                </div>
                <div className="w-full md:w-1/3">
                    <TeamMultiSelect
                        teams={availableTeams}
                        value={selectedTeamIds}
                        onChange={setSelectedTeamIds}
                        placeholder="Filter by teams covered..."
                    />
                </div>
                <div className="hidden md:block text-sm text-muted-foreground ml-auto">
                    Showing {filteredJournalists.length} {filteredJournalists.length === 1 ? 'journalist' : 'journalists'}
                </div>
            </div>

            {filteredJournalists.length === 0 ? (
                <div className="text-center py-16 bg-muted/20 rounded-xl border-2 border-dashed">
                    <p className="text-muted-foreground text-lg mb-2">No journalists found matching your criteria.</p>
                    <Button
                        variant="link"
                        onClick={() => { setSearchName(''); setSelectedTeamIds([]); }}
                    >
                        Clear filters
                    </Button>
                </div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {filteredJournalists.map((journalist) => {
                        const subscribed = isSubscribed(journalist.id)
                        const isProcessing = subscribing[journalist.id]
                        const stats = journalistStats[journalist.id]

                        return (
                            <Card key={journalist.id} className="flex flex-col h-full hover:shadow-md transition-shadow">
                                <CardHeader className="flex flex-row items-start gap-4 space-y-0 pb-2">
                                    <Avatar className="h-14 w-14 border-2 border-background shadow-sm">
                                        <AvatarImage src={journalist.profile_image_url} alt={journalist.display_name} />
                                        <AvatarFallback className="text-lg bg-primary/10 text-primary">
                                            {journalist.display_name?.substring(0, 2).toUpperCase()}
                                        </AvatarFallback>
                                    </Avatar>
                                    <div className="flex-1 min-w-0">
                                        <CardTitle
                                            className="text-lg truncate cursor-pointer hover:text-primary hover:underline"
                                            title={journalist.display_name}
                                            onClick={() => navigate(`/journalists/${journalist.id}`)}
                                        >
                                            {journalist.display_name}
                                        </CardTitle>
                                        <CardDescription className="line-clamp-2 mt-1 text-xs sm:text-sm">
                                            {journalist.bio || 'Football Scout & Analyst'}
                                        </CardDescription>
                                        {(journalist.attribution_url || journalist.attribution_name) && (
                                            <div className="mt-1 flex items-center gap-1">
                                                {journalist.attribution_url ? (
                                                    <a
                                                        href={journalist.attribution_url}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        className="text-xs text-primary hover:underline flex items-center gap-1"
                                                        onClick={(e) => e.stopPropagation()}
                                                    >
                                                        {journalist.attribution_name || 'Visit Site'}
                                                        <ExternalLink className="h-2.5 w-2.5" />
                                                    </a>
                                                ) : (
                                                    <span className="text-xs text-muted-foreground">
                                                        {journalist.attribution_name}
                                                    </span>
                                                )}
                                            </div>
                                        )}
                                        {stats && stats.total_subscribers > 0 && (
                                            <div className="mt-2">
                                                <Badge variant="secondary" className="text-xs font-semibold">
                                                    <Users className="h-3 w-3 mr-1" />
                                                    {stats.total_subscribers} {stats.total_subscribers === 1 ? 'subscriber' : 'subscribers'}
                                                </Badge>
                                            </div>
                                        )}
                                    </div>
                                </CardHeader>
                                <CardContent className="flex-1 pt-2">
                                    <div className="space-y-3">
                                        <div>
                                            <p className="text-xs font-semibold text-muted-foreground mb-2 uppercase tracking-wider">
                                                Covers
                                            </p>
                                            {journalist.assigned_teams && journalist.assigned_teams.length > 0 ? (
                                                <div className="flex flex-wrap gap-2">
                                                    {journalist.assigned_teams.map(team => (
                                                        <Badge
                                                            key={team.id}
                                                            variant="outline"
                                                            className="pl-1 pr-2 py-1 h-7 flex items-center gap-1.5 hover:bg-accent transition-colors"
                                                        >
                                                            {team.logo ? (
                                                                <Avatar className="h-4 w-4">
                                                                    <AvatarImage src={team.logo} alt={team.name} />
                                                                    <AvatarFallback className="text-[8px]">
                                                                        {team.name.substring(0, 2)}
                                                                    </AvatarFallback>
                                                                </Avatar>
                                                            ) : (
                                                                <div className="h-4 w-4 rounded-full bg-muted flex items-center justify-center text-[8px]">
                                                                    {team.name.substring(0, 1)}
                                                                </div>
                                                            )}
                                                            <span className="truncate max-w-[100px]">{team.name}</span>
                                                        </Badge>
                                                    ))}
                                                </div>
                                            ) : (
                                                <span className="text-sm text-muted-foreground italic">General coverage</span>
                                            )}
                                        </div>
                                    </div>
                                </CardContent>
                                <CardFooter className="pt-4 pb-4 bg-muted/10 mt-auto border-t">
                                    {subscribed ? (
                                        <Button
                                            variant="outline"
                                            className="w-full border-green-200 hover:bg-green-50 hover:text-green-700 text-green-600"
                                            onClick={() => handleUnsubscribe(journalist.id)}
                                            disabled={isProcessing}
                                        >
                                            {isProcessing ? (
                                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                            ) : (
                                                <UserCheck className="mr-2 h-4 w-4" />
                                            )}
                                            Subscribed
                                        </Button>
                                    ) : (
                                        <Button
                                            className="w-full"
                                            onClick={() => handleSubscribe(journalist.id)}
                                            disabled={isProcessing}
                                        >
                                            {isProcessing ? (
                                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                            ) : (
                                                <UserPlus className="mr-2 h-4 w-4" />
                                            )}
                                            Subscribe
                                        </Button>
                                    )}
                                    <Button
                                        variant="ghost"
                                        className="w-full mt-2 text-xs text-muted-foreground"
                                        onClick={() => navigate(`/journalists/${journalist.id}`)}
                                    >
                                        View Profile
                                    </Button>
                                </CardFooter>
                            </Card>
                        )
                    })}
                </div>
            )}
        </div>
    )
}
