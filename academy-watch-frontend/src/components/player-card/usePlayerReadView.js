import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useAuth } from '@/context/AuthContext'
import { APIService } from '@/lib/api'
import {
  confirmedClubName,
  linesReadState,
  profileFacts,
  publicPhotos,
  scopedValue,
  showcaseScope,
  totalsReadState,
  viewerKey,
} from '@/lib/player-card'

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
 *
 * Everything is scoped to player + viewer. `showcase` must come from
 * `useScopedShowcase` (below), which withholds the previous viewer's showcase
 * at render time the moment the token changes.
 */
export function usePlayerReadView({ matchPlayerApiId, showcase = null, revision = 0 }) {
  const { token } = useAuth()
  const [attempt, setAttempt] = useState(0)
  const subjectKey = matchPlayerApiId == null || matchPlayerApiId === '' ? null : `${matchPlayerApiId}:${viewerKey(token)}`
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

/**
 * The showcase that `ShowcaseSection` loads, held for the page's read view.
 *
 * The showcase differs by viewer (the server adds the agent's email only for
 * signed-in readers; owners get more). So it is stored with the scope it was
 * loaded for — player + viewer — and is usable only while that is still the
 * scope on screen. On logout, login or an account switch the scope changes in
 * the same render, so the previous viewer's showcase is withheld immediately
 * and a late answer for the old scope is ignored.
 */
export function useScopedShowcase({ playerApiId, local = false }) {
  const { token } = useAuth()
  const scope = playerApiId == null || playerApiId === '' ? null : showcaseScope({ local, playerApiId, token })
  const [entry, setEntry] = useState({ scope: null, value: null })
  const currentScopeRef = useRef(scope)
  useLayoutEffect(() => {
    currentScopeRef.current = scope
  }, [scope])
  const accept = useCallback((value, loadedScope) => {
    // An answer for a scope that is no longer on screen is dropped; it must not
    // replace what the current viewer has already loaded.
    if (loadedScope == null || loadedScope !== currentScopeRef.current) return
    setEntry({ scope: loadedScope, value: value || null })
  }, [])
  return [scopedValue(entry, scope), accept, scope]
}

/**
 * The provider season totals (`GET /players/:id/season-stats`), tracked as its
 * own read: loading, failed (with retry) and last-good are kept apart, scoped
 * to player + viewer + season. A failure never turns into "no totals".
 */
export function useSeasonTotalsRead({ playerApiId, season, revision = 0, enabled = true }) {
  const { token } = useAuth()
  const [attempt, setAttempt] = useState(0)
  const active = enabled && playerApiId != null && playerApiId !== ''
  const scopeKey = active ? `${playerApiId}:${viewerKey(token)}:${season ?? 'default'}` : null
  const requestKey = `${scopeKey}:${revision}:${attempt}`
  const [good, setGood] = useState({ scopeKey: null, value: null })
  const [settled, setSettled] = useState({ requestKey: null, failed: false })

  useEffect(() => {
    if (scopeKey == null) return undefined
    let cancelled = false
    APIService.getPublicPlayerSeasonStats(playerApiId, season)
      .then((response) => {
        if (cancelled) return
        setGood({ scopeKey, value: response || null })
        setSettled({ requestKey, failed: false })
      })
      .catch((error) => {
        if (cancelled) return
        // "Not found" is an answer (no totals for this identity), not a failure.
        if (error?.status === 404) {
          setGood({ scopeKey, value: null })
          setSettled({ requestKey, failed: false })
        } else {
          setSettled({ requestKey, failed: true })
        }
      })
    return () => { cancelled = true }
  }, [playerApiId, requestKey, scopeKey, season])

  const retry = useCallback(() => setAttempt((value) => value + 1), [])
  // Totals a mutation response already carries (the owner just changed a game).
  const accept = useCallback((value) => {
    if (scopeKey == null) return
    setGood({ scopeKey, value: value || null })
  }, [scopeKey])
  const state = totalsReadState({ good, settled, scopeKey, requestKey })
  const { hasTotals, stats, totalsLoading, totalsError } = state
  const notFound = settled.requestKey === requestKey && !settled.failed && hasTotals && stats == null

  return useMemo(
    () => ({ stats, hasTotals, totalsLoading, totalsError, notFound, retry, accept }),
    [accept, hasTotals, notFound, retry, stats, totalsError, totalsLoading],
  )
}

export default usePlayerReadView
