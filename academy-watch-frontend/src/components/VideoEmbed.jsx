import { extractYouTubeId, youTubeEmbedUrl } from '@/lib/youtube'
import { ExternalLink } from 'lucide-react'

/**
 * Responsive YouTube video embed.
 * Falls back to an external link for non-YouTube URLs.
 */
export function VideoEmbed({ url, title }) {
  const videoId = extractYouTubeId(url)

  if (!videoId) {
    return (
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="flex items-center gap-2 text-sm text-primary hover:underline"
      >
        <ExternalLink className="h-3.5 w-3.5 flex-shrink-0" />
        {title || url}
      </a>
    )
  }

  return (
    <div className="relative w-full overflow-hidden rounded-lg" style={{ paddingBottom: '56.25%' }}>
      <iframe
        src={youTubeEmbedUrl(videoId)}
        title={title || 'YouTube video'}
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
        sandbox="allow-scripts allow-same-origin allow-presentation allow-popups"
        allowFullScreen
        className="absolute inset-0 h-full w-full border-0"
      />
    </div>
  )
}

export default VideoEmbed
