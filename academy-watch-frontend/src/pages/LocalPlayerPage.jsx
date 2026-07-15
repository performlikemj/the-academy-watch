import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { AlertTriangle, ArrowRight, MapPin, ShieldAlert, UserPlus } from 'lucide-react'
import { APIService } from '@/lib/api'
import { ShowcaseSection } from '@/components/ShowcaseSection'
import { useAuth } from '@/context/AuthContext'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

function LoadingState() {
  return (
    <div className="mx-auto max-w-6xl space-y-5 px-4 py-8 sm:px-6 lg:px-8" aria-busy="true">
      <p className="sr-only" role="status" aria-live="polite">Loading player profile…</p>
      <div className="space-y-3 py-4">
        <Skeleton className="h-4 w-36" />
        <Skeleton className="h-10 w-72 max-w-full" />
        <Skeleton className="h-5 w-96 max-w-full" />
      </div>
      <Skeleton className="h-20 w-full rounded-xl" />
      <Skeleton className="h-80 w-full rounded-xl" />
    </div>
  )
}

function MissingState() {
  return (
    <div className="mx-auto flex min-h-[65vh] max-w-6xl items-center justify-center px-4 py-12 sm:px-6 lg:px-8">
      <Card className="w-full max-w-xl overflow-hidden border-dashed">
        <CardContent className="flex flex-col items-center gap-4 px-6 py-12 text-center">
          <span className="inline-flex h-14 w-14 items-center justify-center rounded-full bg-amber-100 text-amber-800">
            <AlertTriangle className="h-6 w-6" />
          </span>
          <div className="space-y-2">
            <h1 className="text-xl font-bold tracking-tight text-foreground">
              This profile doesn&apos;t exist or isn&apos;t public yet
            </h1>
            <p className="text-sm leading-relaxed text-muted-foreground">
              It may still be waiting for review, or the profile link may be incorrect.
            </p>
          </div>
          <Link
            to="/local-players/new"
            className="inline-flex items-center gap-1.5 text-sm font-semibold text-primary hover:underline"
          >
            <UserPlus className="h-4 w-4" />
            Create a player profile
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </CardContent>
      </Card>
    </div>
  )
}

function LocalPlayerProfile({ numericPlayerId, onRetry }) {
  const [player, setPlayer] = useState(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    APIService.getLocalPlayer(numericPlayerId)
      .then((response) => {
        if (cancelled) return
        if (!response?.player) {
          setNotFound(true)
          return
        }
        setPlayer(response.player)
      })
      .catch((requestError) => {
        if (cancelled) return
        if (requestError.status === 404) {
          setNotFound(true)
        } else {
          setError(requestError.body?.error || requestError.message || 'Failed to load this profile')
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => { cancelled = true }
  }, [numericPlayerId])

  if (loading) return <LoadingState />
  if (notFound) return <MissingState />

  if (error || !player) {
    return (
      <div className="mx-auto flex min-h-[65vh] max-w-6xl items-center justify-center px-4 py-12 sm:px-6 lg:px-8">
        <Card className="w-full max-w-xl">
          <CardContent className="flex flex-col items-center gap-4 px-6 py-12 text-center">
            <AlertTriangle className="h-8 w-8 text-rose-600" />
            <div>
              <h1 className="font-semibold text-foreground">We couldn&apos;t load this profile</h1>
              <p className="mt-1 text-sm text-muted-foreground">{error || 'Try again in a moment.'}</p>
            </div>
            <Button variant="outline" onClick={onRetry}>
              Try again
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  const location = player.city
    ? [player.city, player.country].filter(Boolean).join(', ')
    : null
  const details = [
    player.birth_year != null ? `Born ${player.birth_year}` : null,
    player.position || null,
    !player.city ? player.country || null : null,
  ].filter(Boolean)

  return (
    <div className="min-h-screen bg-gradient-to-b from-amber-50/60 via-background to-secondary/50">
      <div className="mx-auto max-w-6xl space-y-6 px-4 py-8 sm:px-6 lg:px-8">
        <header className="relative overflow-hidden rounded-2xl border border-border/70 bg-card px-5 py-7 shadow-sm sm:px-8 sm:py-9">
          <div className="pointer-events-none absolute -right-20 -top-24 h-64 w-64 rounded-full bg-amber-200/25 blur-3xl" />
          <div className="relative space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-amber-800">Community player</p>
              {player.status === 'pending' ? (
                <Badge variant="outline" className="border-amber-300 bg-amber-50 text-amber-800">
                  Pending review
                </Badge>
              ) : null}
            </div>
            <h1 className="break-words text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
              {player.display_name}
            </h1>
            {details.length > 0 || location ? (
              <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-muted-foreground sm:text-base">
                {details.map((detail) => <span key={detail}>{detail}</span>)}
                {location ? (
                  <span className="inline-flex items-center gap-1.5">
                    <MapPin className="h-4 w-4" />
                    {location}
                  </span>
                ) : null}
              </div>
            ) : null}
          </div>
        </header>

        <Alert className="border-amber-300 bg-amber-50/95 shadow-sm">
          <ShieldAlert className="h-4 w-4 text-amber-800" />
          <AlertDescription className="font-medium leading-relaxed text-amber-950">
            Community profile — self-reported. Not an official Academy Watch tracked player.
          </AlertDescription>
        </Alert>

        <ShowcaseSection
          local
          playerApiId={numericPlayerId}
          playerName={player.display_name}
        />
      </div>
    </div>
  )
}

export function LocalPlayerPage() {
  const { localPlayerId } = useParams()
  const { token } = useAuth()
  const [attempt, setAttempt] = useState(0)
  const numericPlayerId = Number(localPlayerId)
  const validPlayerId = Number.isInteger(numericPlayerId) && numericPlayerId > 0

  if (!validPlayerId) return <MissingState />

  return (
    <LocalPlayerProfile
      key={`${numericPlayerId}-${attempt}-${token || 'public'}`}
      numericPlayerId={numericPlayerId}
      onRetry={() => setAttempt((value) => value + 1)}
    />
  )
}

export default LocalPlayerPage
