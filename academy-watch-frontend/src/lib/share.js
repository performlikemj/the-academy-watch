// Social share helpers for player profiles — used by ShareMenu and statCard.
//
// getPlayerShareUrl mirrors the API base resolution in src/lib/api.js
// (VITE_API_BASE) without importing that file (it is owned by another
// builder). In prod (absolute VITE_API_BASE) it points at the backend's
// OG-unfurl endpoint (GET /players/<id>/share) so socials get real meta
// tags; in dev (relative /api, no env var) it falls back to the SPA route
// directly since there is no separate unfurl host to hit.
//
// nativeShare()/canNativeShare() below are also owned by this file per the
// iOS migration file-ownership split — platform.js (same owner) is imported
// just for the native-shell check so the two files never drift on what
// "native" means.

import { isNativeApp } from './platform.js'

const RAW_API_BASE =
    (typeof import.meta !== 'undefined' && import.meta.env && import.meta.env.VITE_API_BASE) || '/api'

function isAbsoluteHttpUrl(value) {
    return typeof value === 'string' && /^https?:\/\//i.test(value)
}

export function getPlayerShareUrl(playerId) {
    if (isAbsoluteHttpUrl(RAW_API_BASE)) {
        const base = RAW_API_BASE.replace(/\/+$/, '')
        return `${base}/players/${playerId}/share`
    }
    const origin = (typeof window !== 'undefined' && window.location && window.location.origin) || ''
    return `${origin}/players/${playerId}`
}

export function getShareText(playerName) {
    const name = (playerName || '').trim() || 'This player'
    return `${name} — follow their journey on The Academy Watch`
}

/**
 * Copy a share URL to the clipboard. Returns true on success, false if every
 * copy strategy failed (never throws — callers just skip the "Copied" state).
 */
export async function copyShareLink({ url } = {}) {
    if (!url) return false
    try {
        if (typeof navigator !== 'undefined' && navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(url)
            return true
        }
    } catch (err) {
        console.warn('Clipboard write failed, falling back to legacy copy', err)
    }
    try {
        if (typeof document === 'undefined') return false
        const textarea = document.createElement('textarea')
        textarea.value = url
        textarea.setAttribute('readonly', '')
        textarea.style.position = 'fixed'
        textarea.style.top = '-1000px'
        textarea.style.opacity = '0'
        document.body.appendChild(textarea)
        textarea.focus()
        textarea.select()
        const ok = document.execCommand('copy')
        document.body.removeChild(textarea)
        return ok
    } catch (err) {
        console.warn('Legacy clipboard copy failed', err)
        return false
    }
}

function openShareWindow(intentUrl) {
    if (typeof window === 'undefined') return
    window.open(intentUrl, '_blank', 'noopener,noreferrer,width=600,height=520')
}

export function shareToX({ url, playerName, text } = {}) {
    const shareText = text || getShareText(playerName)
    const params = new URLSearchParams({ text: shareText, url: url || '' })
    openShareWindow(`https://twitter.com/intent/tweet?${params.toString()}`)
}

export function shareToWhatsApp({ url, playerName, text } = {}) {
    const shareText = text || getShareText(playerName)
    const params = new URLSearchParams({ text: `${shareText} ${url || ''}`.trim() })
    openShareWindow(`https://wa.me/?${params.toString()}`)
}

export function shareToFacebook({ url } = {}) {
    const params = new URLSearchParams({ u: url || '' })
    openShareWindow(`https://www.facebook.com/sharer/sharer.php?${params.toString()}`)
}

/**
 * True if some native/OS share affordance is available: the Capacitor
 * share sheet inside the native iOS shell, or the browser's Web Share API
 * on web (mobile Safari/Chrome; most desktop browsers lack it, which is
 * why ShareMenu also renders the per-network buttons above as a fallback).
 */
export function canNativeShare() {
    if (isNativeApp()) return true
    return typeof navigator !== 'undefined' && typeof navigator.share === 'function'
}

/**
 * Show the OS share sheet. Returns true if it was shown (the user may still
 * cancel it), false if unsupported or it failed. Inside the Capacitor native
 * shell this uses @capacitor/share (WKWebView does not implement
 * navigator.share); on web it falls back to the Web Share API. The
 * @capacitor/share import is dynamic so plain web bundles never pay for the
 * plugin code.
 */
export async function nativeShare({ url, playerName, text } = {}) {
    const shareText = text || getShareText(playerName)
    const title = playerName || 'The Academy Watch'

    if (isNativeApp()) {
        try {
            const { Share } = await import('@capacitor/share')
            await Share.share({ title, text: shareText, url })
            return true
        } catch (err) {
            // Capacitor's Share plugin throws when the user dismisses the
            // native share sheet — treat that the same as navigator.share's
            // AbortError and just report "not shared" rather than warning.
            if (err && (err.message === 'Share canceled' || err.name === 'AbortError')) return false
            console.warn('Native share failed', err)
            return false
        }
    }

    if (!canNativeShare()) return false
    try {
        await navigator.share({ title, text: shareText, url })
        return true
    } catch (err) {
        if (err && err.name === 'AbortError') return false
        console.warn('Native share failed', err)
        return false
    }
}
