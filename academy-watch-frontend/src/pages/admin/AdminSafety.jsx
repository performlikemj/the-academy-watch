import { useState } from 'react'
import { Link } from 'react-router-dom'
import { APIService } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { AdminPageHeader, SectionTitle, BigStat } from '@/components/admin/ControlRoom'
import { B3Gate, useControlData, LoadState, DetailPanel, Fact, QuietEmpty, Pagination, rowClass, splitClass, metaClass, stamp } from '@/components/admin/B3Control'

export function AdminSafety() { return <B3Gate flag="admin_safety"><Safety /></B3Gate> }
function Safety() {
    const [offset, setOffset] = useState(0)
    const [selected, setSelected] = useState(null)
    const [all, setAll] = useState(false)
    const [reason, setReason] = useState('')
    const [error, setError] = useState('')
    const [busy, setBusy] = useState(false)
    const list = useControlData(`/admin/safety/cases?status=${all ? 'all' : 'open'}&offset=${offset}`)
    const detail = useControlData(selected ? `/admin/safety/cases/${selected}` : null)
    const inventory = useControlData('/admin/safety/hidden')
    const incident = detail.data?.case
    async function act(action) {
        setError(''); setBusy(true)
        try { await APIService.adminControlAction(`/admin/safety/cases/${incident.id}/actions`, { action, reason: reason.trim(), version: incident.version }); setReason(''); list.reload(); detail.reload(); inventory.reload() }
        catch (err) { setError(err.message || 'Could not save this action.') }
        finally { setBusy(false) }
    }
    return <div className="space-y-8"><AdminPageHeader eyebrow="Safeguarding" title="Keep the game" accent="safe" lede="Hide first, review the reported evidence, then record the decision." />
        <div className="grid gap-5 border-y border-hairline-dark py-6 sm:grid-cols-3"><BigStat label="Open cases" value={list.data?.open_count ?? '—'} /><BigStat label="First action overdue" value={list.data?.overdue_count ?? '—'} sub="First action due within 24 hours" subTone="warn" /><BigStat label="Active holds" value={list.data ? list.data.active_suppressions + list.data.hidden_programs : '—'} sub="Player suppressions and club holds" /></div>
        <div className={splitClass}><section className={selected ? 'hidden min-w-0 xl:block' : 'min-w-0'}><SectionTitle title="Cases" action={<Button variant="outline" size="sm" onClick={() => { setAll(!all); setOffset(0) }}>{all ? 'Open only' : 'Include closed'}</Button>} /><LoadState {...list} />{list.data?.rows.map(row => <button key={row.id} type="button" aria-pressed={selected === row.id} onClick={() => { setSelected(row.id); setReason(''); setError('') }} className={`${rowClass} ${selected === row.id ? 'bg-gold/[0.07]' : ''}`}><span className="flex flex-wrap items-center justify-between gap-2"><span className="break-words">Case {row.id} · {row.target_type.replaceAll('_', ' ')}</span><span className={metaClass}>{row.hidden ? 'Hidden · ' : ''}{row.status}</span></span><span className="mt-2 block text-sm text-muted-dark">{stamp(row.received_at)}{row.overdue ? ' · First action overdue' : ''}</span></button>)}{list.data?.rows.length === 0 && <QuietEmpty>No cases in this view.</QuietEmpty>}<Pagination data={list.data} offset={offset} setOffset={setOffset} /></section>
            <DetailPanel title="Safeguarding case details">{selected && <button type="button" className="mb-4 text-sm underline xl:hidden" onClick={() => setSelected(null)}>Back to cases</button>}{!selected && <QuietEmpty>Select a case to review its evidence.</QuietEmpty>}<LoadState data={selected ? detail.data : {}} error={detail.error} />{incident && <><p className={metaClass}>Case {incident.id} · {incident.target_type.replaceAll('_', ' ')}</p><h2 className="display mb-5 mt-3 text-3xl">{incident.hidden ? 'Hidden while we review' : 'Review the request'}</h2><p className="whitespace-pre-wrap break-words text-sm leading-relaxed">{detail.data.evidence.statement || 'No statement supplied.'}</p><Fact label="Target">{incident.target_id}</Fact><Fact label="First action due">{stamp(incident.first_action_due_at)}</Fact><Fact label="Status">{incident.status}</Fact><Fact label="Notification">{incident.notification_state.replaceAll('_', ' ')}</Fact>
                {incident.status !== 'closed' && <div className="mt-5 space-y-3"><label className="block text-sm">Reason for this case action<Input required maxLength={2000} value={reason} onChange={event => setReason(event.target.value)} className="mt-2" /></label><div className="flex flex-wrap gap-2">{[['hide', 'Hide now'], ['investigate', 'Investigate'], ['club_contact', 'Club contacted'], ['close', 'Close case']].map(([action, label]) => <Button key={action} variant={action === 'hide' ? 'destructive' : 'outline'} disabled={busy || !reason.trim()} onClick={() => act(action)}>{label}</Button>)}</div>{error && <p role="alert" className="text-sm">{error}</p>}</div>}
                <p className="mt-4 text-xs leading-relaxed text-muted-dark">Closing records the decision and queues a notification where an account recipient is available. Holds stay in place until separately reviewed and lifted.</p><Link to="/admin/programs" className="mt-3 block text-sm underline">Review club holds</Link><Link to="/admin/trust?tab=reports" className="mt-3 block text-sm underline">Open existing report moderation</Link><h3 className="mb-3 mt-6 text-sm">Case history</h3>{detail.data.events.map(event => <Fact key={event.id} label={event.action.replaceAll('_', ' ')}><span>{stamp(event.created_at)}<span className="mt-1 block max-w-64 break-words text-xs text-muted-dark">{event.reason}</span></span></Fact>)}</>}</DetailPanel>
        </div><section><SectionTitle title="Hidden inventory" /><LoadState {...inventory} />{inventory.data && <div className="grid gap-5 sm:grid-cols-2"><div>{inventory.data.programs.map(program => <Fact key={program.id} label="Club hold">{program.name}</Fact>)}{inventory.data.programs.length === 0 && <QuietEmpty>No active club holds.</QuietEmpty>}</div><div>{inventory.data.suppressions.map(row => <Fact key={row.id} label={`Suppression ${row.id}`}>{row.local_player_id ? `Local player ${row.local_player_id}` : `Player ${row.player_api_id}`}</Fact>)}{inventory.data.suppressions.length === 0 && <QuietEmpty>No active player suppressions.</QuietEmpty>}</div></div>}</section><p className="rounded-[10px] border border-gold/30 p-5 text-sm leading-relaxed text-muted-dark">New public publication uses the shared adults-only rule. A complete audit of legacy public scout records is not available here. Guardian applications remain coming soon.</p>
    </div>
}
