import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { APIService } from '@/lib/api'
import { FilterBar } from '@/components/filter/FilterBar'
import { CalmHeader, StatusWords, calmPanelClass, calmPillButton } from '@/components/admin/ControlRoom'
import { B3Gate, useDebouncedSearch, useControlData, LoadState, ReasonAction, Pagination, stamp } from '@/components/admin/B3Control'
import { useUrlFilters } from '@/hooks/useUrlFilters'
import { countLabel } from '@/lib/url-filters'
import { cn } from '@/lib/utils'

const DEFAULTS = { q: '', status: 'all', verified: '', country: '', offset: '0', club: '' }
const LIST_KEYS = ['q', 'status', 'verified', 'country', 'offset']
const STATUS = [['approved', 'Approved'], ['pending', 'Waiting for approval'], ['rejected', 'Rejected'], ['suspended', 'Suspended'], ['hidden', 'Emergency hidden']]
const STATUS_WORDS = Object.fromEntries(STATUS)
const options = pairs => pairs.map(([value, label]) => ({ value, label }))

function query(values, keys) {
    const params = new URLSearchParams()
    for (const key of keys) if (values[key] !== '' && values[key] != null) params.set(key, values[key])
    return params.toString()
}

function standing(row) {
    if (row.emergency_hidden) return ['warn', 'Emergency hidden']
    const words = STATUS_WORDS[row.platform_status] || row.platform_status
    return [row.platform_status === 'pending' ? 'gold' : row.platform_status === 'approved' ? 'quiet' : 'warn', words]
}

export function AdminPrograms() { return <B3Gate flag="admin_programs"><Programs /></B3Gate> }

