import { useCallback, useEffect, useMemo, useState } from 'react'
import { useAuth } from '@/context/AuthContext'
import { APIService } from '@/lib/api'
import { confirmedClubName, linesReadState, profileFacts, publicPhotos } from '@/lib/player-card'

/**
 * Read-only data for the player hero, facts strip and season block.
 *
 * The showcase (approved profile, approved public photos, public affiliations)
 * is NOT fetched here: `ShowcaseSection` already loads it for the page and
 * hands it over, so the page asks once. This hook adds one request — the match
 * entries merged server-side into one line per match.
 *
 * A failed read is never shown as an empty season: `linesError` is set, the
 * last good data for the same player and viewer stays on screen, and `retry`
 * asks again. Nothing here widens who can see what.
 */
export function usePlayerReadView({ matchPlayerApiId, showcase = null, revision = 0 }) {
  const { token } = useAuth()
  const [attempt, setAttempt] = useState(0)
  const subjectKey = matchPlayerApiId == null || matchPlayerApiId === '' ? null : `${matchPlayerApiId}:${token || 'public'}`
  const requestKey = `${subjectKey}:${revision}:${attempt}`
  const [good, setGood] = useState({ subjectKey: null, seasons: [], truncated: false })
  const [settled, setSettled] = useState({ requestKey: null, failed: false })

  useEffect(() => {
    if (subjectKey == null) return undefined
    let cancelled = false
    const succeed = (response) => {
      if (cancelled) return
      setGood({
        subjectKey,
        seasons: Array.isArray(response?.seasons) ? response.seasons : [],
        truncated: response?.truncated === true,
      })
      setSettled({ requestKey, failed: false })
    }
    APIService.getPlayerMatches(matchPlayerApiId, { view: 'lines' })
      .then(succeed)
      .catch((error) => {
        if (cancelled) return
        // 404 is the route's answer for "no match entries to show for this
        // identity" (as on the raw list): an empty result, not a failure.
        if (error?.status === 404) succeed(null)
        else setSettled({ requestKey, failed: true })
      })
    return () => { cancelled = true }
  }, [matchPlayerApiId, requestKey, subjectKey])

  const retry = useCallback(() => setAttempt((value) => value + 1), [])
  const state = linesReadState({ good, settled, subjectKey, requestKey })
  const { hasLines, seasons, truncated, linesLoading, linesError } = state

  return useMemo(() => {
    const profile = showcase?.profile || null
    return {
      profile,
      bio: typeof profile?.bio === 'string' && profile.bio.trim() ? profile.bio.trim() : null,
      facts: profileFacts(profile),
      photos: publicPhotos(showcase?.photos),
      confirmedBy: confirmedClubName(showcase?.affiliations),
      // The player's own approved claim — the scout desk's "contactable".
      contactable: showcase?.contactable === true,
      seasons,
      truncated,
      // Nothing to show yet and no answer yet.
      linesLoading,
      // The latest read failed. With `hasLines` the last good data is still shown.
      linesError,
      hasLines,
      retry,
    }
  }, [hasLines, linesError, linesLoading, retry, seasons, showcase, truncated])
}

export default usePlayerReadView
