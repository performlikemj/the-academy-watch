import { useState } from 'react'
import { APIService } from '@/lib/api'
import { useHighlights } from './useHighlights'

export function AdminHighlightTakedown() {
  const enabled = useHighlights()
  const [id, setId] = useState('')
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState('')
  if (!enabled) return null
  async function remove(event) {
    event.preventDefault()
    setBusy(true); setStatus('')
    try {
      await APIService.adminControlAction(`/admin/highlights/${id.trim()}/takedown`, {})
      setStatus('Clip taken down. New clip grants are blocked; existing links expire within 60 seconds.')
    } catch { setStatus('Clip could not be taken down. Check the clip ID and your admin access, then try again.') }
    finally { setBusy(false) }
  }
  return <section className="border-y border-hairline-dark py-6">
    <h2 className="display text-2xl">Take down one highlight</h2>
    <p className="text-sm text-muted-dark mt-3">Withdraw this clip without hiding the player or club. This works even after the original recording has expired.</p>
    <form onSubmit={remove} className="flex flex-wrap items-end gap-3 mt-5">
      <label className="text-sm flex-1 min-w-0">Highlight ID<input className="mt-2 block w-full rounded-full bg-night border border-hairline-dark px-4 h-11" value={id} maxLength={36} onChange={event => setId(event.target.value)} /></label>
      <button type="submit" className="min-h-11 px-5 rounded-full border border-danger text-chalk" disabled={busy || !/^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/.test(id.trim())}>{busy ? 'Taking down…' : 'Take down clip'}</button>
    </form>
    {status && <p role="status" className="text-sm mt-4">{status}</p>}
  </section>
}
