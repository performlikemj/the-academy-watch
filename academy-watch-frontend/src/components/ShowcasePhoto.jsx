import { useEffect, useState } from 'react'
import { useAuth } from '@/context/AuthContext'
import { APIService } from '@/lib/api'

// Approved private photos require credentials; never put bearer tokens in URLs.
export function ShowcasePhoto({ src, previewUrl, alt, ...props }) {
  const { token, hasApiKey } = useAuth()
  const [loaded, setLoaded] = useState(null)
  const key = `${previewUrl}:${token}:${hasApiKey}`
  useEffect(() => {
    if (src || !previewUrl || !token) return
    const controller = new AbortController()
    let objectUrl
    APIService.showcasePhotoBlob(previewUrl, controller.signal).then(blob => {
      if (controller.signal.aborted) return
      objectUrl = URL.createObjectURL(blob)
      setLoaded({ key, url: objectUrl })
    }).catch(() => {})
    return () => {
      controller.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [src, previewUrl, token, key])
  const imageUrl = src || (loaded?.key === key ? loaded.url : null)
  return imageUrl ? <img src={imageUrl} alt={alt} {...props} /> : <span role="img" aria-label={`${alt} — preview unavailable`} />
}
