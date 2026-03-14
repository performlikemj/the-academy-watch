/**
 * Extract a YouTube video ID from various URL formats.
 * Handles: youtube.com/watch?v=X, youtu.be/X, youtube.com/embed/X, youtube.com/shorts/X
 * @param {string} url
 * @returns {string|null}
 */
export function extractYouTubeId(url) {
  if (!url || typeof url !== 'string') return null
  try {
    const u = new URL(url)
    const host = u.hostname.replace('www.', '')

    if (host === 'youtu.be') {
      const id = u.pathname.slice(1).split('/')[0]
      return id || null
    }

    if (host === 'youtube.com' || host === 'm.youtube.com') {
      // /watch?v=VIDEO_ID
      const v = u.searchParams.get('v')
      if (v) return v

      // /embed/VIDEO_ID or /shorts/VIDEO_ID
      const match = u.pathname.match(/^\/(embed|shorts)\/([^/?]+)/)
      if (match) return match[2]
    }
  } catch {
    // not a valid URL
  }
  return null
}

/**
 * Build a YouTube embed URL from a video ID.
 * @param {string} videoId
 * @returns {string}
 */
export function youTubeEmbedUrl(videoId) {
  return `https://www.youtube.com/embed/${videoId}`
}

/**
 * Check whether a URL is a recognised YouTube link.
 * @param {string} url
 * @returns {boolean}
 */
export function isYouTubeUrl(url) {
  return extractYouTubeId(url) !== null
}
