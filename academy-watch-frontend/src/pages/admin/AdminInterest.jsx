import { formatDisplayDate } from '@/lib/display-date'
import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { APIService } from '@/lib/api'
import { interestLabel } from '@/lib/interest'

export function AdminInterest() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [exporting, setExporting] = useState(false)
  useEffect(() => {
    let cancelled = false
    APIService.adminInterest().then((result) => { if (!cancelled) setData(result) })
      .catch(() => { if (!cancelled) setError('Could not load sign-ups. Please refresh to try again.') })
    return () => { cancelled = true }
  }, [])

  const download = async () => {
    setExporting(true)
    setError('')
    try { await APIService.downloadInterestCsv() }
    catch { setError('Could not export sign-ups. Please try again.') }
    finally { setExporting(false) }
  }

  return (
    <section className="dark rounded-lg bg-night p-5 text-chalk sm:p-10">
      <div className="flex flex-wrap items-end justify-between gap-6 border-b border-border pb-8">
        <div>
          <p className="eyebrow mb-3">Control room · Early interest</p>
          <h2 className="display text-4xl sm:text-5xl">Who’s on the touchline.</h2>
          <p className="mt-4 text-sm text-muted-foreground">Interest only. No marketing emails have been sent.</p>
        </div>
        <Button variant="on-dark" onClick={download} disabled={!data || exporting}>
          {exporting ? 'Exporting…' : 'Export CSV'}
        </Button>
      </div>
      {error && <p role="alert" className="py-6">{error}</p>}
      {!data && !error && <p role="status" className="py-8 text-muted-foreground">Loading sign-ups…</p>}
      {data && <>
        <div className="rule-row flex items-baseline gap-4">
          <span className="display text-6xl">{data.total}</span><span className="eyebrow">Sign-ups</span>
        </div>
        <div className="grid gap-10 py-10 md:grid-cols-2">
          {['feature', 'role'].map((group) => <div key={group}>
            <h3 className="eyebrow">By {group}</h3>
            {Object.entries(data.counts[group]).map(([key, count]) => <div key={key} className="rule-row flex items-center justify-between gap-4">
              <span className="text-sm text-muted-foreground">{interestLabel(key)}</span><span className="font-mono text-sm">{count}</span>
            </div>)}
          </div>)}
        </div>
        <h3 className="display mb-5 text-3xl">Latest sign-ups</h3>
        {data.rows.length === 0 ? <p className="border-t border-border py-8 text-muted-foreground">No sign-ups yet. New interest will appear here.</p> :
          <Table>
            <TableHeader><TableRow>{['Email', 'Feature', 'Role', 'Source', 'Joined'].map((label) => <TableHead key={label}>{label}</TableHead>)}</TableRow></TableHeader>
            <TableBody>{data.rows.map((row) => <TableRow key={row.id}>
              <TableCell>{row.email}</TableCell><TableCell>{interestLabel(row.feature)}</TableCell>
              <TableCell>{row.role ? interestLabel(row.role) : '—'}</TableCell><TableCell>{row.source_path || '—'}</TableCell>
              <TableCell>{formatDisplayDate(row.created_at)}</TableCell>
            </TableRow>)}</TableBody>
          </Table>}
        <p className="mt-4 text-xs text-muted-foreground">Showing the newest {data.rows.length} sign-ups. CSV includes all rows.</p>
      </>}
    </section>
  )
}
