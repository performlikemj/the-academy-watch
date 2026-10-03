import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { APIService } from '@/lib/api'
import { FilterBar } from '@/components/filter/FilterBar'
import { CalmHeader, StatusWords, calmPanelClass, calmPillButton, calmWarnButton } from '@/components/admin/ControlRoom'
import { B3Gate, useDebouncedSearch, useControlData, LoadState, ReasonAction, Pagination, stamp } from '@/components/admin/B3Control'
import { useUrlFilters } from '@/hooks/useUrlFilters'
import { countLabel } from '@/lib/url-filters'
import { cn } from '@/lib/utils'

// Everything the list is asked for lives in the address bar; these are the "not set" values.
const DEFAULTS = { q: '', club: '', role: 'all', standing: 'all', verified: '', joined: '', seen: '', sort: 'name', offset: '0', person: '' }
const LIST_KEYS = ['q', 'club', 'role', 'standing', 'verified', 'joined', 'seen', 'sort', 'offset']
const TYPE = [['players', 'Players'], ['clubs', 'Club staff'], ['scouts', 'Scouts'], ['admins', 'Admins']]
const STATUS = [['active', 'Active'], ['waiting', 'Waiting for approval'], ['suspended', 'Suspended']]
const SORT = [['name', 'Name A–Z'], ['name_desc', 'Name Z–A'], ['newest', 'Newest first'], ['standing', 'Standing, then name']]
const options = pairs => pairs.map(([value, label]) => ({ value, label }))
const ROLE_WORDS = { club_manager: 'Club manager', club_owner: 'Club owner', club_coach: 'Coach', club_analyst: 'Analyst', club_viewer: 'Club viewer', verified_scout: 'Verified scout', scout_pending: 'Scout, waiting for approval', scout_rejected: 'Scout, not approved', scout_revoked: 'Scout, approval withdrawn' }
const roleWord = role => ROLE_WORDS[role] || role.replaceAll('_', ' ').replace(/^\w/, letter => letter.toUpperCase())

function query(values, keys) {
    const params = new URLSearchParams()
    for (const key of keys) if (values[key] !== '' && values[key] != null) params.set(key, values[key])
    return params.toString()
}

function roleLine(row) {
    const roles = row.roles.map(roleWord).join(', ') || 'Member'
    const clubs = row.programs.map(program => program.name).join(', ')
    return clubs ? `${roles} · ${clubs}` : roles
}

function standing(row) {
    if (row.account_status === 'suspended') return ['warn', 'Suspended']
    if (row.waiting) return ['gold', 'Waiting for approval']
    return ['quiet', row.account_status === 'active' ? 'Active' : roleWord(row.account_status)]
}

export function AdminPeople() { return <B3Gate flag="admin_people"><People /></B3Gate> }

