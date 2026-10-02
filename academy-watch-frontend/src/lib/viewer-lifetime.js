// Requests and side effects belong to the viewer who started them.
//
// Remounting a page on a viewer change drops its component state, but it does
// not stop JavaScript that is already running: a handler awaiting a response
// carries on after the switch and would send its next request with the NEW
// viewer's credential, log the new viewer out on a late 401, or navigate them
// somewhere. A viewer lifetime (createViewerLifetime / useViewerLifetime),
// which every viewer-bound component talks through, closes that:
//
//  - requests made through `life.api` are bound to the viewer: once the viewer
//    has changed none can be started, and an answer that arrives after the
//    change is delivered as a StaleViewerError — never as a success, never as
//    an ordinary failure;
//  - guarded side effects (navigate, logout, login prompt, toast, a file
//    download) do nothing once the component is unmounted or the viewer has
//    changed.
//
// The shared request layer (APIService.request) is deliberately NOT bound:
// pages that do not remount on a viewer change still get their answers. Its
// one rule is that a 401 for a credential that is no longer current comes back
// as a plain failure, so nothing signs the current session out because of it.
//
// Pure module (no React, no network) so the rules are unit-tested.

export class StaleViewerError extends Error {
  constructor(message = 'The viewer changed before this request finished') {
    super(message)
    this.name = 'StaleViewerError'
    this.stale = true
  }
}

export function isStaleViewerError(error) {
  return Boolean(error) && (error instanceof StaleViewerError || error.name === 'StaleViewerError')
}

/**
 * One lifetime = one mounted component instance under one viewer.
 *
 * `currentViewer()` reads the live credential (not React state), so the guard
 * also holds in the gap between a credential change and the re-render.
 *
 *  - `sameViewer()`  the viewer this lifetime was created for is still the viewer.
 *  - `alive()`       …and the component is still mounted.
 *  - `api(client)`   a proxy of an API client: once the viewer has changed a
 *                    call returns a rejected StaleViewerError WITHOUT sending
 *                    (a rejection, not a throw, so `.catch` chains handle it),
 *                    and a result
 *                    that arrives after the change is delivered as
 *                    StaleViewerError. (Unmounting alone does not abort a
 *                    same-viewer write: the person who started a save is still
 *                    the one signed in, and half-finished saves help nobody.)
 *  - `guard(fn)`     wraps a side effect (navigate, logout, login prompt,
 *                    toast, download): it runs only while alive(), otherwise does nothing.
 */
export function createViewerLifetime({ viewer, currentViewer }) {
  const state = { mounted: false }
  const sameViewer = () => currentViewer() === viewer
  const alive = () => state.mounted && sameViewer()
  const assertSameViewer = () => {
    if (!sameViewer()) throw new StaleViewerError()
  }
  const proxies = new WeakMap()

  const api = (client) => {
    let proxy = proxies.get(client)
    if (proxy) return proxy
    proxy = new Proxy(client, {
      get(target, property, receiver) {
        const value = Reflect.get(target, property, receiver)
        if (typeof value !== 'function') return value
        return (...args) => {
          if (!sameViewer()) return Promise.reject(new StaleViewerError())
          const result = value.apply(target, args)
          if (!result || typeof result.then !== 'function') return result
          return result.then(
            (answer) => {
              assertSameViewer()
              return answer
            },
            (error) => {
              if (!isStaleViewerError(error)) assertSameViewer()
              throw error
            },
          )
        }
      },
    })
    proxies.set(client, proxy)
    return proxy
  }

  const guard = (effect) => (...args) => (alive() && typeof effect === 'function' ? effect(...args) : undefined)

  return {
    viewer,
    mount() { state.mounted = true },
    unmount() { state.mounted = false },
    sameViewer,
    alive,
    assertSameViewer,
    api,
    guard,
  }
}
