import { useEffect, useState } from 'react'
import { useAuth } from '@/context/AuthContext'
import { useViewerLifetime } from '@/hooks/useViewerState'
// Approved private photos require credentials; never put bearer tokens in URLs.
export function ShowcasePhoto({ src, previewUrl, alt, ...props }) {
  // Requests and side effects go through this viewer's lifetime (see lib/viewer-lifetime.js).
  const life = useViewerLifetime()
  const api = life.api
  const { token, hasApiKey } = useAuth()
  const [loaded, setLoaded] = useState(null)
  const key = `${previewUrl}:${token}:${hasApiKey}`
  useEffect(() => {
    if (src || !previewUrl || !token) return
    const controller = new AbortController()
    let objectUrl
    api.showcasePhotoBlob(previewUrl, controller.signal).then(blob => {
      if (controller.signal.aborted) return
      objectUrl = URL.createObjectURL(blob)
      setLoaded({ key, url: objectUrl })
    }).catch(() => {})
    return () => {
      controller.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [src, previewUrl, token, key, api])
  const imageUrl = src || (loaded?.key === key ? loaded.url : null)
  return imageUrl ? <img src={imageUrl} alt={alt} {...props} /> : <span role="img" aria-label={`${alt} — preview unavailable`} />
}
