import './highlights.css'

export function HighlightFeatureError({ enabled, status, retry, showUnknown = false }) {
  if (status !== 'failed' || (enabled !== true && !showUnknown)) return null
  return <div className="p2-highlights my-6">
    <p role="alert" className="hl-error">We could not check highlight availability. Please try again.</p>
    <button className="hl-button mt-3" onClick={retry}>Retry</button>
  </div>
}
