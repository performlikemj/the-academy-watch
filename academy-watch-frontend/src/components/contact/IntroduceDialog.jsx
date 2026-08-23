import { useState, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'
import { Loader2, Send } from 'lucide-react'
import { APIService } from '@/lib/api'
import { MESSAGE_MAX, ATTESTATION_TEXT, describeIntroduceError, canSend } from '@/lib/introduce'

export function IntroduceDialog({ open, onOpenChange, player }) {
  const [message, setMessage] = useState('')
  const [attestationRequired, setAttestationRequired] = useState(false)
  const [attested, setAttested] = useState(false)
  const [sending, setSending] = useState(false)
  const [feedback, setFeedback] = useState(null) // { kind, message, href } | { kind: 'sent' }
  // Epoch of the dialog: bumped when it closes or moves to another player, so a send that lands late is ignored.
  const opSeq = useRef(0)

  useEffect(() => {
    opSeq.current += 1
    if (open) {
      setMessage('')
      setAttestationRequired(false)
      setAttested(false)
      setSending(false)
      setFeedback(null)
    }
  }, [open, player?.player_id])

  const playerName = player?.player_name || 'this player'

  const send = async () => {
    if (!player?.player_id || !canSend(message, attestationRequired, attested)) return
    const seq = opSeq.current
    setSending(true)
    setFeedback(null)
    try {
      await APIService.createContactRequest({
        player_api_id: player.player_id,
        message: message.trim(),
        permission_attestation: attestationRequired && attested,
      })
      if (seq !== opSeq.current) return
      setFeedback({ kind: 'sent' })
    } catch (err) {
      if (seq !== opSeq.current) return
      const described = describeIntroduceError(err)
      if (described.kind === 'attestation') setAttestationRequired(true)
      setFeedback(described)
    } finally {
      if (seq === opSeq.current) setSending(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Introduce yourself to {playerName}</DialogTitle>
          <DialogDescription>
            The player decides whether to accept. Contracted players may route through their club first.
          </DialogDescription>
        </DialogHeader>
        {feedback?.kind === 'sent' ? (
          <div className="space-y-3">
            <p className="text-sm text-foreground">Sent. You will see the reply under your introductions.</p>
            <Button onClick={() => onOpenChange(false)}>Done</Button>
          </div>
        ) : (
          <div className="space-y-3">
            <Textarea
              value={message}
              onChange={(e) => setMessage(e.target.value.slice(0, MESSAGE_MAX))}
              placeholder="Who you are, what you saw, what you are proposing…"
              rows={6}
              maxLength={MESSAGE_MAX}
              aria-label={`Message to ${playerName}`}
            />
            <div className="flex items-center justify-between text-[11px] text-muted-foreground tabular-nums">
              <span>{message.trim().length}/{MESSAGE_MAX}</span>
            </div>
            {attestationRequired ? (
              <label className="flex items-start gap-2 text-sm text-foreground">
                <Checkbox checked={attested} onCheckedChange={(v) => setAttested(v === true)} aria-label="Club permission attestation" />
                <span>{ATTESTATION_TEXT}</span>
              </label>
            ) : null}
            {feedback && feedback.kind !== 'sent' ? (
              <p className={`text-sm ${feedback.kind === 'error' ? 'text-rose-600' : 'text-amber-700'}`}>
                {feedback.message}{' '}
                {feedback.href ? <Link to={feedback.href} className="underline">Get verified</Link> : null}
              </p>
            ) : null}
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => onOpenChange(false)} disabled={sending}>Cancel</Button>
              <Button onClick={send} disabled={sending || !canSend(message, attestationRequired, attested)}>
                {sending ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Send className="mr-1.5 h-4 w-4" />}
                {attestationRequired ? 'Send with attestation' : 'Send introduction'}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

export default IntroduceDialog
