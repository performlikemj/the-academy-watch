import { CLEAT_CSS, CLEAT_SVG } from '@/lib/cleat-loader'

export function CleatLoader({ className = '', surface, caption = true }) {
  return <>
    <style>{CLEAT_CSS}</style>
    <div className={`cleat-loader ${className}`} data-surface={surface} role="status" aria-live="polite" aria-label="Loading">
      <span dangerouslySetInnerHTML={{ __html: CLEAT_SVG }} />
      {caption && <span className="cleat-caption" aria-hidden="true">LOADING</span>}
    </div>
  </>
}
