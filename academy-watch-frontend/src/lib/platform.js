// Capacitor native-shell detection + deep link handling for The Academy
// Watch's iOS app shell.
//
// Contract (see ios-migration-brief.md "Contract: src/lib/platform.js" —
// the shell agent's App.jsx codes against this even before this file
// existed):
//   export function isNativeApp(): boolean
//   export function useDeepLinks(): void
//
// `isNativeApp()` is also the gate the shell/engagement agents use to hide
// admin routes and the Buy-Me-a-Coffee / pricing surfaces inside the native
// app (Apple 3.1.1) — see docs/ios.md.
//
// Web-safety note: @capacitor/core is a real dependency now (installed for
// the iOS shell), so a static import here is safe and does not throw in a
// plain browser build — `Capacitor.isNativePlatform()` simply returns
// `false` outside the native shell. We still wrap it in try/catch per the
// brief so a future Capacitor upgrade or unexpected environment can never
// turn this into a white-screen crash on the web app.

import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Capacitor } from '@capacitor/core'

/**
 * True only when running inside the Capacitor native (iOS) shell. Always
 * false on the web — mobile web included — so nothing here ever hides
 * content from a mobile *browser* user, only from the native app binary.
 */
let _nativeApp = null

export function isNativeApp() {
    // The platform cannot change during a session — compute once and cache,
    // since App.jsx calls this on every route render.
    if (_nativeApp === null) {
        try {
            _nativeApp = Capacitor.isNativePlatform()
        } catch (err) {
            console.warn('[platform] Capacitor.isNativePlatform() check failed — assuming web', err)
            _nativeApp = false
        }
    }
    return _nativeApp
}

/**
 * Convert an incoming deep-link URL (universal link or custom URL scheme)
 * into an in-app router path.
 *
 *   https://theacademywatch.com/players/123?x=1  -> /players/123?x=1
 *   com.theacademywatch.app://players/123         -> /players/123
 *
 * Universal links (http/https) parse with the real path in `pathname`.
 * Custom-scheme links are non-"special" URLs per the WHATWG URL spec, so
 * the WHATWG parser puts the first path segment in `host` instead —
 * `com.theacademywatch.app://players/123` parses to host="players",
 * pathname="/123" — so we stitch host back onto the front of the path for
 * that case. Returns null if the URL can't be parsed at all.
 */
export function toInAppPath(url) {
    if (!url || typeof url !== 'string') return null
    let parsed
    try {
        parsed = new URL(url)
    } catch (err) {
        console.warn('[platform] Could not parse deep link URL', url, err)
        return null
    }
    const isWebScheme = parsed.protocol === 'http:' || parsed.protocol === 'https:'
    const path = isWebScheme
        ? parsed.pathname
        : `/${[parsed.host, parsed.pathname.replace(/^\/+/, '')].filter(Boolean).join('/')}`
    const rebuilt = `${path || '/'}${parsed.search}${parsed.hash}`
    return rebuilt || '/'
}

/**
 * React hook: on native, subscribes to @capacitor/app's `appUrlOpen` event
 * (fired for both universal links and the custom URL scheme) and navigates
 * the in-app router to the resolved path. No-op on web/mobile-web — nothing
 * to subscribe to, and `navigator`-driven navigation already works there.
 *
 * Mount once near the app root, inside the Router (it calls useNavigate).
 */
export function useDeepLinks() {
    const navigate = useNavigate()

    useEffect(() => {
        if (!isNativeApp()) return undefined

        let appUrlOpenHandle = null
        let backButtonHandle = null
        let cancelled = false

        ;(async () => {
            try {
                const { App } = await import('@capacitor/app')
                if (cancelled) return

                appUrlOpenHandle = await App.addListener('appUrlOpen', ({ url } = {}) => {
                    const path = toInAppPath(url)
                    if (path) navigate(path)
                })

                // iOS has no hardware back button (Android-only Capacitor
                // event) so this should never fire — guarded as a no-op
                // anyway so an unexpected emission never throws unhandled
                // and never fights the router's own back/forward handling.
                backButtonHandle = await App.addListener('backButton', () => {})
            } catch (err) {
                if (!cancelled) {
                    console.warn('[platform] Failed to attach native deep-link listeners', err)
                }
            }
        })()

        return () => {
            cancelled = true
            appUrlOpenHandle?.remove()
            backButtonHandle?.remove()
        }
    }, [navigate])
}
