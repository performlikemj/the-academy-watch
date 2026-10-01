/**
 * InterestSignup props: feature (required fixed feature key), showRole (false;
 * show optional role picker), role (optional fixed role), sourcePath (defaults
 * to current pathname), className (optional wrapper classes).
 * Uses inherited light/dark tokens. Stores interest only; sends no email.
 */
import { useId, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { APIService } from '@/lib/api'
import { INTEREST_ROLES, interestLabel } from '@/lib/interest'

export function InterestSignup({ feature, showRole = false, role, sourcePath, className = '' }) {
  const id = useId()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [selectedRole, setSelectedRole] = useState(role || '')
  const [website, setWebsite] = useState('')
  const [state, setState] = useState('idle')
  const [error, setError] = useState('')

  const submit = async (event) => {
    event.preventDefault()
    if (state === 'sending') return
    setState('sending')
    setError('')
    try {
      await APIService.submitInterest({ email, feature, role: showRole ? selectedRole || undefined : role,
        source_path: sourcePath ?? location.pathname, website })
      setState('success')
    } catch (err) {
      setError(err?.status === 429 ? 'Please wait a little before trying again.' :
        err?.body?.error || 'We couldn’t save your interest. Please try again.')
      setState('error')
    }
  }

  return (
    <div className={className}>
      {state === 'success' ? (
        <p role="status" className="border-t border-border py-6 text-lg">
          You're on the list. We'll email you when it opens.
        </p>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          {showRole && (
            <div className="space-y-2">
              <label htmlFor={`${id}-role`} className="eyebrow block">Your role <span>(optional)</span></label>
              <select id={`${id}-role`} value={selectedRole} onChange={(event) => setSelectedRole(event.target.value)}
                className="h-11 w-full rounded-md border border-input bg-background px-3 text-base focus-visible:ring-2 focus-visible:ring-ring">
                <option value="">Choose your role</option>
                {INTEREST_ROLES.map((value) => <option key={value} value={value}>{interestLabel(value)}</option>)}
              </select>
            </div>
          )}
          <div className="space-y-2">
            <label htmlFor={`${id}-email`} className="eyebrow block">Email address</label>
            <div className="flex flex-col gap-3 sm:flex-row">
              <Input id={`${id}-email`} type="email" name="email" autoComplete="email" required maxLength={254}
                value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com"
                aria-invalid={state === 'error'} aria-describedby={error ? `${id}-error` : undefined} />
              <Button type="submit" disabled={state === 'sending'}>
                {state === 'sending' ? 'Joining…' : "I'm interested"}
              </Button>
            </div>
          </div>
          <div hidden aria-hidden="true">
            <label htmlFor={`${id}-website`}>Website</label>
            <input id={`${id}-website`} name="website" tabIndex={-1} autoComplete="off" value={website}
              onChange={(event) => setWebsite(event.target.value)} />
          </div>
          {error && <p id={`${id}-error`} role="alert" className="text-sm">{error}</p>}
          <p className="text-xs leading-relaxed text-muted-foreground">
            Only updates about what you’ve signed up for. No marketing email is sent today.{' '}
            <Link to="/privacy" className="underline underline-offset-4">Privacy policy</Link>
          </p>
        </form>
      )}
    </div>
  )
}
