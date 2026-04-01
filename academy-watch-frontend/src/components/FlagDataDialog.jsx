import { useState } from 'react'
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
    DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Loader2, CheckCircle2, AlertCircle } from 'lucide-react'
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

export function FlagDataDialog({ open, onOpenChange, context = {} }) {
    const [category, setCategory] = useState('stats')
    const [reason, setReason] = useState('')
    const [email, setEmail] = useState('')
    const [submitting, setSubmitting] = useState(false)
    const [message, setMessage] = useState(null)

    const reset = () => {
        setCategory('stats')
        setReason('')
        setEmail('')
        setMessage(null)
    }

    const handleSubmit = async () => {
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
                player_api_id: context.playerApiId || undefined,
                player_name: context.playerName || undefined,
                primary_team_api_id: context.teamApiId || undefined,
                team_name: context.teamName || undefined,
                newsletter_id: context.newsletterId || undefined,
                source: context.source || 'website',
                page_url: window.location.href,
            })
            setMessage({ type: 'success', text: 'Thank you! Your report has been submitted.' })
            setTimeout(() => {
                reset()
                onOpenChange(false)
            }, 2000)
        } catch (err) {
            setMessage({ type: 'error', text: err.message || 'Failed to submit. Please try again.' })
        } finally {
            setSubmitting(false)
        }
    }

    return (
        <Dialog open={open} onOpenChange={(v) => { if (!v) reset(); onOpenChange(v) }}>
            <DialogContent className="max-w-md">
                <DialogHeader>
                    <DialogTitle>Report Incorrect Data</DialogTitle>
                    <DialogDescription>
                        Help us improve accuracy by flagging data issues.
                    </DialogDescription>
                </DialogHeader>

                {(context.playerName || context.teamName) && (
                    <div className="flex flex-wrap gap-1.5">
                        {context.playerName && (
                            <Badge variant="secondary" className="text-xs">{context.playerName}</Badge>
                        )}
                        {context.teamName && (
                            <Badge variant="outline" className="text-xs">{context.teamName}</Badge>
                        )}
                    </div>
                )}

                <div className="space-y-3">
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
                            rows={4}
                        />
                        <p className="text-xs text-muted-foreground mt-1">{reason.length}/1000</p>
                    </div>

                    <div>
                        <Label className="text-xs">Email (optional)</Label>
                        <Input
                            className="mt-1"
                            type="email"
                            placeholder="Your email for follow-up"
                            value={email}
                            onChange={e => setEmail(e.target.value)}
                        />
                    </div>
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

                <DialogFooter>
                    <Button variant="outline" onClick={() => { reset(); onOpenChange(false) }}>
                        Cancel
                    </Button>
                    <Button onClick={handleSubmit} disabled={submitting || !reason.trim()}>
                        {submitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                        Submit Report
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}

export default FlagDataDialog
