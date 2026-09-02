import { useEffect, useRef, useState } from 'react'
import { Heart, Share2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useAuth, useAuthUI } from '@/context/AuthContext'
import { APIService } from '@/lib/api'

function fanLabel(count) {
  if (count === 0) return 'Be the first fan'
  return `${count.toLocaleString()} ${count === 1 ? 'fan' : 'fans'}`
}

export function PlayerReachControls({ signedId, onPublicConfirmed }) {
  const { token } = useAuth()
  const { openLoginModal } = useAuthUI()
  const signedIdKey = signedId == null ? '' : String(signedId)
  const requestKey = `${signedIdKey}:${token || 'public'}`
  const confirmedIdsRef = useRef(new Set())
  const copyTimerRef = useRef(null)
  const [reach, setReach] = useState(null)
  const [busyRequestKey, setBusyRequestKey] = useState(null)
  const [note, setNote] = useState(null)
  const [copied, setCopied] = useState(false)
  const busy = busyRequestKey === requestKey

  useEffect(() => {
    return () => {
      if (copyTimerRef.current) clearTimeout(copyTimerRef.current)
    }
  }, [])

  useEffect(() => {
    if (!signedIdKey) return undefined

    let cancelled = false

    APIService.getPlayerFanCount(signedIdKey)
      .then((response) => {
        if (cancelled) return
        setReach({
          requestKey,
          fans: Math.max(0, Number(response?.fans) || 0),
          following: response?.following === true,
          shareUrl: String(response?.share_url || ''),
        })
        setBusyRequestKey(null)
        setNote(null)
        setCopied(false)
        if (!confirmedIdsRef.current.has(signedIdKey)) {
          confirmedIdsRef.current.add(signedIdKey)
          onPublicConfirmed?.(signedId)
        }
      })
      .catch(() => {
        if (!cancelled) setReach(null)
      })

    return () => { cancelled = true }
  }, [onPublicConfirmed, requestKey, signedId, signedIdKey])

  const toggleFollow = async () => {
    if (!token) {
      openLoginModal()
      return
    }
    if (!reach || busy) return

    const previous = reach
    const nextFollowing = !previous.following
    const nextFans = Math.max(0, previous.fans + (nextFollowing ? 1 : -1))
    setReach({ ...previous, following: nextFollowing, fans: nextFans })
    setBusyRequestKey(requestKey)
    setNote(null)

    try {
      const response = nextFollowing
        ? await APIService.followPlayer(signedIdKey)
        : await APIService.unfollowPlayer(signedIdKey)
      setReach((current) => current?.requestKey === previous.requestKey
        ? {
            ...current,
            following: response?.following === true,
            fans: Number.isInteger(response?.fans) ? response.fans : current.fans,
          }
        : current)
    } catch (error) {
      setReach((current) => current?.requestKey === previous.requestKey ? previous : current)
      setNote({
        requestKey: previous.requestKey,
        text: error?.status === 400
          ? error?.body?.error || 'You cannot follow your own profile'
          : 'We couldn\'t update your follow. Try again.',
      })
    } finally {
      setBusyRequestKey((current) => current === previous.requestKey ? null : current)
    }
  }

  const shareProfile = async () => {
    if (!reach?.shareUrl) return
    setNote(null)
    if (typeof navigator.share === 'function') {
      try {
        await navigator.share({ url: reach.shareUrl })
      } catch (error) {
        if (error?.name !== 'AbortError') {
          setNote({ requestKey, text: 'Sharing is unavailable right now.' })
        }
      }
      return
    }

    try {
      await navigator.clipboard.writeText(reach.shareUrl)
      setCopied(true)
      if (copyTimerRef.current) clearTimeout(copyTimerRef.current)
      copyTimerRef.current = setTimeout(() => {
        setCopied(false)
        copyTimerRef.current = null
      }, 2000)
    } catch {
      setNote({ requestKey, text: 'Copying is unavailable right now.' })
    }
  }

  if (!reach || reach.requestKey !== requestKey) return null

  return (
    <div
      className="mt-3 flex flex-wrap items-center gap-2 rounded-xl border border-rose-200/80 bg-gradient-to-r from-rose-50/90 via-card to-card p-2.5 shadow-sm dark:border-rose-900/60 dark:from-rose-950/35"
      data-testid="player-reach-controls"
    >
      <div className="inline-flex min-h-9 items-center gap-2 rounded-lg bg-card/80 px-3 text-sm font-semibold text-foreground">
        <Heart className="h-4 w-4 fill-rose-500 text-rose-600" aria-hidden="true" />
        <span className="tabular-nums">{fanLabel(reach.fans)}</span>
      </div>
      <Button
        type="button"
        size="sm"
        variant={reach.following ? 'default' : 'outline'}
        className={reach.following
          ? 'gap-1.5 bg-rose-600 text-white hover:bg-rose-700'
          : 'gap-1.5 border-rose-300 text-rose-700 hover:bg-rose-50 hover:text-rose-800 dark:border-rose-800 dark:text-rose-300 dark:hover:bg-rose-950/50'}
        aria-pressed={reach.following}
        disabled={busy}
        onClick={toggleFollow}
      >
        <Heart className={`h-4 w-4 ${reach.following ? 'fill-current' : ''}`} aria-hidden="true" />
        {reach.following ? 'Following' : 'Follow'}
      </Button>
      <div className="relative">
        {copied ? (
          <span
            className="absolute bottom-[calc(100%+0.5rem)] right-0 z-20 whitespace-nowrap rounded-md bg-foreground px-2.5 py-1.5 text-xs font-medium text-background shadow-lg"
            role="status"
          >
            Link copied
          </span>
        ) : null}
        <Button type="button" size="sm" variant="ghost" className="gap-1.5" onClick={shareProfile}>
          <Share2 className="h-4 w-4" aria-hidden="true" />
          Share
        </Button>
      </div>
      {note?.requestKey === requestKey ? (
        <p className="basis-full px-1 text-xs font-medium text-rose-700 dark:text-rose-300" role="status">
          {note.text}
        </p>
      ) : null}
    </div>
  )
}

export default PlayerReachControls
