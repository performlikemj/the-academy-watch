import { useLayoutEffect, useRef, useState } from 'react'
import { CLEAT_MARK, detectSurface } from '@/lib/cleat-loader'

// Styles and artwork come from index.html's boot splash stylesheet (outside #root, so it
// stays for the page's lifetime); the bundle carries no copy of the logo.
export function CleatLoader({ className = '', surface, caption = true }) {
  const ref = useRef(null)
  const [detected, setDetected] = useState()
  useLayoutEffect(() => { if (!surface) setDetected(detectSurface(ref.current)) }, [surface])
  return (
    <div ref={ref} className={`cleat-loader ${className}`} data-surface={surface || detected} role="status" aria-live="polite" aria-label="Loading">
      <span dangerouslySetInnerHTML={{ __html: CLEAT_MARK }} />
      {caption && <span className="cleat-caption" aria-hidden="true">LOADING</span>}
    </div>
  )
}
