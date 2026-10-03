import { useLayoutEffect, useRef, useState } from 'react'
import { CLEAT_CSS, CLEAT_MARK, detectSurface } from '@/lib/cleat-loader'

export function CleatLoader({ className = '', surface, caption = true }) {
  const ref = useRef(null)
  const [detected, setDetected] = useState()
  useLayoutEffect(() => { if (!surface) setDetected(detectSurface(ref.current)) }, [surface])
  return <>
    {/* React hoists and de-duplicates this by href, so several loaders share one sheet. */}
    <style href="academy-watch-cleat-loader" precedence="default">{CLEAT_CSS}</style>
    <div ref={ref} className={`cleat-loader ${className}`} data-surface={surface || detected} role="status" aria-live="polite" aria-label="Loading">
      <span dangerouslySetInnerHTML={{ __html: CLEAT_MARK }} />
      {caption && <span className="cleat-caption" aria-hidden="true">LOADING</span>}
    </div>
  </>
}
