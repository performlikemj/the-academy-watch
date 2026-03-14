import React, { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Loader2 } from 'lucide-react'

function extractHandleFromUrl(url) {
    const match = (url || '').match(/https?:\/\/(?:twitter\.com|x\.com)\/([^/]+)\/status/)
    return match ? `@${match[1]}` : null
}

export function TweetForm({ teams, players, onSubmit, initialData, loading }) {
    const [form, setForm] = useState({
        content: '',
        source_author: '',
        source_url: '',
        team_id: '',
        player_id: '',
        player_name: '',
        newsletter_id: '',
        ...initialData,
    })

    useEffect(() => {
        if (initialData) {
            setForm(prev => ({ ...prev, ...initialData }))
        }
    }, [initialData])

    const handleUrlChange = (url) => {
        setForm(prev => {
            const next = { ...prev, source_url: url }
            if (!prev.source_author || prev.source_author === extractHandleFromUrl(prev.source_url)) {
                const handle = extractHandleFromUrl(url)
                if (handle) next.source_author = handle
            }
            return next
        })
    }

    const handlePlayerChange = (playerId) => {
        const player = players.find(p => String(p.player_id || p.id) === String(playerId))
        setForm(prev => ({
            ...prev,
            player_id: playerId || '',
            player_name: player?.name || '',
        }))
    }

    const handleSubmit = (e) => {
        e.preventDefault()
        const payload = {
            content: form.content.trim(),
            source_author: form.source_author.trim(),
            source_url: form.source_url.trim() || undefined,
            team_id: form.team_id ? Number(form.team_id) : undefined,
            player_id: form.player_id ? Number(form.player_id) : undefined,
            player_name: form.player_name.trim() || undefined,
            newsletter_id: form.newsletter_id ? Number(form.newsletter_id) : undefined,
        }
        onSubmit(payload)
    }

    const isValid = form.content.trim() && form.source_author.trim() && form.team_id

    return (
        <form onSubmit={handleSubmit} className="space-y-4">
            <div>
                <Label htmlFor="team_id">Team *</Label>
                <Select value={String(form.team_id || '')} onValueChange={v => setForm(prev => ({ ...prev, team_id: v }))}>
                    <SelectTrigger><SelectValue placeholder="Select team" /></SelectTrigger>
                    <SelectContent>
                        {(teams || []).map(t => (
                            <SelectItem key={t.id} value={String(t.id)}>{t.name}</SelectItem>
                        ))}
                    </SelectContent>
                </Select>
            </div>

            <div>
                <Label htmlFor="source_url">Tweet URL</Label>
                <Input
                    id="source_url"
                    placeholder="https://x.com/username/status/123..."
                    value={form.source_url}
                    onChange={e => handleUrlChange(e.target.value)}
                />
            </div>

            <div>
                <Label htmlFor="source_author">Twitter Handle *</Label>
                <Input
                    id="source_author"
                    placeholder="@username"
                    value={form.source_author}
                    onChange={e => setForm(prev => ({ ...prev, source_author: e.target.value }))}
                />
            </div>

            <div>
                <Label htmlFor="content">Tweet Content *</Label>
                <Textarea
                    id="content"
                    placeholder="Paste the tweet text here..."
                    rows={4}
                    value={form.content}
                    onChange={e => setForm(prev => ({ ...prev, content: e.target.value }))}
                />
            </div>

            <div>
                <Label htmlFor="player_id">Player (optional)</Label>
                <Select value={String(form.player_id || '')} onValueChange={handlePlayerChange}>
                    <SelectTrigger><SelectValue placeholder="Associate with a player" /></SelectTrigger>
                    <SelectContent>
                        <SelectItem value="">None</SelectItem>
                        {(players || []).map(p => (
                            <SelectItem key={p.player_id || p.id} value={String(p.player_id || p.id)}>
                                {p.name}
                            </SelectItem>
                        ))}
                    </SelectContent>
                </Select>
            </div>

            {/* Preview */}
            {form.content.trim() && form.source_author.trim() && (
                <Card className="bg-muted/50">
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm text-muted-foreground">Preview</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <blockquote className="border-l-4 border-blue-400 pl-4 italic">
                            <p className="text-sm">{form.content}</p>
                            <footer className="text-xs text-muted-foreground mt-2">
                                &mdash; {form.source_author} on Twitter/X
                                {form.source_url && (
                                    <> &middot; <a href={form.source_url} target="_blank" rel="noopener noreferrer" className="underline">View tweet</a></>
                                )}
                            </footer>
                        </blockquote>
                    </CardContent>
                </Card>
            )}

            <Button type="submit" disabled={!isValid || loading}>
                {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {initialData?.id ? 'Update Tweet' : 'Add Tweet'}
            </Button>
        </form>
    )
}
