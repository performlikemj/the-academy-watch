import { useState } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { ArrowLeft, Loader2, CheckCircle2, AlertCircle } from 'lucide-react'
import { APIService } from '@/lib/api'

const CATEGORIES = [
    { value: 'stats', label: 'Incorrect Stats' },
    { value: 'player_data', label: 'Player Info (name, position, etc.)' },
    { value: 'club_assignment', label: 'Wrong Club Assignment' },
    { value: 'match_result', label: 'Incorrect Match Result' },
    { value: 'missing_data', label: 'Missing Data' },
    { value: 'transfer', label: 'Transfer Issue' },
    { value: 'other', label: 'Other' },
]

export function FlagData() {
    const [searchParams] = useSearchParams()
    const playerName = searchParams.get('player_name') || ''
    const playerId = searchParams.get('player_id') || ''
    const teamName = searchParams.get('team_name') || ''
    const newsletterId = searchParams.get('newsletter_id') || ''
    const source = searchParams.get('source') || 'website'

    const [category, setCategory] = useState('stats')
    const [reason, setReason] = useState('')
    const [email, setEmail] = useState('')
    const [submitting, setSubmitting] = useState(false)
    const [message, setMessage] = useState(null)
    const [submitted, setSubmitted] = useState(false)

    const handleSubmit = async (e) => {
        e.preventDefault()
        if (!reason.trim()) {
            setMessage({ type: 'error', text: 'Please describe the issue.' })
            return
        }
        setSubmitting(true)
        setMessage(null)
        try {
            await APIService.submitFlag({
                category,
                reason: reason.trim(),
                email: email.trim() || undefined,
                player_api_id: playerId ? parseInt(playerId, 10) : undefined,
                player_name: playerName || undefined,
                team_name: teamName || undefined,
                newsletter_id: newsletterId ? parseInt(newsletterId, 10) : undefined,
                source,
                page_url: window.location.href,
            })
            setSubmitted(true)
            setMessage({ type: 'success', text: 'Thank you! Your report has been submitted and will be reviewed.' })
        } catch (err) {
            setMessage({ type: 'error', text: err.message || 'Failed to submit. Please try again.' })
        } finally {
            setSubmitting(false)
        }
    }

    return (
        <div className="min-h-screen bg-background">
            <div className="container max-w-lg mx-auto py-8 px-4">
                <Link to="/">
                    <Button variant="ghost" className="mb-6">
                        <ArrowLeft className="h-4 w-4 mr-2" />
                        Back to Home
                    </Button>
                </Link>

                <div className="mb-8 text-center">
                    <h1 className="text-3xl font-bold tracking-tight mb-2">The Academy Watch</h1>
                    <p className="text-muted-foreground">
                        Report incorrect or missing data
                    </p>
                </div>

                <Card>
                    <CardHeader>
                        <CardTitle>Report a Data Issue</CardTitle>
                        <CardDescription>
                            Help us improve accuracy by flagging incorrect data. Our team reviews every submission.
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        {(playerName || teamName) && (
                            <div className="flex flex-wrap gap-1.5 mb-4">
                                {playerName && (
                                    <Badge variant="secondary" className="text-xs">{playerName}</Badge>
                                )}
                                {teamName && (
                                    <Badge variant="outline" className="text-xs">{teamName}</Badge>
                                )}
                                {newsletterId && (
                                    <Badge variant="outline" className="text-xs">From Newsletter</Badge>
                                )}
                            </div>
                        )}

                        {submitted ? (
                            <div className="text-center py-8">
                                <CheckCircle2 className="h-12 w-12 text-emerald-500 mx-auto mb-4" />
                                <h3 className="text-lg font-medium mb-2">Report Submitted</h3>
                                <p className="text-muted-foreground mb-6">
                                    Thank you for helping us improve our data accuracy.
                                </p>
                                <Link to="/">
                                    <Button variant="outline">Back to Home</Button>
                                </Link>
                            </div>
                        ) : (
                            <form onSubmit={handleSubmit} className="space-y-4">
                                <div>
                                    <Label className="text-xs">Issue Type</Label>
                                    <select
                                        className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                                        value={category}
                                        onChange={e => setCategory(e.target.value)}
                                    >
                                        {CATEGORIES.map(c => (
                                            <option key={c.value} value={c.value}>{c.label}</option>
                                        ))}
                                    </select>
                                </div>

                                <div>
                                    <Label className="text-xs">What's incorrect?</Label>
                                    <Textarea
                                        className="mt-1"
                                        placeholder="Describe what's wrong and what the correct data should be..."
                                        value={reason}
                                        onChange={e => setReason(e.target.value)}
                                        maxLength={1000}
                                        rows={5}
                                        required
                                    />
                                    <p className="text-xs text-muted-foreground mt-1">{reason.length}/1000</p>
                                </div>

                                <div>
                                    <Label className="text-xs">Email (optional)</Label>
                                    <Input
                                        className="mt-1"
                                        type="email"
                                        placeholder="Your email if you'd like follow-up"
                                        value={email}
                                        onChange={e => setEmail(e.target.value)}
                                    />
                                </div>

                                {message && (
                                    <Alert className={
                                        message.type === 'error'
                                            ? 'border-rose-500 bg-rose-50'
                                            : 'border-emerald-500 bg-emerald-50'
                                    }>
                                        {message.type === 'error'
                                            ? <AlertCircle className="h-4 w-4 text-rose-600" />
                                            : <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                                        }
                                        <AlertDescription className={
                                            message.type === 'error' ? 'text-rose-800' : 'text-emerald-800'
                                        }>
                                            {message.text}
                                        </AlertDescription>
                                    </Alert>
                                )}

                                <Button type="submit" className="w-full" disabled={submitting || !reason.trim()}>
                                    {submitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                                    Submit Report
                                </Button>
                            </form>
                        )}
                    </CardContent>
                </Card>

                <div className="mt-8 text-center text-sm text-muted-foreground">
                    <p>
                        We use data from API-Football. Some inconsistencies are upstream
                        and will be forwarded to the data provider.
                    </p>
                </div>
            </div>
        </div>
    )
}
