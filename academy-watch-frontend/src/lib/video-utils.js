/** Helpers for the video-analysis admin pages. */

/** Accept "47:30", "1:02:15" or plain seconds; return seconds, null for empty,
 * undefined for unparseable. */
export function parseTimeInput(value) {
    const text = String(value ?? '').trim()
    if (!text) return null
    if (/^\d+(\.\d+)?$/.test(text)) return Number(text)
    const parts = text.split(':').map((p) => p.trim())
    if (parts.length < 2 || parts.length > 3 || parts.some((p) => !/^\d+$/.test(p))) return undefined
    return parts.reduce((acc, p) => acc * 60 + Number(p), 0)
}

export function formatSeconds(s) {
    if (s === null || s === undefined) return ''
    const total = Math.round(s)
    const h = Math.floor(total / 3600)
    const m = Math.floor((total % 3600) / 60)
    const sec = total % 60
    const mm = String(m).padStart(h ? 2 : 1, '0')
    const ss = String(sec).padStart(2, '0')
    return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`
}

/** Parse pasted roster lines like "10 John Smith" / "10, John Smith". */
export function parseRosterText(text) {
    const entries = []
    for (const line of String(text || '').split('\n')) {
        const m = line.trim().match(/^(\d{1,2})[\s,.-]+(.+)$/)
        if (m) entries.push({ jersey_number: Number(m[1]), player_name: m[2].trim() })
    }
    return entries
}
