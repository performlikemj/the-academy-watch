import { useState } from 'react'
import { CheckCircle2, Loader2, ShieldAlert } from 'lucide-react'

import { useAuth, useAuthUI } from '@/context/AuthContext'
import { APIService } from '@/lib/api'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'

const REPORT_REASONS = [
  { value: 'participant_safety', label: 'Safety concern' },
  { value: 'harassment', label: 'Harassment' },
  { value: 'spam', label: 'Spam or repeated contact' },
  { value: 'misrepresentation', label: 'Misrepresentation' },
  { value: 'inappropriate_content', label: 'Inappropriate content' },
  { value: 'other', label: 'Something else' },
]

function reportErrorMessage(error) {
  if (error?.status === 429) {
    return 'You’ve submitted several reports recently. Please wait before trying again.'
  }
  if (error?.status === 400) {
    return error?.body?.error || error?.message || 'Check the report and try again.'
  }
  return 'We couldn’t submit this report. Please try again.'
}

export function ContentReportDialog({ subjectId, subjectType = 'player_profile', className }) {
  const { token } = useAuth()
  const { openLoginModal, logout } = useAuthUI()
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState('inappropriate_content')
  const [details, setDetails] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState(null)

  const reset = () => {
    setReason('inappropriate_content')
    setDetails('')
    setSubmitted(false)
    setError(null)
  }

  const handleTrigger = (event) => {
    if (!token) {
      event.preventDefault()
      openLoginModal()
    }
  }

  const handleOpenChange = (nextOpen) => {
    if (submitting) return
    setOpen(nextOpen)
    if (!nextOpen) reset()
  }

  const handleSubmit = async () => {
    const normalizedSubjectId = String(subjectId ?? '').trim()
    if (!normalizedSubjectId || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      await APIService.submitContentReport({
        subject_type: subjectType,
        subject_id: normalizedSubjectId,
        reason_code: reason,
        details: details.trim() || null,
      })
      setSubmitted(true)
    } catch (requestError) {
      if (requestError?.status === 401) {
        logout()
        setOpen(false)
        reset()
        openLoginModal()
      } else {
        setError(reportErrorMessage(requestError))
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className={cn('text-muted-foreground hover:text-rose-700', className)}
          onClick={handleTrigger}
          aria-label="Report"
        >
          <ShieldAlert className="h-4 w-4" />
          Report
        </Button>
      </DialogTrigger>

        <DialogContent className="sm:max-w-md">
          {submitted ? (
            <div className="flex flex-col items-center gap-4 py-6 text-center" role="status">
              <span className="inline-flex h-14 w-14 items-center justify-center rounded-full bg-emerald-100 text-emerald-700">
                <CheckCircle2 className="h-7 w-7" />
              </span>
              <DialogHeader className="items-center sm:text-center">
                <DialogTitle>Report submitted</DialogTitle>
                <DialogDescription>
                  Thanks for letting us know. Academy Watch will review it.
                </DialogDescription>
              </DialogHeader>
              <Button onClick={() => handleOpenChange(false)}>Done</Button>
            </div>
          ) : (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2">
                  <ShieldAlert className="h-5 w-5 text-rose-700" />
                  Report profile
                </DialogTitle>
                <DialogDescription>
                  Report this player profile for content that violates the community rules. Our team reviews every report.
                </DialogDescription>
              </DialogHeader>

              <div className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="content-report-reason">Reason</Label>
                  <Select value={reason} onValueChange={setReason}>
                    <SelectTrigger id="content-report-reason" className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {REPORT_REASONS.map((option) => (
                        <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <div className="flex items-center justify-between gap-3">
                    <Label htmlFor="content-report-details">Details (optional)</Label>
                    <span className="text-xs tabular-nums text-muted-foreground">{details.length}/2,000</span>
                  </div>
                  <Textarea
                    id="content-report-details"
                    value={details}
                    onChange={(event) => setDetails(event.target.value)}
                    maxLength={2000}
                    rows={5}
                    placeholder="Share what the moderation team should review."
                  />
                  <p className="text-xs text-muted-foreground">
                    Share only what helps the moderation team understand the concern.
                  </p>
                </div>
              </div>

              {error ? (
                <Alert className="border-rose-300 bg-rose-50">
                  <ShieldAlert className="h-4 w-4 text-rose-700" />
                  <AlertDescription className="text-rose-900">{error}</AlertDescription>
                </Alert>
              ) : null}

              <DialogFooter>
                <Button variant="outline" onClick={() => handleOpenChange(false)} disabled={submitting}>
                  Cancel
                </Button>
                <Button onClick={handleSubmit} disabled={submitting || !String(subjectId ?? '').trim()}>
                  {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                  {submitting ? 'Submitting…' : 'Submit report'}
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
    </Dialog>
  )
}

export default ContentReportDialog