function Programs() {
    const [values, setValues] = useUrlFilters(DEFAULTS)
    const [search, setSearch] = useState(values.q)
    const debounced = useDebouncedSearch(search)
    const written = useRef(values.q)
    useEffect(() => {
        if (debounced === written.current) return
        written.current = debounced
        setValues({ q: debounced, offset: '0' }, { replace: true })
    }, [debounced, setValues])
    useEffect(() => {
        if (values.q !== written.current) { written.current = values.q; setSearch(values.q) }
    }, [values.q])

    const offset = Number(values.offset) || 0
    const selected = Number(values.club) || null
    const list = useControlData(`/admin/programs?${query(values, LIST_KEYS)}`)
    const detail = useControlData(selected ? `/admin/programs/${selected}` : null)
    const program = detail.data?.program

    // Countries are counted by the server under the other filters in force (the whole list, not one page).
    const countryQuery = query(values, ['q', 'status', 'verified'])
    const loadCountries = useCallback(async text => {
        const data = await APIService.adminControlRead(`/admin/programs/countries?${countryQuery}`)
        const needle = text.toLowerCase()
        return data.countries.filter(row => row.value.toLowerCase().includes(needle)).map(row => ({ value: row.value, label: row.value, count: row.count }))
    }, [countryQuery])

    const filters = useMemo(() => [
        { key: 'status', label: 'Status', anyLabel: 'Any', defaultValue: 'all', options: options(STATUS) },
        { key: 'verified', label: 'Verified', anyLabel: 'Any', options: options([['yes', 'Verified'], ['no', 'Not verified yet']]) },
        { key: 'country', label: 'Country', anyLabel: 'Anywhere', searchable: true, searchPlaceholder: 'Type a country…', loadOptions: loadCountries, selectedLabel: values.country },
    ], [loadCountries, values.country])

    const [last, setLast] = useState(null)
    useEffect(() => { if (list.data) setLast(list.data) }, [list.data])
    const shown = list.data || last
    const rows = shown?.rows || []
    function reload() { list.reload(); detail.reload() }

    return (
        <div className="flex flex-col gap-5">
            <CalmHeader
                title="Clubs"
                actions={(
                    <label className="flex h-11 w-full items-center rounded-full border border-chalk/25 px-4 focus-within:border-chalk/60 sm:w-auto sm:min-w-[280px]">
                        <span className="sr-only">Search clubs</span>
                        <input type="search" maxLength={120} placeholder="Search clubs, towns, regions" value={search} onChange={event => setSearch(event.target.value)} className="w-full flex-1 border-0 bg-transparent text-sm text-chalk outline-none placeholder:text-muted-dark" />
                    </label>
                )}
            />
            <FilterBar
                label="Club filters"
                filters={filters}
                values={values}
                onChange={changes => setValues({ ...changes, offset: '0', club: '' })}
                count={shown ? countLabel(shown.total, 'club', 'clubs') : ''}
            />

            <div className="flex flex-wrap items-start gap-6">
                <section aria-label="Clubs" aria-busy={!list.data && !list.error} className={cn('min-w-0 flex-[3_1_480px] border-t border-chalk/[0.12]', selected && 'hidden xl:block')}>
                    {list.error ? <LoadState {...list} /> : !shown ? (
                        <div role="status" aria-label="Loading clubs" className="flex flex-col gap-2 pt-2">{[0, 1, 2, 3, 4].map(index => <div key={index} className="h-12 animate-pulse rounded-xl bg-chalk/[0.05]" />)}</div>
                    ) : (
                        <ul className={cn('m-0 list-none p-0 pt-2 transition-opacity', !list.data && 'opacity-60')}>
                            {rows.map(row => {
                                const [tone, words] = standing(row)
                                return (
                                    <li key={row.id}>
                                        <button
                                            type="button"
                                            aria-pressed={selected === row.id}
                                            onClick={() => setValues({ club: String(row.id) })}
                                            className={cn(
                                                'grid w-full grid-cols-1 gap-x-4 gap-y-1 rounded-xl px-3 py-3.5 text-left text-sm [overflow-wrap:anywhere] hover:bg-chalk/[0.04] focus-visible:outline-2 focus-visible:outline-gold sm:grid-cols-[minmax(0,2fr)_minmax(0,2fr)_minmax(0,1fr)]',
                                                selected === row.id && 'bg-chalk/[0.06]',
                                            )}
                                        >
                                            <span className="min-w-0 font-medium text-chalk">{row.name}</span>
                                            <span className="min-w-0 text-[#C9C5BA]">{[row.city, row.region, row.country].filter(Boolean).join(' · ')}</span>
                                            <StatusWords tone={tone}>{words}</StatusWords>
                                        </button>
                                    </li>
                                )
                            })}
                        </ul>
                    )}
                    {shown && rows.length === 0 && !list.error && <p className="px-3 py-8 text-sm text-muted-dark">No clubs match this search.</p>}
                    <Pagination data={shown} offset={offset} setOffset={value => setValues({ offset: String(value) })} />
                </section>

                {selected && (
                    <aside aria-label="Club details" className={cn(calmPanelClass, 'flex flex-[2_1_300px] flex-col gap-4')}>
                        <button type="button" className="self-start text-sm text-muted-dark underline xl:hidden" onClick={() => setValues({ club: '' })}>Back to clubs</button>
                        <LoadState data={detail.data} error={detail.error} />
                        {program && <ClubPanel key={program.id} program={program} managers={detail.data.managers} actions={detail.data.actions} onDone={reload} />}
                    </aside>
                )}
            </div>
        </div>
    )
}

