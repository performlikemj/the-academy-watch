import { useEffect, useId, useRef, useState } from 'react'
import { ChevronDown, X } from 'lucide-react'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'
import { clearableKeys, isFilterSet, pillText } from '@/lib/url-filters'

/**
 * The one filter bar for every list (people, clubs, players, scout desk).
 *
 * filters: [{ key, label, options: [{ value, label, count? }], anyLabel?, defaultValue?,
 *             searchable?, searchPlaceholder?, loadOptions?(text) -> Promise<options>,
 *             selectedLabel?, neutral?, group?: [filter, …] }]
 * values:  { key: value } — the page keeps them in the address bar (useUrlFilters).
 * onChange(changes): { key: value, … }; an empty string means "not set".
 * count:   result count text, e.g. "2 people". Filtering itself is the server's job.
 *
 * A filter with a value turns solid and gains ✕. `group` is the "More" pill: several
 * small filters behind one pill. `neutral` (a sort order) never turns solid and is
 * not reset by Clear. Semantic tokens only, so the bar sits on night and chalk alike.
 */
export function FilterBar({ filters, values, onChange, count, label = 'Filters', className }) {
    const set = clearableKeys(filters, values)
    return (
        <div role="group" aria-label={label} className={cn('flex flex-wrap items-center gap-2 text-sm', className)}>
            {filters.map(filter => <FilterPill key={filter.key} filter={filter} values={values} onChange={onChange} />)}
            {set.length > 0 && (
                <button
                    type="button"
                    className="h-10 rounded-full px-3 text-muted-foreground underline underline-offset-2 hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                    onClick={() => onChange(Object.fromEntries(set.map(key => [key, ''])))}
                >
                    Clear
                </button>
            )}
            {/* The count keeps its line while a new answer loads, so the list below does not jump. */}
            <p className="ml-auto min-h-5 text-muted-foreground" aria-live="polite" data-testid="filter-count">{count}</p>
        </div>
    )
}

function FilterPill({ filter, values, onChange }) {
    const [open, setOpen] = useState(false)
    const members = filter.group || [filter]
    const active = !filter.neutral && members.some(member => isFilterSet(member, values))
    const text = pillText(filter, values)
    const pick = changes => { onChange(changes); if (!filter.group) setOpen(false) }
    return (
        <span
            className={cn(
                'inline-flex h-10 max-w-full items-center rounded-full border',
                active ? 'border-transparent bg-primary font-medium text-primary-foreground' : 'border-foreground/25 text-foreground',
            )}
        >
            <Popover open={open} onOpenChange={setOpen}>
                <PopoverTrigger asChild>
                    <button
                        type="button"
                        aria-haspopup="listbox"
                        className={cn(
                            'flex h-full min-w-0 items-center gap-1.5 rounded-full pl-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring',
                            active ? 'pr-1.5' : 'pr-3.5',
                        )}
                    >
                        <span className="min-w-0 truncate">{text}</span>
                        <ChevronDown className="h-4 w-4 flex-none opacity-70" aria-hidden="true" />
                    </button>
                </PopoverTrigger>
                <PopoverContent
                    align="start"
                    sideOffset={8}
                    className="w-[min(300px,calc(100vw-2rem))] rounded-2xl border-foreground/20 p-3 text-sm"
                >
                    {filter.group
                        ? <div className="flex flex-col gap-4">{filter.group.map(member => <OptionList key={member.key} filter={member} value={values[member.key]} onPick={pick} titled />)}</div>
                        : <OptionList filter={filter} value={values[filter.key]} onPick={pick} />}
                </PopoverContent>
            </Popover>
            {active && (
                <button
                    type="button"
                    aria-label={`Clear ${filter.label}`}
                    className="mr-1 flex h-8 w-8 flex-none items-center justify-center rounded-full hover:bg-primary-foreground/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                    onClick={() => onChange(Object.fromEntries(members.map(member => [member.key, ''])))}
                >
                    <X className="h-4 w-4" aria-hidden="true" />
                </button>
            )}
        </span>
    )
}

function OptionList({ filter, value, onPick, titled = false }) {
    const titleId = useId()
    const [text, setText] = useState('')
    const [loaded, setLoaded] = useState(null)
    const [failed, setFailed] = useState(false)
    const load = filter.loadOptions
    const request = useRef(0)

    // Type-ahead is answered by the server when the filter can ask it; a short
    // pause between keystrokes keeps it to one request per word.
    useEffect(() => {
        if (!load) return
        const id = ++request.current
        const timer = setTimeout(() => {
            load(text.trim()).then(options => {
                if (request.current === id) { setLoaded(options); setFailed(false) }
            }).catch(() => { if (request.current === id) setFailed(true) })
        }, text ? 250 : 0)
        return () => clearTimeout(timer)
    }, [load, text])

    const any = filter.defaultValue ?? ''
    const source = load ? (loaded || filter.options || []) : (filter.options || [])
    const needle = text.trim().toLowerCase()
    const options = load || !needle ? source : source.filter(option => option.label.toLowerCase().includes(needle))
    const current = value ?? any

    const row = (optionValue, optionLabel, optionCount) => {
        const selected = String(current) === String(optionValue)
        return (
            <button
                key={String(optionValue)}
                type="button"
                role="option"
                aria-selected={selected}
                className={cn(
                    'flex w-full items-baseline justify-between gap-3 rounded-[10px] px-3 py-2.5 text-left hover:bg-foreground/[0.06] focus-visible:outline-2 focus-visible:outline-ring',
                    selected ? 'bg-foreground/[0.08] font-medium text-foreground' : 'text-foreground/80',
                )}
                onClick={() => onPick({ [filter.key]: optionValue })}
            >
                <span className="min-w-0 [overflow-wrap:anywhere]">{selected && optionValue !== any ? '✓ ' : ''}{optionLabel}</span>
                {Number.isFinite(optionCount) && <span className="flex-none font-normal text-muted-foreground">{optionCount.toLocaleString('en-GB')}</span>}
            </button>
        )
    }

    return (
        <div className="flex flex-col gap-0.5">
            {titled && <p id={titleId} className="px-3 pb-1 text-[13px] text-muted-foreground">{filter.label}</p>}
            {filter.searchable && (
                <label className="mb-2 block">
                    <span className="sr-only">{filter.searchPlaceholder || `Search ${filter.label.toLowerCase()}`}</span>
                    <input
                        type="search"
                        value={text}
                        maxLength={120}
                        autoComplete="off"
                        onChange={event => setText(event.target.value)}
                        placeholder={filter.searchPlaceholder || `Type a ${filter.label.toLowerCase()} name…`}
                        className="h-10 w-full rounded-[10px] border border-foreground/20 bg-transparent px-3 text-foreground placeholder:text-muted-foreground focus-visible:outline-2 focus-visible:outline-ring"
                    />
                </label>
            )}
            <div role="listbox" aria-label={titled ? undefined : filter.label} aria-labelledby={titled ? titleId : undefined} className="flex max-h-[min(320px,50vh)] flex-col gap-0.5 overflow-y-auto">
                {!filter.neutral && row(any, filter.anyLabel || 'Any')}
                {options.map(option => row(option.value, option.label, option.count))}
                {load && !loaded && !failed && <p role="status" className="px-3 py-2.5 text-muted-foreground">Loading…</p>}
                {failed && <p role="alert" className="px-3 py-2.5 text-muted-foreground">Could not load these choices.</p>}
                {(!load || loaded) && !failed && needle && options.length === 0 && <p className="px-3 py-2.5 text-muted-foreground">Nothing matches “{text.trim()}”.</p>}
            </div>
        </div>
    )
}
