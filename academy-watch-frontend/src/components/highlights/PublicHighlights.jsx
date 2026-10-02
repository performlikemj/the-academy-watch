import { useEffect, useState } from 'react'
import { APIService } from '@/lib/api'
import { useHighlights } from './useHighlights'
import { HighlightFeatureError } from './HighlightFeatureError'
import './highlights.css'

function Clips({ path }) {
  const [rows, setRows] = useState([])
  useEffect(() => {
    const controller = new AbortController()
    APIService.request(path, { signal: controller.signal }, { nullOn404: true }).then(data => setRows(data?.highlights || [])).catch(() => setRows([]))
    return () => controller.abort()
  }, [path])
  if (!rows.length) return null
  return <section className="p2-highlights" aria-label="Approved highlights"><p className="hl-label">Picked by the club · approved by the player</p><h2 className="mt-3">Highlights</h2>{rows.map(row => <article key={row.id} className="hl-row"><h3>{row.title}</h3><p className="hl-muted mt-2 mb-4">{row.duration_s}s · {row.club_name}</p><video controls preload="none" src={APIService.highlightClipUrl(row.clip_url)} aria-label={row.title} /></article>)}</section>
}

export function PublicHighlights({ playerId, slug }) {
  const { enabled, status, retry } = useHighlights()
  const path = slug ? `/programs/${encodeURIComponent(slug)}/highlights` : `/players/${playerId}/highlights`
  return <><HighlightFeatureError status={status} retry={retry} />{enabled === true && <Clips key={path} path={path} />}</>
}
