import { useState } from 'react'
import { Link } from 'react-router-dom'
import { APIService } from '@/lib/api'
import { Input } from '@/components/ui/input'
import { AdminPageHeader, SectionTitle } from '@/components/admin/ControlRoom'
import { B3Gate, useControlData, LoadState, DetailPanel, Fact, QuietEmpty, ReasonAction, Pagination, rowClass, splitClass, metaClass, stamp } from '@/components/admin/B3Control'

export function AdminPrograms() { return <B3Gate flag="admin_programs"><Programs /></B3Gate> }
function Programs() {
    const [search, setSearch] = useState('')
    const [offset, setOffset] = useState(0)
    const [selected, setSelected] = useState(null)
    const [owner, setOwner] = useState('')
    const list = useControlData(`/admin/programs?q=${encodeURIComponent(search)}&offset=${offset}`)
    const detail = useControlData(selected ? `/admin/programs/${selected}` : null)
    const program = detail.data?.program
    function reload() { list.reload(); detail.reload() }
    return <div className="space-y-8">
        <AdminPageHeader eyebrow={`Clubs${list.data ? ` · ${list.data.total}` : ''}`} title="Every club," accent="one list" lede="Programs, claim standing and the people responsible for them." actions={<label className="w-full sm:w-72"><span className="sr-only">Search clubs</span><Input placeholder="Search clubs, towns, regions" value={search} onChange={event => { setSearch(event.target.value); setOffset(0) }} /></label>} />
        <div className={splitClass}><section className={selected ? 'hidden min-w-0 xl:block' : 'min-w-0'}><SectionTitle title="Programs" /><LoadState {...list} />
            {list.data?.rows.map(row => <button key={row.id} type="button" aria-pressed={selected === row.id} onClick={() => { setSelected(row.id); setOwner('') }} className={`${rowClass} ${selected === row.id ? 'bg-gold/[0.07]' : ''}`}><span className="flex flex-wrap items-center justify-between gap-3"><span className="min-w-0 break-words text-base">{row.name}<span className="mt-1 block text-sm text-muted-dark">{[row.city, row.region, row.country].filter(Boolean).join(' · ')}</span></span><span className={metaClass}>{row.emergency_hidden ? 'Hidden' : row.platform_status}</span></span><span className="mt-3 flex flex-wrap gap-5 text-sm text-muted-dark">{row.players} players · {row.managers} managers · {row.matches} matches</span></button>)}
            {list.data?.rows.length === 0 && <QuietEmpty>No programs match this search.</QuietEmpty>}<Pagination data={list.data} offset={offset} setOffset={setOffset} />
        </section><DetailPanel title="Program details">{selected && <button type="button" className="mb-4 text-sm underline xl:hidden" onClick={() => setSelected(null)}>Back to programs</button>}
            {!selected && <QuietEmpty>Select a program to review its standing.</QuietEmpty>}<LoadState data={selected ? detail.data : {}} error={detail.error} />
            {program && <><h2 className="display break-words text-3xl">{program.name}</h2><p className={`${metaClass} my-4`}>{program.emergency_hidden ? 'Emergency hidden' : program.platform_status}</p><Fact label="Origin">{program.origin}</Fact><Fact label="Verified">{stamp(program.verified_at)}</Fact><Fact label="Pending claims">{program.claims_pending}</Fact>
                <Link to={`/programs/${program.slug}`} className="my-4 block text-sm underline">View public page</Link><Link to="/admin/funding" className="block text-sm underline">Review claims and managers</Link>
                <h3 className="mb-3 mt-6 text-sm">Managers</h3>{detail.data.managers.length === 0 && <p className="text-sm text-muted-dark">No managers assigned.</p>}
                {detail.data.managers.map(manager => <Fact key={manager.user_account_id} label={manager.display_name}><span>{manager.owner ? 'Owner' : manager.status} · {manager.standing}</span></Fact>)}
                {detail.data.actions.owner && <><label className="mt-5 block text-sm">Assign owner<select aria-label="Assign owner" className="mt-2 h-11 w-full rounded-full border border-hairline-dark bg-night px-4" value={owner} onChange={event => setOwner(event.target.value)}><option value="">Choose an active manager</option>{detail.data.managers.filter(manager => manager.status === 'active' && manager.standing === 'active').map(manager => <option key={manager.user_account_id} value={manager.user_account_id}>{manager.display_name}</option>)}</select></label><ReasonAction label="Assign owner" disabled={!owner} action={reason => APIService.adminControlAction(`/admin/programs/${program.id}/owner`, { user_account_id: Number(owner), reason })} onDone={reload} /></>}
                <ReasonAction key={`hide-${program.id}`} label={program.emergency_hidden ? 'Lift emergency hide' : 'Emergency hide'} disabled={!detail.data.actions.emergency} action={reason => APIService.adminControlAction(`/admin/programs/${program.id}/emergency-${program.emergency_hidden ? 'lift' : 'hide'}`, { reason })} onDone={reload} />
                <p className="mt-3 text-xs leading-relaxed text-muted-dark">Emergency hide holds this club and its linked public player pages. Individual takedowns remain in place when the club hold is lifted.</p>
                {!detail.data.actions.emergency && <p className="mt-2 text-xs text-muted-dark">Emergency actions are not enabled.</p>}
            </>}
        </DetailPanel></div>
    </div>
}
