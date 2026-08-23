import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Loader2, ShieldCheck, Clock, XCircle } from 'lucide-react'
import { APIService } from '@/lib/api'
import { useAuth, useAuthUI } from '@/context/AuthContext'
import { buildVerificationPayload, describeVerificationStatus, canApply, LIMITS } from '@/lib/scout-verification'

const EMPTY = { full_name: '', organization: '', role_title: '', statement: '', evidence_text: '' }

function StatusIcon({ tone }) {
  if (tone === 'approved') return <ShieldCheck className="h-8 w-8 text-emerald-500" />
  if (tone === 'pending') return <Clock className="h-8 w-8 text-amber-500" />
  if (tone === 'rejected' || tone === 'revoked') return <XCircle className="h-8 w-8 text-rose-500" />
  return <ShieldCheck className="h-8 w-8 text-primary" />
}

export function ScoutVerificationPage() {
  const auth = useAuth()
  const { openLoginModal } = useAuthUI()
  const [loading, setLoading] = useState(true)
  const [verification, setVerification] = useState(null)
  const [fields, setFields] = useState(EMPTY)
  const [errors, setErrors] = useState([])
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!auth?.token) {
      setLoading(false)
      return undefined
    }
    let cancelled = false
    setLoading(true)
    APIService.getScoutVerification()
      .then((res) => { if (!cancelled) setVerification(res?.verification || null) })
      .catch(() => { if (!cancelled) setVerification(null) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [auth?.token])

  const update = (key) => (event) => setFields((current) => ({ ...current, [key]: event.target.value }))

  const handleSubmit = async (event) => {
    event.preventDefault()
    const built = buildVerificationPayload(fields)
    if (!built.ok) {
      setErrors(built.errors)
      return
    }
    setErrors([])
    setSubmitting(true)
    try {
      const res = await APIService.submitScoutVerification(built.payload)
      setVerification(res?.verification || null)
      setFields(EMPTY)
    } catch (err) {
      if (err?.status === 409 && err?.body?.verification) {
        setVerification(err.body.verification)
      } else {
        setErrors([err?.body?.error || err?.message || 'Could not submit. Try again.'])
      }
    } finally {
      setSubmitting(false)
    }
  }

  const status = describeVerificationStatus(verification)

  return (
    <div className="min-h-screen bg-background p-4">
      <div className="mx-auto w-full max-w-2xl space-y-4">
        <Card>
          <CardHeader>
            <div className="flex items-center gap-3">
              <StatusIcon tone={status.tone} />
              <div>
                <CardTitle>{status.title}</CardTitle>
                <CardDescription>{status.body}</CardDescription>
              </div>
            </div>
          </CardHeader>
          {!auth?.token ? (
            <CardFooter>
              <Button onClick={openLoginModal}>Sign in to apply</Button>
            </CardFooter>
          ) : loading ? (
            <CardContent className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Loading…</CardContent>
          ) : verification && !canApply(verification) ? (
            <CardContent className="space-y-1 text-sm text-muted-foreground">
              <p><span className="font-medium text-foreground">{verification.full_name}</span> · {verification.role_title} · {verification.organization}</p>
              <p>Submitted {verification.submitted_at ? new Date(verification.submitted_at).toLocaleDateString() : '—'}</p>
              <p><Link to="/scout" className="underline">Back to the Scout Desk</Link></p>
            </CardContent>
          ) : null}
        </Card>

        {auth?.token && !loading && canApply(verification) ? (
          <Card>
            <CardHeader>
              <CardTitle>Apply for verification</CardTitle>
              <CardDescription>Reviewed by a person. Use links that show your role — a club staff page, a federation listing, LinkedIn.</CardDescription>
            </CardHeader>
            <form onSubmit={handleSubmit}>
              <CardContent className="space-y-3">
                <Input value={fields.full_name} onChange={update('full_name')} placeholder="Full name" maxLength={LIMITS.full_name} aria-label="Full name" />
                <Input value={fields.organization} onChange={update('organization')} placeholder="Organisation (club, agency, federation)" maxLength={LIMITS.organization} aria-label="Organisation" />
                <Input value={fields.role_title} onChange={update('role_title')} placeholder="Your role (e.g. Head of Recruitment)" maxLength={LIMITS.role_title} aria-label="Role" />
                <Textarea value={fields.statement} onChange={update('statement')} placeholder="What do you scout, where, and for whom?" rows={5} maxLength={LIMITS.statement} aria-label="Statement" />
                <Textarea value={fields.evidence_text} onChange={update('evidence_text')} placeholder={'https:// links, one per line (max 10)'} rows={3} aria-label="Evidence links" />
                {errors.length > 0 ? (
                  <ul className="list-disc pl-5 text-sm text-rose-600">{errors.map((e) => <li key={e}>{e}</li>)}</ul>
                ) : null}
              </CardContent>
              <CardFooter>
                <Button type="submit" disabled={submitting}>
                  {submitting ? (<><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Submitting…</>) : 'Submit for review'}
                </Button>
              </CardFooter>
            </form>
          </Card>
        ) : null}
      </div>
    </div>
  )
}

export default ScoutVerificationPage
