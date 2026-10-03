import { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { APIService } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { formatDisplayDate } from '@/lib/display-date'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'

export function useControlFlags() {
    const [flags, setFlags] = useState(null)
    useEffect(() => {
        let live = true
        APIService.getFeatures().then(value => { if (live) setFlags(value) }).catch(() => { if (live) setFlags({}) })
        return () => { live = false }
    }, [])
    return flags
}

export function B3Gate({ flag, children }) {
    const flags = useControlFlags()
    if (!flags) return <p role="status" className="text-muted-dark">Loading control room…</p>
    if (!flags[flag]) return <div className="space-y-4"><h1 className="display text-4xl">Page unavailable</h1><p className="text-muted-dark">This control-room page has not been enabled.</p><Link to="/admin/dashboard" className="underline">Back to Today</Link></div>
    return children
}

export function useControlTab(flag, choices, fallback) {
    const flags = useControlFlags()
    const [params, setParams] = useSearchParams()
    const [localTab, setLocalTab] = useState(fallback)
    const requested = params.get('tab')
    const tab = flags?.[flag] && choices.includes(requested) ? requested : localTab
    const select = value => {
        setLocalTab(value)
        if (flags?.[flag]) setParams(current => {
            const next = new URLSearchParams(current)
            next.set('tab', value)
            return next
        }, { replace: true })
    }
    return [tab, select]
}

export function useControlData(path) {
    const [result, setResult] = useState({})
    const [revision, setRevision] = useState(0)
    const reload = useCallback(() => setRevision(value => value + 1), [])
    useEffect(() => {
        if (!path) return
        let live = true
        APIService.adminControlRead(path).then(data => {
            if (live) setResult({ path, revision, data, error: '' })
        }).catch(err => {
            if (live) setResult({ path, revision, data: null, error: err.message || 'Could not load this view.' })
        })
        return () => { live = false }
    }, [path, revision])
    const current = result.path === path && result.revision === revision
    return { data: current ? result.data : null, error: current ? result.error : '', reload }
}

export function LoadState({ error, data }) {
    if (error) return <p role="alert" className="rounded-[10px] border border-danger p-4">{error}</p>
    if (!data) return <p role="status" className="text-muted-dark">Loading…</p>
    return null
}

export function DetailPanel({ children, title }) {
    return <aside aria-label={title} className="min-w-0 self-start rounded-[10px] border border-hairline-dark bg-chalk/[0.04] p-5 sm:p-7">{children}</aside>
}

export function Fact({ label, children }) {
    return <div className="flex flex-wrap justify-between gap-x-5 gap-y-1 border-t border-hairline-dark py-3 text-sm"><span className="text-muted-dark">{label}</span><span className="min-w-0 max-w-full [overflow-wrap:anywhere] text-right">{children ?? '—'}</span></div>
}

export function QuietEmpty({ children }) {
    return <p className="border-b border-hairline-dark py-8 text-sm text-muted-dark">{children}</p>
}

export const rowClass = 'w-full min-w-0 [overflow-wrap:anywhere] border-b border-hairline-dark px-2 py-4 text-left hover:bg-chalk/[0.04] focus-visible:outline-2 focus-visible:outline-gold'
export const splitClass = 'grid min-w-0 gap-8 xl:grid-cols-[minmax(0,1fr)_360px]'
export const metaClass = 'font-mono text-[11px] uppercase tracking-[.14em] text-muted-dark'
// UK dates, as everywhere else in admin (lib/display-date).
export const stamp = value => formatDisplayDate(value, { withTime: true, fallback: 'Never' })

export function ReasonAction({ label, action, onDone, disabled = false, target, warning }) {
    const [reason, setReason] = useState('')
    const [error, setError] = useState('')
    const [busy, setBusy] = useState(false)
    const [confirming, setConfirming] = useState(false)
    async function submit() {
        if (!reason.trim()) return
        setBusy(true)
        setError('')
        try { await action(reason.trim()); setReason(''); onDone?.() }
        catch (err) { setError(err.message || 'Action failed. Try again.') }
        finally { setBusy(false); setConfirming(false) }
    }
    return <form onSubmit={event => { event.preventDefault(); setConfirming(true) }} className="mt-5 space-y-3">
        <label className="block text-sm">Reason for {label.toLowerCase()}<Input value={reason} onChange={event => setReason(event.target.value)} required maxLength={2000} disabled={disabled || busy} className="mt-2" /></label>
        <Button type="submit" variant="outline" disabled={disabled || busy || !reason.trim()} className="w-full">{busy ? 'Saving…' : label}</Button>
        {error && <p role="alert" className="text-sm text-chalk">{error}</p>}
        <ConfirmAction open={confirming} onCancel={() => setConfirming(false)} onConfirm={submit} label={label} target={target} reason={reason} warning={warning} busy={busy} />
    </form>
}

export function Pagination({ data, offset, setOffset }) {
    if (!data || (offset === 0 && data.total <= data.limit)) return null
    return <div className="mt-5 flex flex-wrap items-center gap-3"><Button variant="outline" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - data.limit))}>Previous</Button><span className="text-sm text-muted-dark">{offset >= data.total ? `0 on this page · ${data.total} total` : `${offset + 1}–${Math.min(offset + data.limit, data.total)} of ${data.total}`}</span><Button variant="outline" disabled={offset + data.limit >= data.total} onClick={() => setOffset(offset + data.limit)}>Next</Button></div>
}


export function ConfirmAction({ open, onCancel, onConfirm, label, target, reason, warning, busy }) {
    return <Dialog open={open} onOpenChange={value => { if (!value && !busy) onCancel() }}><DialogContent><DialogHeader><DialogTitle>Confirm {label?.toLowerCase()}</DialogTitle><DialogDescription>{label} for {target}. Reason: {reason}</DialogDescription></DialogHeader>{warning && <p role="alert" className="text-sm">{warning}</p>}<DialogFooter><Button variant="outline" disabled={busy} onClick={onCancel}>Cancel</Button><Button disabled={busy} onClick={onConfirm}>Confirm {label?.toLowerCase()}</Button></DialogFooter></DialogContent></Dialog>
}

export function useDebouncedSearch(value) {
    const [search, setSearch] = useState(value)
    useEffect(() => { const timer = setTimeout(() => setSearch(value), 300); return () => clearTimeout(timer) }, [value])
    return search
}
