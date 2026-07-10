// Social share helpers for player profiles — used by ShareMenu and statCard.
//
// getPlayerShareUrl mirrors the API base resolution in src/lib/api.js
// (VITE_API_BASE) without importing that file (it is owned by another
// builder). In prod (absolute VITE_API_BASE) it points at the backend's
// OG-unfurl endpoint (GET /players/<id>/share) so socials get real meta
// tags; in dev (relative /api, no env var) it falls back to the SPA route
// directly since there is no separate unfurl host to hit.

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

export function canNativeShare() {
    return typeof navigator !== 'undefined' && typeof navigator.share === 'function'
}

/**
 * Web Share API with feature detection. Returns true if the share sheet was
 * shown (the user may still cancel it), false if unsupported or it failed.
 */
export async function nativeShare({ url, playerName, text } = {}) {
    if (!canNativeShare()) return false
    const shareText = text || getShareText(playerName)
    try {
        await navigator.share({ title: playerName || 'The Academy Watch', text: shareText, url })
        return true
    } catch (err) {
        if (err && err.name === 'AbortError') return false
        console.warn('Native share failed', err)
        return false
    }
}
