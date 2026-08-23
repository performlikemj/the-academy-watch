import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from '@/components/ui/card'
import { Loader2, CheckCircle, XCircle, ShieldCheck } from 'lucide-react'
import { APIService } from '@/lib/api'
import { describeConsentDecision, describeConsentOutcome, INVALID_LINK_COPY } from '@/lib/club-consent'

function Shell({ children }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <Card className="w-full max-w-md">{children}</Card>
    </div>
  )
}

export function ClubConsentPage() {
  const { token } = useParams()
  const navigate = useNavigate()
  // Status: 'loading' | 'ready' | 'submitting' | 'done' | 'invalid'
  const [status, setStatus] = useState('loading')
  const [decision, setDecision] = useState(null)
  const [outcome, setOutcome] = useState(null)

  useEffect(() => {
    let cancelled = false
    if (!token) {
      setStatus('invalid')
      return undefined
    }
    setStatus('loading')
    APIService.getClubConsentSummary(token)
      .then((res) => {
        if (cancelled) return
        setDecision(res?.decision || null)
        setStatus(res?.decision ? 'ready' : 'invalid')
      })
      .catch(() => { if (!cancelled) setStatus('invalid') })
    return () => { cancelled = true }
  }, [token])

  const handleConfirm = async () => {
    try {
      setStatus('submitting')
      const res = await APIService.submitClubConsent(token)
      setOutcome(res?.decision || null)
      setStatus('done')
    } catch {
      setStatus('invalid')
    }
  }

  if (status === 'loading') {
    return (
      <Shell>
        <CardContent className="pt-6">
          <div className="flex flex-col items-center gap-4">
            <Loader2 className="h-12 w-12 animate-spin text-primary" />
            <p className="text-lg text-muted-foreground">Checking your consent link...</p>
          </div>
        </CardContent>
      </Shell>
    )
  }

  if (status === 'invalid') {
    return (
      <Shell>
        <CardHeader>
          <div className="flex items-center gap-3">
            <XCircle className="h-8 w-8 text-rose-500" />
            <CardTitle className="text-rose-700">{INVALID_LINK_COPY.title}</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">{INVALID_LINK_COPY.body}</p>
        </CardContent>
        <CardFooter>
          <Button variant="outline" onClick={() => navigate('/')}>Return to Home</Button>
        </CardFooter>
      </Shell>
    )
  }

  if (status === 'done') {
    const copy = describeConsentOutcome(outcome)
    return (
      <Shell>
        <CardHeader>
          <div className="flex items-center gap-3">
            <CheckCircle className="h-8 w-8 text-emerald-500" />
            <CardTitle className="text-emerald-700">{copy.title}</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">{copy.body}</p>
        </CardContent>
        <CardFooter>
          <Button variant="outline" onClick={() => navigate('/my-club')}>Go to my club</Button>
        </CardFooter>
      </Shell>
    )
  }

  const copy = describeConsentDecision(decision)
  return (
    <Shell>
      <CardHeader>
        <div className="flex items-center gap-3">
          <div className="h-12 w-12 rounded-full bg-primary/10 flex items-center justify-center">
            <ShieldCheck className="h-6 w-6 text-primary" />
          </div>
          <div>
            <CardTitle>{copy.title}</CardTitle>
            <CardDescription>The Academy Watch · club consent</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">{copy.body}</p>
        <p className="text-xs text-muted-foreground">Only a club manager should answer this. The decision is recorded for the club and the scout.</p>
      </CardContent>
      <CardFooter className="flex gap-3">
        <Button variant="outline" onClick={() => navigate('/')}>Not now</Button>
        <Button
          className="flex-1"
          variant={copy.tone === 'decline' ? 'destructive' : 'default'}
          onClick={handleConfirm}
          disabled={status === 'submitting'}
        >
          {status === 'submitting' ? (<><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Sending...</>) : copy.confirmLabel}
        </Button>
      </CardFooter>
    </Shell>
  )
}

export default ClubConsentPage
