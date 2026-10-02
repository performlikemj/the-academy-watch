import { useCallback, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useAuth } from '@/context/AuthContext'
import { APIService } from '@/lib/api'
import { scopedValue, viewerKey, viewerStateWrite } from '@/lib/player-card'
import { createViewerLifetime } from '@/lib/viewer-lifetime'

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

/**
 * The lifetime of this component under this viewer. Every viewer-bound
 * component uses it instead of calling APIService or a global action directly:
 *
 *   const life = useViewerLifetime()
 *   const api = life.api                      // APIService, bound to this viewer
 *   const navigate = life.guard(useNavigate()) // no-op once unmounted / viewer changed
 *
 * Once the viewer has changed, `api.x()` throws StaleViewerError before sending
 * anything (so a multi-step handler cannot issue its follow-up request as the
 * next viewer), and guarded effects do nothing once the component is unmounted
 * or the viewer has changed.
 */
export function useViewerLifetime() {
  const viewer = useViewerKey()
  const lifetime = useMemo(() => {
    const life = createViewerLifetime({ viewer, currentViewer: () => viewerKey(APIService.userToken) })
    return { ...life, api: life.api(APIService) }
  }, [viewer])
  useLayoutEffect(() => {
    lifetime.mount()
    return () => lifetime.unmount()
  }, [lifetime])
  return lifetime
}

/** A side effect (navigate, logout, login prompt, toast) that only runs while `life` is alive. */
export function useGuarded(life, effect) {
  return useMemo(() => life.guard(effect), [effect, life])
}

export default useViewerState