function ClubPanel({ program, managers, actions, onDone }) {
    const [acting, setActing] = useState(null)
    const [owner, setOwner] = useState('')
    const [tone, words] = standing(program)
    const facts = [
        ['Standing', <StatusWords key="standing" tone={tone} className="text-chalk">{words}</StatusWords>],
        ['Where', [program.city, program.region, program.country].filter(Boolean).join(' · ') || '—'],
        ['Verified', program.verified_at ? stamp(program.verified_at) : 'Not yet'],
        ['People', `${program.players} players · ${program.managers} managers · ${program.matches} matches`],
        ...(program.claims_pending ? [['Waiting', `${program.claims_pending} claim${program.claims_pending === 1 ? '' : 's'} to review`]] : []),
        ['Source', program.origin === 'api' ? 'Football data provider' : 'Added on the platform'],
    ]
    const candidates = managers.filter(manager => manager.status === 'active' && manager.standing === 'active')
    return (
        <>
            <h2 className="m-0 text-xl font-semibold text-chalk [overflow-wrap:anywhere]">{program.name}</h2>
            <dl className="m-0 grid grid-cols-[max-content_minmax(0,1fr)] gap-x-4 gap-y-2 text-sm">
                {facts.map(([label, value]) => <div key={label} className="contents"><dt className="text-muted-dark">{label}</dt><dd className="m-0 min-w-0 text-chalk [overflow-wrap:anywhere]">{value}</dd></div>)}
            </dl>
            <details className="border-t border-chalk/10 pt-3 text-sm" open={managers.length > 0 && managers.length <= 4}>
                <summary className="cursor-pointer font-medium text-chalk">Managers <span className="font-normal text-muted-dark">· {managers.length}</span></summary>
                {managers.length === 0 && <p className="mt-2 text-muted-dark">No managers assigned.</p>}
                <ul className="m-0 mt-2 flex list-none flex-col gap-1.5 p-0">
                    {managers.map(manager => <li key={manager.user_account_id} className="flex flex-wrap justify-between gap-x-4 [overflow-wrap:anywhere]"><span className="min-w-0 text-chalk">{manager.display_name}</span><span className="text-muted-dark">{manager.owner ? 'Owner' : manager.status} · {manager.standing}</span></li>)}
                </ul>
            </details>
            <div className="flex flex-wrap gap-2.5 border-t border-chalk/10 pt-4">
                <Link to={`/admin/funding?tab=claims`} className={calmPillButton}>Claims and managers</Link>
                <details className="relative">
                    <summary aria-label="More actions" className={cn(calmPillButton, 'cursor-pointer list-none px-3.5 [&::-webkit-details-marker]:hidden')}>⋯</summary>
                    <div className="absolute left-0 z-10 mt-2 flex w-56 flex-col rounded-2xl border border-chalk/20 bg-ink p-2 text-sm">
                        <Link to={`/programs/${program.slug}`} className="rounded-[10px] px-3 py-2.5 text-chalk no-underline hover:bg-chalk/[0.06] hover:no-underline">View public page</Link>
                        {actions.owner && <button type="button" className="rounded-[10px] px-3 py-2.5 text-left text-chalk hover:bg-chalk/[0.06]" onClick={event => { setActing('owner'); event.currentTarget.closest('details').open = false }}>Assign owner…</button>}
                        <button type="button" disabled={!actions.emergency} className="rounded-[10px] px-3 py-2.5 text-left text-[#F0A592] hover:bg-chalk/[0.06] disabled:opacity-50" onClick={event => { setActing('hide'); event.currentTarget.closest('details').open = false }}>{program.emergency_hidden ? 'Lift emergency hide…' : 'Emergency hide…'}</button>
                        {!actions.emergency && <p className="px-3 py-2 text-[13px] text-muted-dark">Emergency actions are not enabled.</p>}
                    </div>
                </details>
            </div>
            {acting === 'owner' && (
                <div>
                    <label className="block text-sm">Assign owner
                        <select aria-label="Assign owner" className="mt-2 h-11 w-full rounded-full border border-hairline-dark bg-night px-4" value={owner} onChange={event => setOwner(event.target.value)}>
                            <option value="">Choose an active manager</option>
                            {candidates.map(manager => <option key={manager.user_account_id} value={manager.user_account_id}>{manager.display_name}</option>)}
                        </select>
                    </label>
                    <ReasonAction target={program.name} label="Assign owner" disabled={!owner} action={reason => APIService.adminControlAction(`/admin/programs/${program.id}/owner`, { user_account_id: Number(owner), reason })} onDone={() => { setActing(null); onDone() }} />
                    <button type="button" className="mt-3 text-sm text-muted-dark underline" onClick={() => setActing(null)}>Cancel</button>
                </div>
            )}
            {acting === 'hide' && (
                <div>
                    <ReasonAction target={program.name} label={program.emergency_hidden ? 'Lift emergency hide' : 'Emergency hide'} disabled={!actions.emergency} action={reason => APIService.adminControlAction(`/admin/programs/${program.id}/emergency-${program.emergency_hidden ? 'lift' : 'hide'}`, { reason })} onDone={() => { setActing(null); onDone() }} />
                    <p className="mt-3 text-[13px] leading-relaxed text-muted-dark">Emergency hide holds this club and its linked public player pages. Individual takedowns remain in place when the club hold is lifted.</p>
                    <button type="button" className="mt-3 text-sm text-muted-dark underline" onClick={() => setActing(null)}>Cancel</button>
                </div>
            )}
        </>
    )
}
