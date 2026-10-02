import { useCallback, useLayoutEffect, useRef, useState } from 'react'
import { useAuth } from '@/context/AuthContext'
import { scopedValue, viewerKey, viewerStateWrite } from '@/lib/player-card'

/** Identity of the person looking: changes on logout, login and account switch. */
export function useViewerKey() {
  const { token } = useAuth()
  return viewerKey(token)
}

/**
 * State that belongs to the viewer (watchlist marks, an open dialog, …).
 *
 * The first line of defence is the keyed boundary of the page: on a viewer
 * change the page body remounts and this state is discarded with it. This hook
 * is the second: the value is only readable by the viewer it was written for,
 * and a setter made for one viewer does nothing once another viewer is on
 * screen — so a request A started that answers after the switch cannot touch
 * what B sees.
 */
export function useViewerState(viewer, initial = null) {
  const [entry, setEntry] = useState({ scope: viewer, value: initial })
  const currentRef = useRef(viewer)
  useLayoutEffect(() => {
    currentRef.current = viewer
  }, [viewer])
  const set = useCallback((next) => {
    setEntry((previous) => viewerStateWrite(previous, { writer: viewer, current: currentRef.current, next, initial }))
  }, [initial, viewer])
  const value = entry.scope === viewer ? scopedValue(entry, viewer) : initial
  return [value, set]
}

export default useViewerState
