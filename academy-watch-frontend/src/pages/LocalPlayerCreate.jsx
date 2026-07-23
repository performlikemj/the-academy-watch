import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, CheckCircle2, Loader2, LogIn, ShieldCheck, UserPlus } from 'lucide-react'
import { APIService } from '@/lib/api'
import { useAuth, useAuthUI } from '@/context/AuthContext'
import { VerificationCode, VerificationInstructions } from '@/components/showcase/VerificationCode'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

const EMPTY_FORM = {
  display_name: '',
  birth_year: '',
  position: '',
  country: '',
  city: '',
  relationship_type: 'player',
}

const RELATIONSHIPS = [
  { value: 'player', label: 'Player' },
  { value: 'agent', label: 'Agent' },
  { value: 'guardian', label: 'Parent / Guardian' },
]

function SignedOutState({ onSignIn }) {
  return (
    <div className="mx-auto flex min-h-[70vh] max-w-6xl items-center justify-center px-4 py-12 sm:px-6 lg:px-8">
      <Card className="w-full max-w-md overflow-hidden border-border/80">
        <CardContent className="flex flex-col items-center gap-4 px-8 py-12 text-center">
          <span className="inline-flex h-14 w-14 items-center justify-center rounded-full bg-amber-100 text-amber-900">
            <UserPlus className="h-6 w-6" />
          </span>
          <div className="space-y-2">
            <h1 className="text-xl font-bold tracking-tight text-foreground">Sign in to create a player profile</h1>
            <p className="text-sm leading-relaxed text-muted-foreground">
              Your account will be linked to the profile so you can manage its showcase after review.
            </p>
          </div>
          <Button onClick={onSignIn}>
            <LogIn className="mr-1.5 h-4 w-4" />
            Sign in
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}

function AuthenticatedLocalPlayerCreate({ token }) {
  const [form, setForm] = useState(EMPTY_FORM)
  const [errors, setErrors] = useState({})
  const [submitting, setSubmitting] = useState(false)
  const [requestError, setRequestError] = useState(null)
  const [duplicate, setDuplicate] = useState(null)
  const [created, setCreated] = useState(null)
  const [copyState, setCopyState] = useState('idle')
  const activeTokenRef = useRef(token)

  useEffect(() => {
    activeTokenRef.current = token
    return () => { activeTokenRef.current = null }
  }, [token])

  const updateField = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }))
    setErrors((current) => {
      if (!current[field]) return current
      const next = { ...current }
      delete next[field]
      return next
    })
    setRequestError(null)
    setDuplicate(null)
  }

  const validate = () => {
    const next = {}
    const name = form.display_name.trim()
    const year = form.birth_year.trim()
    if (name.length < 2) next.display_name = 'Enter at least 2 characters.'
    if (name.length > 200) next.display_name = 'Use 200 characters or fewer.'
    if (year && !Number.isInteger(Number(year))) {
      next.birth_year = 'Enter a whole year, for example 2008.'
    }
    return next
  }

  const submit = async (event) => {
    event.preventDefault()
    if (submitting) return
    const validationErrors = validate()
    setErrors(validationErrors)
    if (Object.keys(validationErrors).length > 0) return

    const birthYear = form.birth_year.trim()
    const payload = {
      display_name: form.display_name.trim(),
      relationship_type: form.relationship_type,
    }
    if (birthYear) payload.birth_year = Number(birthYear)
    if (form.position.trim()) payload.position = form.position.trim()
    if (form.country.trim()) payload.country = form.country.trim()
    if (form.city.trim()) payload.city = form.city.trim()

    setSubmitting(true)
    setRequestError(null)
    setDuplicate(null)
    const requestToken = token
    try {
      const response = await APIService.createLocalPlayer(payload)
      if (activeTokenRef.current !== requestToken) return
      setCreated(response)
      setCopyState('idle')
    } catch (error) {
      if (activeTokenRef.current !== requestToken) return
      if (error?.status === 409) {
        const existing = error.body?.existing
        setDuplicate(existing && typeof existing === 'object' ? existing : {})
      } else {
        setRequestError(error?.body?.error || error?.message || 'Failed to create this profile')
      }
    } finally {
      if (activeTokenRef.current === requestToken) setSubmitting(false)
    }
  }

  const copyVerificationCode = async (code) => {
    if (!code) return
    if (typeof navigator === 'undefined' || !navigator.clipboard) {
      setCopyState('failed')
      return
    }
    try {
      await navigator.clipboard.writeText(code)
      setCopyState('copied')
    } catch {
      setCopyState('failed')
    }
  }

  if (created?.player) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-amber-50/60 via-background to-secondary/50">
        <div className="mx-auto max-w-2xl px-4 py-10 sm:px-6 lg:px-8">
          <Card className="overflow-hidden border-amber-200 shadow-sm">
            <CardHeader className="border-b border-amber-200/70 bg-amber-50/70">
              <div className="flex items-start gap-3">
                <span className="mt-0.5 inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-emerald-700">
                  <CheckCircle2 className="h-5 w-5" />
                </span>
                <div>
                  <CardTitle>Profile created and claimed</CardTitle>
                  <CardDescription className="mt-1">
                    {created.player.display_name} is now waiting for Academy Watch review.
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-5 py-6">
              <div className="flex items-start gap-2 rounded-lg border border-border/70 bg-secondary/40 p-3 text-sm text-foreground/80">
                <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                Keep this code safe. It belongs to the claim automatically created for your account.
              </div>
              <VerificationCode
                code={created.claim?.verification_code}
                copyState={copyState}
                onCopy={copyVerificationCode}
              />
              <VerificationInstructions includeProofStep={false} />
              <Button asChild className="w-full sm:w-auto">
                <Link to={`/local-players/${created.player.id}`}>
                  View your profile
                  <ArrowRight className="ml-1.5 h-4 w-4" />
                </Link>
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    )
  }

  const duplicateId = duplicate?.id
  const duplicateName = duplicate?.display_name
  const duplicateStatus = duplicate?.status
  const duplicateDetails = [
    duplicateName || null,
    duplicateStatus ? `Status: ${duplicateStatus}` : null,
  ].filter(Boolean).join(' · ')

  return (
    <div className="min-h-screen bg-gradient-to-b from-amber-50/60 via-background to-secondary/50">
      <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6 lg:px-8">
        <div className="mb-6 space-y-2">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-amber-800">Community profiles</p>
          <h1 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">Create a player profile</h1>
          <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground sm:text-base">
            For players outside official API-Football coverage. Details are self-reported and the profile stays private until review.
          </p>
        </div>

        {duplicate ? (
          <Alert className="mb-5 border-amber-300 bg-amber-50">
            <UserPlus className="h-4 w-4 text-amber-800" />
            <AlertDescription className="text-amber-950">
              <span className="font-semibold">A player with this name and birth year may already exist.</span>
              {duplicateId ? (
                <span className="mt-1 block">
                  {duplicateDetails ? <span>{duplicateDetails} — </span> : null}
                  <Link to={`/local-players/${duplicateId}`} className="font-semibold text-primary hover:underline">
                    View existing profile
                  </Link>
                </span>
              ) : null}
            </AlertDescription>
          </Alert>
        ) : null}

        {requestError ? (
          <Alert className="mb-5 border-rose-300 bg-rose-50">
            <AlertDescription className="text-rose-800">{requestError}</AlertDescription>
          </Alert>
        ) : null}

        <Card>
          <CardHeader>
            <CardTitle>Player details</CardTitle>
            <CardDescription>Only the display name is required. You can add more showcase details later.</CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-5" onSubmit={submit} noValidate>
              <div className="space-y-2">
                <Label htmlFor="local-player-display-name">Display name</Label>
                <Input
                  id="local-player-display-name"
                  value={form.display_name}
                  onChange={(event) => updateField('display_name', event.target.value)}
                  placeholder="Player name"
                  minLength={2}
                  maxLength={200}
                  autoComplete="name"
                  disabled={submitting}
                  aria-invalid={Boolean(errors.display_name)}
                  aria-describedby={errors.display_name ? 'local-player-display-name-error' : undefined}
                />
                {errors.display_name ? (
                  <p id="local-player-display-name-error" className="text-xs text-destructive" role="alert">
                    {errors.display_name}
                  </p>
                ) : null}
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="local-player-birth-year">Birth year (optional)</Label>
                  <Input
                    id="local-player-birth-year"
                    type="number"
                    step="1"
                    inputMode="numeric"
                    value={form.birth_year}
                    onChange={(event) => updateField('birth_year', event.target.value)}
                    placeholder="e.g. 2008"
                    disabled={submitting}
                    aria-invalid={Boolean(errors.birth_year)}
                    aria-describedby={errors.birth_year ? 'local-player-birth-year-error' : undefined}
                  />
                  {errors.birth_year ? (
                    <p id="local-player-birth-year-error" className="text-xs text-destructive" role="alert">
                      {errors.birth_year}
                    </p>
                  ) : null}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="local-player-position">Position (optional)</Label>
                  <Input
                    id="local-player-position"
                    value={form.position}
                    onChange={(event) => updateField('position', event.target.value)}
                    placeholder="e.g. Centre-forward"
                    disabled={submitting}
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="local-player-country">Country (optional)</Label>
                  <Input
                    id="local-player-country"
                    value={form.country}
                    onChange={(event) => updateField('country', event.target.value)}
                    autoComplete="country-name"
                    disabled={submitting}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="local-player-city">City (optional)</Label>
                  <Input
                    id="local-player-city"
                    value={form.city}
                    onChange={(event) => updateField('city', event.target.value)}
                    autoComplete="address-level2"
                    disabled={submitting}
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="local-player-relationship">Your relationship to the player</Label>
                <Select
                  value={form.relationship_type}
                  onValueChange={(value) => updateField('relationship_type', value)}
                  disabled={submitting}
                >
                  <SelectTrigger id="local-player-relationship">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {RELATIONSHIPS.map((relationship) => (
                      <SelectItem key={relationship.value} value={relationship.value}>
                        {relationship.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="flex flex-col-reverse gap-2 border-t border-border/70 pt-5 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-xs leading-relaxed text-muted-foreground">
                  Submitting creates a claim for your account automatically.
                </p>
                <Button type="submit" disabled={submitting} className="shrink-0">
                  {submitting ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <UserPlus className="mr-1.5 h-4 w-4" />}
                  {submitting ? 'Creating…' : 'Create profile'}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

export function LocalPlayerCreate() {
  const { token } = useAuth()
  const { openLoginModal } = useAuthUI()

  if (!token) return <SignedOutState onSignIn={openLoginModal} />

  return <AuthenticatedLocalPlayerCreate key={token} token={token} />
}

export default LocalPlayerCreate
