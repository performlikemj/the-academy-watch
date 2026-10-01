import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, ShieldCheck } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { APIService } from '@/lib/api'
import { useAuth, useAuthUI } from '@/context/AuthContext'
import { ROLE_LABELS } from '@/lib/staff-access'

// The token rides the URL fragment (#token=…) so it never reaches server logs or Referer headers.
function tokenFromHash() {
  if (typeof window === 'undefined') return ''
  return new URLSearchParams(window.location.hash.replace(/^#/, '')).get('token') || ''
}

const STATE_COPY = {
  invite_wrong_account: {
    title: 'This invite is for a different email',
    body: 'Sign out, then sign in with the email address the invitation was sent to.',
  },
  invite_expired: {
    title: 'This invite has expired',
    body: 'Ask the club to send you a new invitation.',
  },
  invite_revoked: {
    title: 'This invite is no longer active',
    body: 'The club withdrew or replaced this invitation. Ask them to send a new one if you still need access.',
  },
  invite_used: {
    title: 'This invite has already been used',
    body: 'Each invitation works once. If you accepted it, open My club to reach the club.',
  },
  invite_not_found: {
    title: 'We could not find this invite',
    body: 'Check that you opened the full link from the email, or ask the club to send a new one.',
  },
  already_has_access: {
    title: 'You already have access',
    body: 'Open My club to reach this club.',
  },
  invite_scope_unavailable: {
    title: 'This invite can’t be used',
    body: 'The squads it covered no longer exist. Ask the club to send a new invitation.',
  },
}

function Shell({ children }) {
  return (
    <div className="min-h-screen bg-chalk">
      <div className="floodlight-container flex min-h-[70vh] items-center justify-center py-16">
        <section className="w-full max-w-lg" aria-live="polite">{children}</section>
      </div>
    </div>
  )
}

export function StaffInviteAccept() {
  const navigate = useNavigate()
  const { token: authToken } = useAuth()
  const { openLoginModal } = useAuthUI()
  const [status, setStatus] = useState('idle')
  const [preview, setPreview] = useState(null)
  const [inviteToken, setInviteToken] = useState(tokenFromHash)
  useEffect(() => {
    const follow = () => { setInviteToken(tokenFromHash()); setPreview(null); setStatus('idle') }
    window.addEventListener('hashchange', follow)
    return () => window.removeEventListener('hashchange', follow)
  }, [])
  const [error, setError] = useState(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (!authToken || !inviteToken) return undefined
    let cancelled = false
    const timer = setTimeout(async () => {
      setStatus('loading')
      try {
        const data = await APIService.request('/me/staff-invites/preview', { method: 'POST', body: JSON.stringify({ token: inviteToken }) })
        if (cancelled) return
        setPreview(data)
        setStatus(data?.state === 'ready' ? 'ready' : 'blocked')
      } catch (requestError) {
        if (cancelled) return
        if (requestError?.status === 404) {
          setPreview({ state: 'invite_not_found' })
          setStatus('blocked')
        } else {
          setStatus('error')
        }
      }
    }, 0)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [authToken, inviteToken, attempt])

  const accept = useCallback(async () => {
    setStatus('accepting')
    setError(null)
    try {
      const data = await APIService.request('/me/staff-invites/accept', { method: 'POST', body: JSON.stringify({ token: inviteToken }) })
      navigate(`/my-club?program=${encodeURIComponent(data.program_id)}`)
    } catch (requestError) {
      const code = requestError?.body?.error
      if (code && STATE_COPY[code]) {
        setPreview({ state: code })
        setStatus('blocked')
      } else {
        setError('We could not accept the invitation. Try again in a moment.')
        setStatus('ready')
      }
    }
  }, [inviteToken, navigate])

  const heading = <p className="eyebrow mb-4 inline-flex items-center gap-2"><ShieldCheck className="h-3.5 w-3.5" />Club staff invitation</p>

  if (!inviteToken) {
    return <Shell>{heading}<h1 className="display text-[44px] sm:text-[56px]">{STATE_COPY.invite_not_found.title}</h1><p className="mt-4 text-muted-foreground">{STATE_COPY.invite_not_found.body}</p></Shell>
  }
  if (!authToken) {
    return (
      <Shell>
        {heading}
        <h1 className="display text-[44px] sm:text-[56px]">Join your club’s <em className="text-gold-text">private</em> home</h1>
        <p className="mt-4 text-muted-foreground">Sign in with the email address this invitation was sent to. We’ll email you a one-time code — no password needed.</p>
        <Button className="mt-8" onClick={openLoginModal}>Sign in to accept</Button>
      </Shell>
    )
  }
  if (status === 'error') {
    return <Shell>{heading}<h1 className="display text-[44px]">Something went wrong</h1><p className="mt-4 text-muted-foreground">We couldn’t check this invitation. Your link may still be fine.</p><Button className="mt-8" variant="outline" onClick={() => setAttempt((n) => n + 1)}>Try again</Button></Shell>
  }
  if (status === 'blocked') {
    const copy = STATE_COPY[preview?.state] || STATE_COPY.invite_not_found
    return (
      <Shell>
        {heading}
        <h1 className="display text-[44px] sm:text-[56px]">{copy.title}</h1>
        <p className="mt-4 text-muted-foreground">{copy.body}</p>
        {['invite_used', 'already_has_access'].includes(preview?.state) ? <Button className="mt-8" onClick={() => navigate('/my-club')}>Open My club</Button> : null}
      </Shell>
    )
  }
  if (status !== 'ready' && status !== 'accepting') {
    return <Shell><p role="status" className="inline-flex items-center text-muted-foreground"><Loader2 className="mr-2 h-5 w-5 animate-spin" />Checking your invitation…</p></Shell>
  }
  const role = ROLE_LABELS[preview?.role] || 'Staff'
  return (
    <Shell>
      {heading}
      <h1 className="display text-[44px] sm:text-[56px]">{preview?.program?.name || 'Your club'}</h1>
      <div className="mt-8 border-t border-hairline">
        <div className="rule-row flex items-center justify-between"><span className="text-muted-foreground">Your role</span><span className="font-mono text-xs uppercase tracking-[0.14em]">{role}</span></div>
      </div>
      <p className="mt-6 text-sm text-muted-foreground">Accepting gives this account access to the club’s private workspace for your role. The club can change or remove it at any time.</p>
      {error ? <p role="alert" className="mt-4 text-sm text-danger">{error}</p> : null}
      <div className="mt-8 flex flex-wrap gap-3">
        <Button onClick={accept} disabled={status === 'accepting'}>{status === 'accepting' ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : null}Accept invitation</Button>
        <Button variant="outline" onClick={() => navigate('/')}>Not now</Button>
      </div>
    </Shell>
  )
}

export default StaffInviteAccept
