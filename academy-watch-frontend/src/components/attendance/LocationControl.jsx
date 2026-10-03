import { useState } from 'react'

const runImmediately = callback => callback()

export function LocationControl({ location, setLocation, radius, setRadius, dark = false, run = runImmediately }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  function locate() {
    setError('')
    if (!navigator.geolocation) { setError('Location is unavailable. Browse without distances.'); return }
    setBusy(true)
    run(() => navigator.geolocation.getCurrentPosition(({ coords }) => run(() => {
      setLocation({ lat: coords.latitude, lng: coords.longitude })
      setBusy(false)
    }), () => run(() => { setBusy(false); setError('Location is off or unavailable. Browse without distances.') }), { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 }))
  }
  return <div className={`c4-location ${dark ? 'c4-night' : ''}`}>
    {location ? <><span>Using my location</span><label>Distance<select aria-label="Distance" value={radius} onChange={e => setRadius(Number(e.target.value))}><option value="25">Within 25 km</option><option value="50">Within 50 km</option><option value="100">Within 100 km</option><option value="250">Within 250 km</option></select></label><button type="button" onClick={() => { setLocation(null); setError('') }}>Turn location off</button></> : <button type="button" disabled={busy} onClick={locate}>{busy ? 'Finding your location…' : 'Use my location'}</button>}
    <p className="c4-meta" role={error ? 'status' : undefined}>{error || (location ? 'Distances use the club’s approved venue pin.' : 'Location is off, so distances are unavailable.')}</p>
  </div>
}