function People() {
    const [values, setValues] = useUrlFilters(DEFAULTS)
    // The search box answers at once; the address bar follows a moment later (one request per word).
    const [search, setSearch] = useState(values.q)
    const debounced = useDebouncedSearch(search)
    const written = useRef(values.q)
    useEffect(() => {
        if (debounced === written.current) return
        written.current = debounced
        setValues({ q: debounced, offset: '0' }, { replace: true })
    }, [debounced, setValues])
    useEffect(() => {
        // Back / forward or a pasted link changed the search from outside the box.
        if (values.q !== written.current) { written.current = values.q; setSearch(values.q) }
    }, [values.q])

    const offset = Number(values.offset) || 0
    const selected = Number(values.person) || null
    const list = useControlData(`/admin/people?${query(values, LIST_KEYS)}`)
    const detail = useControlData(selected ? `/admin/people/${selected}` : null)
    const person = detail.data?.person

    // The club choices are counted by the server under the other filters in force.
    // (`club` rides along only so the chosen club is always among the choices; it does not narrow the counts.)
    const clubQuery = query(values, ['q', 'role', 'standing', 'verified', 'joined', 'seen', 'club'])
    const [clubName, setClubName] = useState('')
    const loadClubs = useCallback(async text => {
        const data = await APIService.adminControlRead(`/admin/people/clubs?${clubQuery}${text ? `&club_q=${encodeURIComponent(text)}` : ''}`)
        return [...data.clubs.map(club => ({ value: String(club.id), label: club.name, count: club.count })), { value: 'none', label: 'No club', count: data.no_club }]
    }, [clubQuery])
    // A shared link names the club by id; its name comes from the people shown or the choices.
    const shownClub = values.club === 'none' ? 'No club'
        : list.data?.rows.flatMap(row => row.programs).find(program => String(program.id) === values.club)?.name || clubName
    useEffect(() => {
        if (!values.club || values.club === 'none' || shownClub) return
        let live = true
        loadClubs('').then(found => { if (live) setClubName(found.find(option => option.value === values.club)?.label || '') }).catch(() => {})
        return () => { live = false }
    }, [values.club, shownClub, loadClubs])

    const filters = useMemo(() => [
        { key: 'club', label: 'Club', anyLabel: 'All clubs', searchable: true, searchPlaceholder: 'Type a club name…', loadOptions: loadClubs, selectedLabel: shownClub || 'Chosen club' },
        { key: 'role', label: 'Type', anyLabel: 'Everyone', defaultValue: 'all', options: options(TYPE) },
        { key: 'standing', label: 'Status', anyLabel: 'Any', defaultValue: 'all', options: options(STATUS) },
        {
            key: 'more', label: 'More', group: [
                { key: 'verified', label: 'Verified', anyLabel: 'Any', options: options([['yes', 'Verified scout'], ['no', 'Not verified']]) },
                { key: 'joined', label: 'Joined', anyLabel: 'Any time', options: options([['7d', 'In the last 7 days'], ['30d', 'In the last 30 days'], ['year', 'In the last year']]) },
                { key: 'seen', label: 'Last seen', anyLabel: 'Any time', options: options([['7d', 'In the last 7 days'], ['30d', 'In the last 30 days'], ['quiet', 'Not for 90 days, or never']]) },
            ],
        },
        { key: 'sort', label: 'Sort', neutral: true, defaultValue: 'name', options: options(SORT) },
    ], [loadClubs, shownClub])

    // Keep the last answer on screen while the next one loads: the count and the list hold their place.
    const [last, setLast] = useState(null)
    useEffect(() => { if (list.data) setLast(list.data) }, [list.data])
    const shown = list.data || last
    const rows = shown?.rows || []

    return (
        <div className="flex flex-col gap-5">
            <CalmHeader
                title="People"
                actions={(
                    <label className="flex h-11 w-full items-center rounded-full border border-chalk/25 px-4 focus-within:border-chalk/60 sm:w-auto sm:min-w-[280px]">
                        <span className="sr-only">Search people</span>
                        <input type="search" maxLength={120} placeholder="Search name or email" value={search} onChange={event => setSearch(event.target.value)} className="w-full flex-1 border-0 bg-transparent text-sm text-chalk outline-none placeholder:text-muted-dark" />
                    </label>
                )}
            />
            <FilterBar
                label="People filters"
                filters={filters}
                values={values}
                onChange={changes => setValues({ ...changes, offset: '0', person: '' })}
                count={shown ? countLabel(shown.total, 'person', 'people') : ''}
            />

            <div className="flex flex-wrap items-start gap-6">
                <section aria-label="Accounts" aria-busy={!list.data && !list.error} className={cn('min-w-0 flex-[3_1_480px] border-t border-chalk/[0.12]', selected && 'hidden xl:block')}>
                    {list.error ? <LoadState {...list} /> : !shown ? <ListSkeleton /> : (
                        <ul className={cn('m-0 list-none p-0 pt-2 transition-opacity', !list.data && 'opacity-60')}>
                            {rows.map(row => {
                                const [tone, words] = standing(row)
                                return (
                                    <li key={row.id}>
                                        <button
                                            type="button"
                                            aria-pressed={selected === row.id}
                                            onClick={() => setValues({ person: String(row.id) })}
                                            className={cn(
                                                'grid w-full grid-cols-1 gap-x-4 gap-y-1 rounded-xl px-3 py-3.5 text-left text-sm [overflow-wrap:anywhere] hover:bg-chalk/[0.04] focus-visible:outline-2 focus-visible:outline-gold sm:grid-cols-[minmax(0,2fr)_minmax(0,2fr)_minmax(0,1fr)]',
                                                selected === row.id && 'bg-chalk/[0.06]',
                                            )}
                                        >
                                            <span className="min-w-0 font-medium text-chalk">{row.display_name || row.email}</span>
                                            <span className="min-w-0 text-[#C9C5BA]">{roleLine(row)}</span>
                                            <StatusWords tone={tone}>{words}</StatusWords>
                                        </button>
                                    </li>
                                )
                            })}
                        </ul>
                    )}
                    {shown && rows.length === 0 && !list.error && <p className="px-3 py-8 text-sm text-muted-dark">No accounts match this search.</p>}
                    <Pagination data={shown} offset={offset} setOffset={value => setValues({ offset: String(value) })} />
                </section>

                {selected && (
                    <aside aria-label="Account details" className={cn(calmPanelClass, 'flex flex-[2_1_300px] flex-col gap-4')}>
                        <button type="button" className="self-start text-sm text-muted-dark underline xl:hidden" onClick={() => setValues({ person: '' })}>Back to accounts</button>
                        <LoadState data={detail.data} error={detail.error} />
                        {person && <PersonPanel key={person.id} person={person} lastOwnerOf={detail.data.last_owner_programs} onDone={() => { list.reload(); detail.reload() }} />}
                    </aside>
                )}
            </div>
        </div>
    )
}

