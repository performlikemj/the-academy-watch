import React, { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog'
import { Loader2, Plus, Trash2, Pencil, Link2, Unlink, FileText, LogOut, KeyRound } from 'lucide-react'
import { APIService } from '@/lib/api'
import { useAuth, useAuthUI } from '@/context/AuthContext'
import { TweetForm } from '@/components/curator/TweetForm'

export function CuratorDashboard() {
    const navigate = useNavigate()
    const { logout } = useAuthUI()
    const { hasCuratorKey } = useAuth()

    const [loading, setLoading] = useState(true)
    const [teams, setTeams] = useState([])
    const [selectedTeamId, setSelectedTeamId] = useState('')
    const [newsletters, setNewsletters] = useState([])
    const [tweets, setTweets] = useState([])
    const [players, setPlayers] = useState([])
    const [error, setError] = useState('')
    const [success, setSuccess] = useState('')

    // Curator key setup
    const [curatorKeyInput, setCuratorKeyInput] = useState('')
    const [showKeySetup, setShowKeySetup] = useState(!hasCuratorKey)

    // Tweet form
    const [showTweetForm, setShowTweetForm] = useState(false)
    const [editingTweet, setEditingTweet] = useState(null)
    const [submitting, setSubmitting] = useState(false)

    // Delete confirmation
    const [deletingId, setDeletingId] = useState(null)
    const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)

    // Attach dialog
    const [attachingTweet, setAttachingTweet] = useState(null)
    const [attachNewsletterId, setAttachNewsletterId] = useState('')

    // Newsletter generation
    const [generating, setGenerating] = useState(false)

    const saveCuratorKey = () => {
        APIService.setCuratorKey(curatorKeyInput)
        setShowKeySetup(false)
        setCuratorKeyInput('')
        loadTeams()
    }

    const loadTeams = useCallback(async () => {
        try {
            setLoading(true)
            const data = await APIService.getCuratorTeams()
            setTeams(data?.teams || [])
            if (data?.teams?.length && !selectedTeamId) {
                setSelectedTeamId(String(data.teams[0].id))
            }
        } catch (err) {
            console.error('Failed to load curator teams', err)
            setError(err.message || 'Failed to load teams')
        } finally {
            setLoading(false)
        }
    }, [selectedTeamId])

    const loadTeamData = useCallback(async () => {
        if (!selectedTeamId) return
        try {
            const [nlData, twData, plData] = await Promise.all([
                APIService.getCuratorNewsletters({ team_id: selectedTeamId }),
                APIService.getCuratorTweets({ team_id: selectedTeamId }),
                APIService.getCuratorPlayers({ team_id: selectedTeamId }),
            ])
            setNewsletters(nlData?.newsletters || [])
            setTweets(twData?.tweets || [])
            setPlayers(plData?.players || [])
        } catch (err) {
            console.error('Failed to load team data', err)
            setError(err.message || 'Failed to load team data')
        }
    }, [selectedTeamId])

    useEffect(() => {
        if (hasCuratorKey || APIService.curatorKey) {
            loadTeams()
        }
    }, [hasCuratorKey, loadTeams])

    useEffect(() => {
        if (selectedTeamId) {
            loadTeamData()
        }
    }, [selectedTeamId, loadTeamData])

    const handleTeamChange = (teamId) => {
        setSelectedTeamId(teamId)
        setError('')
        setSuccess('')
    }

    const handleCreateTweet = async (payload) => {
        setSubmitting(true)
        setError('')
        try {
            if (editingTweet) {
                await APIService.updateCuratorTweet(editingTweet.id, payload)
                setSuccess('Tweet updated')
            } else {
                await APIService.createCuratorTweet(payload)
                setSuccess('Tweet added')
            }
            setShowTweetForm(false)
            setEditingTweet(null)
            loadTeamData()
        } catch (err) {
            setError(err.message || 'Failed to save tweet')
        } finally {
            setSubmitting(false)
        }
    }

    const handleDelete = async () => {
        if (!deletingId) return
        try {
            await APIService.deleteCuratorTweet(deletingId)
            setTweets(prev => prev.filter(t => t.id !== deletingId))
            setSuccess('Tweet deleted')
        } catch (err) {
            setError(err.message || 'Failed to delete tweet')
        } finally {
            setDeletingId(null)
            setShowDeleteConfirm(false)
        }
    }

    const handleAttach = async () => {
        if (!attachingTweet || !attachNewsletterId) return
        try {
            await APIService.attachCuratorTweet(attachingTweet.id, Number(attachNewsletterId))
            setSuccess('Tweet attached to newsletter')
            setAttachingTweet(null)
            setAttachNewsletterId('')
            loadTeamData()
        } catch (err) {
            setError(err.message || 'Failed to attach tweet')
        }
    }

    const handleDetach = async (tweetId) => {
        try {
            await APIService.detachCuratorTweet(tweetId)
            setSuccess('Tweet detached from newsletter')
            loadTeamData()
        } catch (err) {
            setError(err.message || 'Failed to detach tweet')
        }
    }

    const handleGenerateNewsletter = async () => {
        if (!selectedTeamId) return
        setGenerating(true)
        setError('')
        try {
            const result = await APIService.generateCuratorNewsletter({
                team_id: Number(selectedTeamId),
            })
            setSuccess(result?.message || 'Newsletter generated')
            loadTeamData()
        } catch (err) {
            setError(err.message || 'Failed to generate newsletter')
        } finally {
            setGenerating(false)
        }
    }

    const handleLogout = () => {
        logout()
        navigate('/')
    }

    // Key setup screen
    if (showKeySetup || (!hasCuratorKey && !APIService.curatorKey)) {
        return (
            <div className="max-w-md mx-auto mt-20 p-6">
                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <KeyRound className="h-5 w-5" />
                            Curator Access
                        </CardTitle>
                        <CardDescription>
                            Enter your curator key to access the tweet curation dashboard.
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <div>
                            <Label htmlFor="curatorKey">Curator Key</Label>
                            <Input
                                id="curatorKey"
                                type="password"
                                placeholder="Enter your curator key..."
                                value={curatorKeyInput}
                                onChange={e => setCuratorKeyInput(e.target.value)}
                                onKeyDown={e => e.key === 'Enter' && curatorKeyInput.trim() && saveCuratorKey()}
                            />
                        </div>
                        <Button onClick={saveCuratorKey} disabled={!curatorKeyInput.trim()} className="w-full">
                            Save Key
                        </Button>
                    </CardContent>
                </Card>
            </div>
        )
    }

    if (loading) {
        return (
            <div className="flex justify-center items-center min-h-[400px]">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
        )
    }

    return (
        <div className="max-w-5xl mx-auto p-6 space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold">Tweet Curator Dashboard</h1>
                    <p className="text-muted-foreground">Add tweets and attributions to newsletters</p>
                </div>
                <div className="flex gap-2">
                    <Button variant="outline" size="sm" onClick={() => setShowKeySetup(true)}>
                        <KeyRound className="h-4 w-4 mr-1" /> Key
                    </Button>
                    <Button variant="outline" size="sm" onClick={handleLogout}>
                        <LogOut className="h-4 w-4 mr-1" /> Logout
                    </Button>
                </div>
            </div>

            {/* Alerts */}
            {error && (
                <div className="bg-destructive/10 text-destructive px-4 py-3 rounded-md text-sm">
                    {error}
                    <button className="ml-2 underline" onClick={() => setError('')}>dismiss</button>
                </div>
            )}
            {success && (
                <div className="bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400 px-4 py-3 rounded-md text-sm">
                    {success}
                    <button className="ml-2 underline" onClick={() => setSuccess('')}>dismiss</button>
                </div>
            )}

            {/* Team Selector */}
            <Card>
                <CardHeader className="pb-3">
                    <CardTitle className="text-lg">Select Team</CardTitle>
                </CardHeader>
                <CardContent>
                    <Select value={selectedTeamId} onValueChange={handleTeamChange}>
                        <SelectTrigger className="w-full max-w-sm">
                            <SelectValue placeholder="Choose a team" />
                        </SelectTrigger>
                        <SelectContent>
                            {teams.map(t => (
                                <SelectItem key={t.id} value={String(t.id)}>{t.name}</SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </CardContent>
            </Card>

            {selectedTeamId && (
                <>
                    {/* Newsletter Section */}
                    <Card>
                        <CardHeader className="flex flex-row items-center justify-between pb-3">
                            <div>
                                <CardTitle className="text-lg">Newsletters</CardTitle>
                                <CardDescription>{newsletters.length} newsletter(s)</CardDescription>
                            </div>
                            <Button onClick={handleGenerateNewsletter} disabled={generating} size="sm">
                                {generating ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <FileText className="h-4 w-4 mr-1" />}
                                Generate Newsletter
                            </Button>
                        </CardHeader>
                        <CardContent>
                            {newsletters.length === 0 ? (
                                <p className="text-muted-foreground text-sm">No newsletters yet. Generate one to get started.</p>
                            ) : (
                                <div className="space-y-2">
                                    {newsletters.slice(0, 10).map(nl => (
                                        <div key={nl.id} className="flex items-center justify-between py-2 border-b last:border-0">
                                            <div>
                                                <span className="font-medium text-sm">{nl.title || `Newsletter #${nl.id}`}</span>
                                                <span className="text-xs text-muted-foreground ml-2">
                                                    {nl.week_start_date && nl.week_end_date
                                                        ? `${nl.week_start_date} - ${nl.week_end_date}`
                                                        : nl.issue_date || 'No date'}
                                                </span>
                                            </div>
                                            <div className="flex gap-1">
                                                {nl.published && <Badge variant="secondary">Published</Badge>}
                                                {nl.email_sent && <Badge variant="outline">Sent</Badge>}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </CardContent>
                    </Card>

                    {/* Tweets Section */}
                    <Card>
                        <CardHeader className="flex flex-row items-center justify-between pb-3">
                            <div>
                                <CardTitle className="text-lg">Tweets</CardTitle>
                                <CardDescription>{tweets.length} tweet(s) curated</CardDescription>
                            </div>
                            <Button onClick={() => { setEditingTweet(null); setShowTweetForm(true) }} size="sm">
                                <Plus className="h-4 w-4 mr-1" /> Add Tweet
                            </Button>
                        </CardHeader>
                        <CardContent>
                            {tweets.length === 0 ? (
                                <p className="text-muted-foreground text-sm">No tweets added yet. Click "Add Tweet" to curate content.</p>
                            ) : (
                                <div className="space-y-3">
                                    {tweets.map(tw => (
                                        <div key={tw.id} className="border rounded-lg p-4">
                                            <div className="flex items-start justify-between gap-4">
                                                <div className="flex-1 min-w-0">
                                                    <blockquote className="border-l-4 border-blue-400 pl-3 text-sm italic">
                                                        {tw.content}
                                                    </blockquote>
                                                    <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
                                                        <span className="font-medium">{tw.source_author}</span>
                                                        <span>&middot;</span>
                                                        <span>Twitter/X</span>
                                                        {tw.source_url && (
                                                            <>
                                                                <span>&middot;</span>
                                                                <a href={tw.source_url} target="_blank" rel="noopener noreferrer" className="underline">
                                                                    View
                                                                </a>
                                                            </>
                                                        )}
                                                        {tw.player_name && (
                                                            <>
                                                                <span>&middot;</span>
                                                                <Badge variant="outline" className="text-xs">{tw.player_name}</Badge>
                                                            </>
                                                        )}
                                                    </div>
                                                    {tw.newsletter_id && (
                                                        <div className="mt-1">
                                                            <Badge variant="secondary" className="text-xs">
                                                                Attached to Newsletter #{tw.newsletter_id}
                                                            </Badge>
                                                        </div>
                                                    )}
                                                </div>
                                                <div className="flex gap-1 shrink-0">
                                                    <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        className="h-8 w-8"
                                                        onClick={() => { setEditingTweet(tw); setShowTweetForm(true) }}
                                                        title="Edit"
                                                    >
                                                        <Pencil className="h-3.5 w-3.5" />
                                                    </Button>
                                                    {tw.newsletter_id ? (
                                                        <Button
                                                            variant="ghost"
                                                            size="icon"
                                                            className="h-8 w-8"
                                                            onClick={() => handleDetach(tw.id)}
                                                            title="Detach from newsletter"
                                                        >
                                                            <Unlink className="h-3.5 w-3.5" />
                                                        </Button>
                                                    ) : (
                                                        <Button
                                                            variant="ghost"
                                                            size="icon"
                                                            className="h-8 w-8"
                                                            onClick={() => { setAttachingTweet(tw); setAttachNewsletterId('') }}
                                                            title="Attach to newsletter"
                                                        >
                                                            <Link2 className="h-3.5 w-3.5" />
                                                        </Button>
                                                    )}
                                                    <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        className="h-8 w-8 text-destructive"
                                                        onClick={() => { setDeletingId(tw.id); setShowDeleteConfirm(true) }}
                                                        title="Delete"
                                                    >
                                                        <Trash2 className="h-3.5 w-3.5" />
                                                    </Button>
                                                </div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </>
            )}

            {/* Tweet Form Dialog */}
            <Dialog open={showTweetForm} onOpenChange={(open) => { if (!open) { setShowTweetForm(false); setEditingTweet(null) } }}>
                <DialogContent className="max-w-lg">
                    <DialogHeader>
                        <DialogTitle>{editingTweet ? 'Edit Tweet' : 'Add Tweet'}</DialogTitle>
                    </DialogHeader>
                    <TweetForm
                        teams={teams}
                        players={players}
                        onSubmit={handleCreateTweet}
                        loading={submitting}
                        initialData={editingTweet ? {
                            id: editingTweet.id,
                            content: editingTweet.content,
                            source_author: editingTweet.source_author,
                            source_url: editingTweet.source_url || '',
                            team_id: String(editingTweet.team_id || selectedTeamId),
                            player_id: editingTweet.player_id ? String(editingTweet.player_id) : '',
                            player_name: editingTweet.player_name || '',
                        } : { team_id: selectedTeamId }}
                    />
                </DialogContent>
            </Dialog>

            {/* Attach Dialog */}
            <Dialog open={!!attachingTweet} onOpenChange={(open) => { if (!open) setAttachingTweet(null) }}>
                <DialogContent className="max-w-sm">
                    <DialogHeader>
                        <DialogTitle>Attach to Newsletter</DialogTitle>
                    </DialogHeader>
                    <div className="space-y-4">
                        <Select value={attachNewsletterId} onValueChange={setAttachNewsletterId}>
                            <SelectTrigger><SelectValue placeholder="Select newsletter" /></SelectTrigger>
                            <SelectContent>
                                {newsletters.map(nl => (
                                    <SelectItem key={nl.id} value={String(nl.id)}>
                                        {nl.title || `Newsletter #${nl.id}`} ({nl.week_start_date || nl.issue_date || 'no date'})
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                        <Button onClick={handleAttach} disabled={!attachNewsletterId} className="w-full">
                            Attach
                        </Button>
                    </div>
                </DialogContent>
            </Dialog>

            {/* Delete Confirmation */}
            <AlertDialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Delete Tweet</AlertDialogTitle>
                        <AlertDialogDescription>
                            Are you sure you want to delete this tweet? This action cannot be undone.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel onClick={() => { setDeletingId(null); setShowDeleteConfirm(false) }}>
                            Cancel
                        </AlertDialogCancel>
                        <AlertDialogAction onClick={handleDelete}>Delete</AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </div>
    )
}
