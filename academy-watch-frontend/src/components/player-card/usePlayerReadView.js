import { useEffect, useMemo, useState } from 'react'
import { useAuth } from '@/context/AuthContext'
import { APIService } from '@/lib/api'
import { confirmedClubName, profileFacts, publicPhotos } from '@/lib/player-card'

/**
 * Read-only data for the player hero, facts strip and season block.
 * Both requests are the existing public reads: the showcase (approved profile,
 * approved public photos, public affiliations) and the match entries merged
 * server-side into one line per match. Nothing here widens who can see what;
 * a failed or forbidden read simply leaves that part of the page out.
 */
export function usePlayerReadView({ playerApiId, local = false, matchPlayerApiId, revision = 0 }) {
  const { token } = useAuth()
  const showcaseKey = `${local ? 'local' : 'api'}:${playerApiId}:${token || 'public'}`
  const linesKey = `${matchPlayerApiId}:${token || 'public'}:${revision}`
  const [showcaseState, setShowcaseState] = useState({ key: null, value: null })
  const [linesState, setLinesState] = useState({ key: null, seasons: [] })

  useEffect(() => {
    if (playerApiId == null || playerApiId === '') return undefined
    let cancelled = false
    APIService.getPlayerShowcase(playerApiId, { local })
      .then((value) => { if (!cancelled) setShowcaseState({ key: showcaseKey, value: value || null }) })
      .catch(() => { if (!cancelled) setShowcaseState({ key: showcaseKey, value: null }) })
    return () => { cancelled = true }
  }, [local, playerApiId, showcaseKey])

  useEffect(() => {
    if (matchPlayerApiId == null || matchPlayerApiId === '') return undefined
    let cancelled = false
    APIService.getPlayerMatches(matchPlayerApiId, { view: 'lines' })
      .then((response) => {
        if (cancelled) return
        setLinesState({ key: linesKey, seasons: Array.isArray(response?.seasons) ? response.seasons : [] })
      })
      .catch(() => { if (!cancelled) setLinesState({ key: linesKey, seasons: [] }) })
    return () => { cancelled = true }
  }, [linesKey, matchPlayerApiId])

  const showcase = showcaseState.key === showcaseKey ? showcaseState.value : null
  const showcaseLoaded = showcaseState.key === showcaseKey
  const linesLoaded = linesState.key === linesKey
  // Keep the last lines on screen while a refresh for the same player and viewer is in flight.
  const sameSubject = typeof linesState.key === 'string' && linesState.key.startsWith(`${matchPlayerApiId}:${token || 'public'}:`)
  const linesReady = linesLoaded || sameSubject
  const loadedSeasons = linesState.seasons

  return useMemo(() => {
    const profile = showcase?.profile || null
    return {
      showcaseLoaded,
      linesLoaded,
      profile,
      bio: typeof profile?.bio === 'string' && profile.bio.trim() ? profile.bio.trim() : null,
      facts: profileFacts(profile),
      photos: publicPhotos(showcase?.photos),
      confirmedBy: confirmedClubName(showcase?.affiliations),
      claimed: showcase?.claim_status === 'claimed',
      seasons: linesReady ? loadedSeasons : [],
    }
  }, [linesLoaded, linesReady, loadedSeasons, showcase, showcaseLoaded])
}

export default usePlayerReadView
