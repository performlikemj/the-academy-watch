import { useState } from 'react'
import { APIService } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { CheckCircle2, Loader2, Send } from 'lucide-react'

const MAX_CONTENT_LENGTH = 280

/**
 * QuickTakeForm - Public form for submitting community takes about players.
 *
 * Props:
 * - playerName: Optional pre-filled player name
 * - playerId: Optional player API ID
 * - teamId: Optional team ID
 * - onSuccess: Optional callback after successful submission
 * - compact: If true, uses a more compact layout
 */
export function QuickTakeForm({
    playerName: initialPlayerName = '',
    playerId = null,
    teamId = null,
    onSuccess = null,
    compact = false
}) {
    const [playerName, setPlayerName] = useState(initialPlayerName)
    const [content, setContent] = useState('')
    const [submitterName, setSubmitterName] = useState('')
    const [submitterEmail, setSubmitterEmail] = useState('')
    const [loading, setLoading] = useState(false)
    const [success, setSuccess] = useState(false)
    const [error, setError] = useState(null)

    const handleSubmit = async (e) => {
        e.preventDefault()

        if (!playerName.trim()) {
            setError('Please enter the player name')
            return
        }
        if (!content.trim()) {
            setError('Please enter your take')
            return
        }
        if (content.length > MAX_CONTENT_LENGTH) {
            setError(`Take must be ${MAX_CONTENT_LENGTH} characters or less`)
            return
        }

        setLoading(true)
        setError(null)

        try {
            await APIService.submitQuickTake({
                player_name: playerName.trim(),
                player_id: playerId,
                team_id: teamId,
                content: content.trim(),
                submitter_name: submitterName.trim() || null,
                submitter_email: submitterEmail.trim() || null,
            })

            setSuccess(true)
            setContent('')
            if (onSuccess) onSuccess()
        } catch (err) {
            setError(err.message || 'Failed to submit take. Please try again.')
        } finally {
            setLoading(false)
        }
    }

    if (success) {
        return (
            <Card className={compact ? 'border-green-200 bg-green-50' : ''}>
                <CardContent className="pt-6">
                    <div className="text-center">
                        <CheckCircle2 className="h-12 w-12 text-green-600 mx-auto mb-3" />
                        <h3 className="font-semibold text-lg mb-2">Take Submitted!</h3>
                        <p className="text-muted-foreground mb-4">
                            Thanks for your take! It will be reviewed before publication.
                        </p>
                        <Button
                            variant="outline"
                            onClick={() => setSuccess(false)}
                        >
                            Submit Another
                        </Button>
                    </div>
                </CardContent>
            </Card>
        )
    }

    if (compact) {
        return (
            <form onSubmit={handleSubmit} className="space-y-3">
                {error && (
                    <Alert variant="destructive" className="py-2">
                        <AlertDescription>{error}</AlertDescription>
                    </Alert>
                )}

                {!initialPlayerName && (
                    <Input
                        value={playerName}
                        onChange={(e) => setPlayerName(e.target.value)}
                        placeholder="Player name"
                        disabled={loading}
                    />
                )}

                <Textarea
                    value={content}
                    onChange={(e) => setContent(e.target.value)}
                    placeholder="Share your take on this player..."
                    rows={2}
                    disabled={loading}
                    maxLength={MAX_CONTENT_LENGTH}
                />
                <div className="flex justify-between items-center">
                    <span className="text-xs text-muted-foreground">
                        {content.length}/{MAX_CONTENT_LENGTH}
                    </span>
                    <Button type="submit" size="sm" disabled={loading}>
                        {loading ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                            <>
                                <Send className="h-4 w-4 mr-1" />
                                Submit
                            </>
                        )}
                    </Button>
                </div>
            </form>
        )
    }

    return (
        <Card>
            <CardHeader>
                <CardTitle>Share Your Take</CardTitle>
                <CardDescription>
                    Submit a quick take about a player. Your take will be reviewed before publication.
                </CardDescription>
            </CardHeader>
            <CardContent>
                <form onSubmit={handleSubmit} className="space-y-4">
                    {error && (
                        <Alert variant="destructive">
                            <AlertDescription>{error}</AlertDescription>
                        </Alert>
                    )}

                    <div className="space-y-2">
                        <Label htmlFor="player-name">Player Name *</Label>
                        <Input
                            id="player-name"
                            value={playerName}
                            onChange={(e) => setPlayerName(e.target.value)}
                            placeholder="e.g., Kobbie Mainoo"
                            disabled={loading || !!initialPlayerName}
                        />
                    </div>

                    <div className="space-y-2">
                        <Label htmlFor="take-content">Your Take *</Label>
                        <Textarea
                            id="take-content"
                            value={content}
                            onChange={(e) => setContent(e.target.value)}
                            placeholder="Share your opinion on this player's performance, potential, or current spell..."
                            rows={3}
                            disabled={loading}
                            maxLength={MAX_CONTENT_LENGTH}
                        />
                        <p className="text-xs text-muted-foreground text-right">
                            {content.length}/{MAX_CONTENT_LENGTH} characters
                        </p>
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-2">
                            <Label htmlFor="submitter-name">Your Name (optional)</Label>
                            <Input
                                id="submitter-name"
                                value={submitterName}
                                onChange={(e) => setSubmitterName(e.target.value)}
                                placeholder="Anonymous if blank"
                                disabled={loading}
                            />
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="submitter-email">Email (optional)</Label>
                            <Input
                                id="submitter-email"
                                type="email"
                                value={submitterEmail}
                                onChange={(e) => setSubmitterEmail(e.target.value)}
                                placeholder="For notifications"
                                disabled={loading}
                            />
                        </div>
                    </div>

                    <Button type="submit" className="w-full" disabled={loading}>
                        {loading ? (
                            <>
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                Submitting...
                            </>
                        ) : (
                            <>
                                <Send className="mr-2 h-4 w-4" />
                                Submit Take
                            </>
                        )}
                    </Button>

                    <p className="text-xs text-muted-foreground text-center">
                        By submitting, you agree that your take may be published in our newsletters.
                    </p>
                </form>
            </CardContent>
        </Card>
    )
}
