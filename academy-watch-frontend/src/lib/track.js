// Self-contained first-party product analytics client.
// Design constraints (frozen contract):
//   - No cookies, no external SDK. Uses raw fetch / sendBeacon only.
//   - Analytics must NEVER break the app: every path fails silently.
//   - Respects a localStorage opt-out flag ("aw_analytics_optout").
//   - Only these event names are emitted by callers; the server also
//     re-validates against its allowlist.

const ENDPOINT = (typeof import.meta !== 'undefined' && import.meta.env && import.meta.env.VITE_API_BASE
    ? import.meta.env.VITE_API_BASE
    : '/api') + '/events'

const SESSION_KEY = 'aw_analytics_session'
const OPTOUT_KEY = 'aw_analytics_optout'
const FLUSH_AT = 10        // flush when the queue reaches this many events
const FLUSH_INTERVAL = 5000 // ms — periodic flush timer

// Query params that can carry a secret / login-granting capability from
// email links (/verify, /unsubscribe, /manage, /claim-account all use ?token=).
// These must never be persisted to the analytics store, so they are stripped
// from both the pageview `path` and the `referrer` before an event is queued.
const SENSITIVE_PARAMS = [
    'token', 'code', 'key', 'secret', 'auth', 'access_token',
    'refresh_token', 'jwt', 'password', 'pwd', 'session',
]

let queue = []
let timer = null

function isBrowser() {
    return typeof window !== 'undefined'
}

// Remove sensitive query params from a path or full URL. On any parse failure
// the whole query string is dropped, which fails safe (never leaks a token).
function sanitizeUrl(url) {
    if (!url) return url
    const qIndex = url.indexOf('?')
    if (qIndex === -1) return url
    const base = url.slice(0, qIndex)
    const query = url.slice(qIndex + 1)
    try {
        const params = new URLSearchParams(query)
        let changed = false
        for (const name of SENSITIVE_PARAMS) {
            while (params.has(name)) {
                params.delete(name)
                changed = true
            }
        }
        if (!changed) return url
        const rest = params.toString()
        return rest ? `${base}?${rest}` : base
    } catch {
        // Malformed query — drop it entirely rather than risk leaking a secret.
        return base
    }
}

function currentPath() {
    try {
        return (window.location && (window.location.pathname + window.location.search)) || null
    } catch {
        return null
    }
}

function isOptedOut() {
    try {
        return isBrowser() && window.localStorage.getItem(OPTOUT_KEY) === '1'
    } catch {
        return false
    }
}

function getSessionId() {
    try {
        let id = window.sessionStorage.getItem(SESSION_KEY)
        if (!id) {
            id = (window.crypto && typeof window.crypto.randomUUID === 'function')
                ? window.crypto.randomUUID()
                : `s-${Date.now()}-${Math.random().toString(16).slice(2)}`
            window.sessionStorage.setItem(SESSION_KEY, id)
        }
        return id
    } catch {
        return null
    }
}

function currentReferrer() {
    try {
        return sanitizeUrl(document.referrer || null)
    } catch {
        return null
    }
}

function scheduleFlush() {
    if (timer !== null) return
    try {
        timer = setTimeout(() => {
            timer = null
            flush()
        }, FLUSH_INTERVAL)
    } catch {
        timer = null
    }
}

// Send whatever is queued. `useBeacon` picks sendBeacon (for unload paths);
// otherwise a keepalive fetch is used so an in-flight POST survives navigation.
function flush(useBeacon = false) {
    if (queue.length === 0) return
    if (timer !== null) {
        try { clearTimeout(timer) } catch { /* noop */ }
        timer = null
    }

    const batch = queue
    queue = []
    const payload = { events: batch }

    try {
        if (useBeacon && isBrowser() && navigator && typeof navigator.sendBeacon === 'function') {
            // Use a CORS-safelisted content type (text/plain) so the cross-origin
            // unload beacon is NOT held back by a preflight — an OPTIONS+POST is
            // unreliable during pagehide/visibilitychange and would silently drop
            // exit events. Flask still parses the JSON body via get_json(force=True).
            const blob = new Blob([JSON.stringify(payload)], { type: 'text/plain' })
            navigator.sendBeacon(ENDPOINT, blob)
            return
        }
        fetch(ENDPOINT, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
            keepalive: true,
        }).catch(() => { /* silent */ })
    } catch {
        // Never let analytics throw into the app.
    }
}

function enqueue(name, props) {
    if (!name || isOptedOut() || !isBrowser()) return
    try {
        const event = {
            name,
            path: sanitizeUrl(currentPath()),
            referrer: currentReferrer(),
            session_id: getSessionId(),
        }
        if (props && typeof props === 'object') event.props = props
        queue.push(event)
        if (queue.length >= FLUSH_AT) {
            flush()
        } else {
            scheduleFlush()
        }
    } catch {
        // Never let analytics throw into the app.
    }
}

export function track(name, props) {
    enqueue(name, props)
}

export function trackPageview(path) {
    if (isOptedOut() || !isBrowser()) return
    try {
        const event = {
            name: 'pageview',
            path: sanitizeUrl(path || currentPath()),
            referrer: currentReferrer(),
            session_id: getSessionId(),
        }
        queue.push(event)
        if (queue.length >= FLUSH_AT) {
            flush()
        } else {
            scheduleFlush()
        }
    } catch {
        // Never let analytics throw into the app.
    }
}

// Flush on tab hide / unload via sendBeacon so queued events aren't lost.
if (isBrowser()) {
    try {
        window.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'hidden') flush(true)
        })
        window.addEventListener('pagehide', () => flush(true))
    } catch {
        // Environment without these events — ignore.
    }
}
