import { useState, useEffect, useCallback, useRef } from 'react'
import { APIService } from '@/lib/api'
import { useAuth } from '@/context/AuthContext'

/**
 * Single source of truth for a player's showcase + the viewer's claim state.
 *
 * ProfileHero (claim CTA) and ShowcaseSection (claim strip, reel, profile
 * editing) both need this data — so it lives here and is fetched ONCE per
 * page load. There must be exactly one GET /players/<id>/showcase per load;
 * PlayerPage calls this hook once and passes the result to both consumers.
 */
export function useShowcase(playerApiId) {
  const { token } = useAuth()

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [showcase, setShowcase] = useState(null)
  const [myClaims, setMyClaims] = useState([])

  const fetchData = useCallback(async () => {
    const [sc, claims] = await Promise.all([
      APIService.getPlayerShowcase(playerApiId),
      token ? APIService.getMyClaims().catch(() => null) : Promise.resolve(null),
    ])
    const claimsArr = Array.isArray(claims) ? claims : claims?.claims || []
    return { sc, claimsArr }
  }, [playerApiId, token])

  // PlayerPage is reused across /players/:id navigations — track the active
  // player so an in-flight refresh for the previous player never lands.
  const activePlayerRef = useRef(playerApiId)

  useEffect(() => {
    let cancelled = false
    activePlayerRef.current = playerApiId
    setLoading(true)
    setError(false)
    fetchData()
      .then(({ sc, claimsArr }) => {
        if (cancelled) return
        setShowcase(sc || null)
        setMyClaims(claimsArr)
      })
      .catch(() => {
        if (!cancelled) setError(true)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [fetchData, playerApiId])

  const refresh = useCallback(async () => {
    const pid = playerApiId
    try {
      const { sc, claimsArr } = await fetchData()
      if (activePlayerRef.current !== pid) return
      setShowcase(sc || null)
      setMyClaims(claimsArr)
    } catch {
      // best-effort refresh
    }
  }, [fetchData, playerApiId])

  return { showcase, myClaims, loading, error, refresh }
}

/**
 * Derive the viewer-relative claim state for a player from the shared
 * showcase + claims data. Kept as a pure helper so hero and showcase strip
 * classify claim status identically.
 */
export function deriveClaimState(showcase, myClaims, playerApiId) {
  const claimStatus = showcase?.claim_status // 'unclaimed' | 'claimed'
  const myClaim = (myClaims || []).find(
    (c) => Number(c.player_api_id) === Number(playerApiId),
  )
  const isOwner = myClaim?.status === 'approved'
  const isPending = myClaim?.status === 'pending'
  const isRejected = myClaim?.status === 'rejected'
  const claimedByOther = claimStatus === 'claimed' && !isOwner
  // Only offer to claim an unclaimed profile the viewer has no claim on.
  const canClaim = !isOwner && !myClaim && claimStatus === 'unclaimed'
  return { claimStatus, myClaim, isOwner, isPending, isRejected, claimedByOther, canClaim }
}