function ListSkeleton() {
    return <div role="status" aria-label="Loading people" className="flex flex-col gap-2 pt-2">{[0, 1, 2, 3, 4].map(index => <div key={index} className="h-12 animate-pulse rounded-xl bg-chalk/[0.05]" />)}</div>
}

function PersonPanel({ person, lastOwnerOf, onDone }) {
    const suspended = person.account_status === 'suspended'
    const [acting, setActing] = useState(false)
    const [tone, words] = standing(person)
    const facts = [
        ['Role', roleLine(person)],
        ['Joined', stamp(person.created_at)],
        ['Last seen', stamp(person.last_login_at)],
        ['Standing', <StatusWords key="standing" tone={tone} className="text-chalk">{words}</StatusWords>],
        ...(person.suspension ? [['Suspension reason', person.suspension.reason || 'Not recorded'], ['Suspended by', person.suspension.by || 'Not recorded'], ['Suspended at', stamp(person.suspension.at)]] : []),
        ...(person.approved_claims ? [['Approved claims', person.approved_claims]] : []),
    ]
    return (
        <>
            <div>
                <h2 className="m-0 text-xl font-semibold text-chalk [overflow-wrap:anywhere]">{person.display_name || person.email}</h2>
                <p className="mt-1 text-sm text-muted-dark [overflow-wrap:anywhere]">{person.email}</p>
            </div>
            <dl className="m-0 grid grid-cols-[max-content_minmax(0,1fr)] gap-x-4 gap-y-2 text-sm">
                {facts.map(([label, value]) => <div key={label} className="contents"><dt className="text-muted-dark">{label}</dt><dd className="m-0 min-w-0 text-chalk [overflow-wrap:anywhere]">{value}</dd></div>)}
            </dl>
            <div className="flex flex-wrap gap-2.5 border-t border-chalk/10 pt-4">
                {/* One action that changes the account; the rest are links to where that work is done. */}
                {!acting && <button type="button" className={suspended ? calmPillButton : calmWarnButton} onClick={() => setActing(true)}>{suspended ? 'Restore…' : 'Suspend…'}</button>}
                <details className="relative">
                    <summary aria-label="More actions" className={cn(calmPillButton, 'cursor-pointer list-none px-3.5 [&::-webkit-details-marker]:hidden')}>⋯</summary>
                    <div className="absolute left-0 z-10 mt-2 flex w-56 flex-col rounded-2xl border border-chalk/20 bg-ink p-2 text-sm">
                        <Link to="/admin/users" className="rounded-[10px] px-3 py-2.5 text-chalk no-underline hover:bg-chalk/[0.06] hover:no-underline">Writer permissions</Link>
                        {person.scout_verification && <Link to={`/admin/trust?tab=verifications&user=${person.id}`} className="rounded-[10px] px-3 py-2.5 text-chalk no-underline hover:bg-chalk/[0.06] hover:no-underline">Review scout verification</Link>}
                        {person.programs.map(program => <Link key={program.id} to="/admin/programs" className="rounded-[10px] px-3 py-2.5 text-chalk no-underline [overflow-wrap:anywhere] hover:bg-chalk/[0.06] hover:no-underline">Open {program.name}</Link>)}
                    </div>
                </details>
            </div>
            {acting && (
                <div>
                    <ReasonAction
                        target={`${person.display_name} (${person.email})`}
                        warning={!suspended && lastOwnerOf?.length ? `This is the last active owner of ${lastOwnerOf.join(', ')}. Suspending them leaves no active owner to manage staff or billing.` : undefined}
                        label={suspended ? 'Restore account' : 'Suspend account'}
                        action={reason => APIService.adminControlAction(`/admin/users/${person.id}/${suspended ? 'restore' : 'suspend'}`, { reason })}
                        onDone={() => { setActing(false); onDone() }}
                    />
                    <button type="button" className="mt-3 text-sm text-muted-dark underline" onClick={() => setActing(false)}>Cancel</button>
                </div>
            )}
            <details className="text-[13px] text-muted-dark">
                <summary className="cursor-pointer">What this view leaves out</summary>
                <p className="mt-2 leading-relaxed">Account details only. Private club notes, feedback and messages are reviewed through their reported case. People can export their own data from account settings.</p>
            </details>
        </>
    )
}
