import React, { useState, useEffect } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { Button } from '@/components/ui/button.jsx'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card.jsx'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar.jsx'
import { Badge } from '@/components/ui/badge.jsx'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs.jsx'
import { Loader2, UserPlus, UserCheck, ArrowLeft, Calendar, Users, Trophy, Lock, ExternalLink } from 'lucide-react'


import { APIService } from '@/lib/api'
import SubscribeToJournalist from '@/components/SubscribeToJournalist.jsx'

export function JournalistProfile() {
    const { id } = useParams()
    const navigate = useNavigate()
    const [journalist, setJournalist] = useState(null)
    const [stats, setStats] = useState(null)
    const [articles, setArticles] = useState([])
    const [loading, setLoading] = useState(true)
    const [subscribing, setSubscribing] = useState(false)
    const [isSubscribed, setIsSubscribed] = useState(false)

    useEffect(() => {
        loadData()
    }, [id])

    const loadData = async () => {
        try {
            setLoading(true)

            // 1. Fetch Journalist Details (from list endpoint for now, or we could add a specific GET endpoint)
            // Since we don't have a specific GET /journalists/:id public endpoint, we'll use the list and find.
            // Optimization: Add a specific endpoint later.
            const journalists = await APIService.request('/journalists')
            const found = journalists.find(j => j.id === parseInt(id))

            if (!found) {
                setJournalist(null)
                return
            }
            setJournalist(found)

            // 2. Fetch Public Stats
            const statsData = await APIService.getJournalistPublicStats(id)
            setStats(statsData)

            // 3. Fetch Articles (Track Record)
            const articlesData = await APIService.request(`/journalists/${id}/articles`)
            setArticles(articlesData)

            // 4. Check Subscription Status
            try {
                const mySubs = await APIService.request('/my-subscriptions')
                // API returns list of journalist objects, so we check sub.id (journalist ID)
                const subscribed = mySubs.some(sub => sub.id === parseInt(id))
                setIsSubscribed(subscribed)
            } catch (e) {
                // User might not be logged in
                setIsSubscribed(false)
            }

        } catch (error) {
            console.error('Failed to load profile:', error)
        } finally {
            setLoading(false)
        }
    }

    const handleSubscribe = async () => {
        try {
            setSubscribing(true)
            if (isSubscribed) {
                if (!confirm('Are you sure you want to unsubscribe?')) return
                await APIService.request(`/journalists/${id}/unsubscribe`, { method: 'POST' })
                setIsSubscribed(false)
            } else {
                await APIService.request(`/journalists/${id}/subscribe`, { method: 'POST' })
                setIsSubscribed(true)
            }
            // Reload stats to show updated count
            const statsData = await APIService.getJournalistPublicStats(id)
            setStats(statsData)
        } catch (error) {
            console.error('Failed to toggle subscription:', error)
            alert('Action failed. Please try again.')
        } finally {
            setSubscribing(false)
        }
    }

    if (loading) {
        return (
            <div className="flex flex-col items-center justify-center min-h-[50vh]">
                <Loader2 className="h-8 w-8 animate-spin text-primary mb-4" />
                <p className="text-muted-foreground">Loading profile...</p>
            </div>
        )
    }

    if (!journalist) {
        return (
            <div className="max-w-4xl mx-auto p-8 text-center">
                <h2 className="text-2xl font-bold text-foreground">Journalist Not Found</h2>
                <Button variant="link" onClick={() => navigate('/journalists')} className="mt-4">
                    <ArrowLeft className="mr-2 h-4 w-4" /> Back to Directory
                </Button>
            </div>
        )
    }

    return (
        <div className="max-w-5xl mx-auto px-4 py-8 space-y-8">
            {/* Back Button */}
            <Button variant="ghost" size="sm" onClick={() => navigate('/journalists')} className="mb-4">
                <ArrowLeft className="mr-2 h-4 w-4" /> Back to Directory
            </Button>

            {/* Header Profile Card */}
            <div className="bg-card rounded-none border-b border-border pb-8">
                <div className="flex flex-col md:flex-row gap-8 items-start">
                    <Avatar className="h-32 w-32 border border-border rounded-full">
                        <AvatarImage src={journalist.profile_image_url} alt={journalist.display_name} className="object-cover" />
                        <AvatarFallback className="text-4xl bg-black text-white font-serif">
                            {journalist.display_name?.substring(0, 2).toUpperCase()}
                        </AvatarFallback>
                    </Avatar>

                    <div className="flex-1 space-y-4">
                        <div className="flex justify-between items-start">
                            <div>
                                <h1 className="text-4xl font-serif font-bold text-foreground tracking-tight">{journalist.display_name}</h1>
                                <p className="text-lg text-muted-foreground mt-2 font-serif leading-relaxed max-w-2xl">{journalist.bio || 'Football Scout & Analyst'}</p>

                                {(journalist.attribution_url || journalist.attribution_name) && (
                                    <div className="mt-3 flex items-center gap-2">
                                        {journalist.attribution_url ? (
                                            <a
                                                href={journalist.attribution_url}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:text-primary/80 hover:underline"
                                            >
                                                {journalist.attribution_name || 'Visit Website'}
                                                <ExternalLink className="h-3 w-3" />
                                            </a>
                                        ) : (
                                            <span className="text-sm font-medium text-muted-foreground">
                                                {journalist.attribution_name}
                                            </span>
                                        )}
                                    </div>
                                )}
                            </div>
                            <Button
                                size="lg"
                                onClick={handleSubscribe}
                                disabled={subscribing}
                                variant={isSubscribed ? "outline" : "default"}
                                className={isSubscribed
                                    ? "border-border text-foreground/80 hover:bg-secondary rounded-full"
                                    : "bg-foreground text-primary-foreground hover:bg-foreground/90 rounded-full px-8"}
                            >
                                {subscribing ? (
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                ) : isSubscribed ? (
                                    <UserCheck className="mr-2 h-4 w-4" />
                                ) : (
                                    <UserPlus className="mr-2 h-4 w-4" />
                                )}
                                {isSubscribed ? 'Subscribed' : 'Subscribe'}
                            </Button>
                        </div>

                        {/* Stats Row */}
                        <div className="flex flex-wrap gap-8 py-4 border-t border-border mt-6">
                            <div className="flex flex-col">
                                <span className="text-2xl font-bold font-serif">{stats?.total_subscribers || 0}</span>
                                <span className="text-xs uppercase tracking-wider text-muted-foreground">
                                    {stats?.total_subscribers === 1 ? 'Subscriber' : 'Subscribers'}
                                </span>
                            </div>
                            <div className="flex flex-col">
                                <span className="text-2xl font-bold font-serif">{journalist.assigned_teams?.length || 0}</span>
                                <span className="text-xs uppercase tracking-wider text-muted-foreground">
                                    {journalist.assigned_teams?.length === 1 ? 'Team' : 'Teams'}
                                </span>
                            </div>
                            <div className="flex flex-col">
                                <span className="text-2xl font-bold font-serif">{new Date(journalist.created_at).getFullYear()}</span>
                                <span className="text-xs uppercase tracking-wider text-muted-foreground">Joined</span>
                            </div>
                        </div>

                        {/* Teams Badges - Clickable links to team newsletters */}
                        {journalist.assigned_teams && journalist.assigned_teams.length > 0 && (
                            <div className="flex flex-wrap gap-2 pt-2">
                                {journalist.assigned_teams.map(team => (
                                    <Link
                                        key={team.id}
                                        to={`/newsletters?team=${team.id}&team_name=${encodeURIComponent(team.name)}`}
                                    >
                                        <Badge
                                            variant="outline"
                                            className="px-3 py-1 text-sm flex items-center gap-2 border-border text-foreground/80 rounded-full font-normal hover:bg-secondary hover:border-border cursor-pointer transition-colors"
                                        >
                                            {team.logo && <img src={team.logo} alt="" className="w-4 h-4 object-contain" />}
                                            {team.name}
                                        </Badge>
                                    </Link>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            </div>

            <div className="bg-card border border-border rounded-lg p-6">
                <SubscribeToJournalist
                    journalistId={journalist.id}
                    journalistName={journalist.display_name}
                    onSubscribed={loadData}
                />
            </div>

            {/* Content Tabs */}
            <Tabs defaultValue="analysis" className="w-full">
                <TabsList className="w-full justify-start border-b border-border bg-transparent p-0 h-auto gap-8 rounded-none">
                    <TabsTrigger
                        value="analysis"
                        className="rounded-none border-b-2 border-transparent data-[state=active]:border-black data-[state=active]:bg-transparent data-[state=active]:shadow-none px-0 py-3 font-serif text-lg text-muted-foreground data-[state=active]:text-foreground"
                    >
                        Latest Analysis
                    </TabsTrigger>
                    <TabsTrigger
                        value="about"
                        className="rounded-none border-b-2 border-transparent data-[state=active]:border-black data-[state=active]:bg-transparent data-[state=active]:shadow-none px-0 py-3 font-serif text-lg text-muted-foreground data-[state=active]:text-foreground"
                    >
                        About
                    </TabsTrigger>
                </TabsList>

                <TabsContent value="analysis" className="mt-8 space-y-6">
                    {articles.length > 0 ? (
                        <div className="grid gap-0 divide-y divide-border">
                            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 bg-gradient-to-r from-secondary to-background border border-primary/10 rounded-lg p-4 mb-4">
                                <div className="space-y-1">
                                    <p className="text-sm font-semibold text-foreground">Subscribe for more analysis</p>
                                    <p className="text-sm text-muted-foreground">Get every premium writeup and match breakdown from {journalist.display_name}.</p>
                                </div>
                                <Button
                                    size="sm"
                                    onClick={handleSubscribe}
                                    variant={isSubscribed ? "outline" : "default"}
                                    className={isSubscribed ? "border-border text-foreground/80" : "bg-foreground text-primary-foreground"}
                                    disabled={subscribing}
                                >
                                    {subscribing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                                    {isSubscribed ? 'Subscribed' : 'Subscribe'}
                                </Button>
                            </div>
                            {articles.map(article => {
                                const targetId = article.newsletter_id
                                const handleClick = () => {
                                    if (targetId) {
                                        // Navigate to the new journalist newsletter view
                                        navigate(`/newsletters/${encodeURIComponent(targetId)}/writer/${id}`)
                                    } else {
                                        navigate(`/writeups/${article.id}`)
                                    }
                                }
                                return (
                                    <div key={article.id} className="py-6 group cursor-pointer" onClick={handleClick}>
                                        <div className="flex justify-between items-start mb-2">
                                            <div className="flex items-center gap-2">
                                                <span className="text-xs font-bold uppercase tracking-wider text-foreground">
                                                    {article.team_name}
                                                </span>
                                                <span className="text-xs text-muted-foreground/70">•</span>
                                                <span className="text-xs text-muted-foreground">
                                                    {new Date(article.created_at).toLocaleDateString(undefined, {
                                                        year: 'numeric', month: 'long', day: 'numeric'
                                                    })}
                                                </span>
                                            </div>
                                        </div>
                                        <h3 className="text-xl font-bold font-serif text-foreground group-hover:underline mb-2 leading-tight">
                                            {article.title || `Weekly Analysis: ${article.team_name}`}
                                        </h3>
                                        <p className="text-muted-foreground line-clamp-2 font-serif leading-relaxed">
                                            {article.content?.replace(/<[^>]*>/g, '').substring(0, 200)}...
                                        </p>
                                        <div className="mt-3 flex items-center gap-4">
                                            {article.is_locked && (
                                                <div className="flex items-center text-amber-600 text-sm font-medium bg-amber-50 px-2 py-1 rounded-md border border-amber-100">
                                                    <Lock className="w-3 h-3 mr-1" /> Premium
                                                </div>
                                            )}
                                            {article.applause_count > 0 && (
                                                <div className="flex items-center text-muted-foreground text-sm">
                                                    <span className="mr-1">👏</span> {article.applause_count}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                )
                            })}
                        </div>
                    ) : (
                        <div className="text-center py-12 bg-secondary rounded-lg border border-dashed">
                            <p className="text-muted-foreground">No analysis published yet.</p>
                        </div>
                    )}
                </TabsContent>

                <TabsContent value="about" className="mt-6">
                    <Card>
                        <CardHeader>
                            <CardTitle>About {journalist.display_name}</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="prose max-w-none text-foreground/80">
                                <p>{journalist.bio || "No bio available."}</p>
                            </div>
                        </CardContent>
                    </Card>
                </TabsContent>
            </Tabs>
        </div >
    )
}
