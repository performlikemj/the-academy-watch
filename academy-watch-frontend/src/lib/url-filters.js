// Filters that live in the address bar: a reload, back/forward and a shared
// link all show the same list. Pure helpers here; the hook is useUrlFilters.

/** Next query string after `changes`; a value equal to its default leaves the address clean. */
export function nextFilterParams(current, changes, defaults = {}) {
    const next = new URLSearchParams(current)
    for (const [key, value] of Object.entries(changes)) {
        if (value == null || value === '' || String(value) === String(defaults[key] ?? '')) next.delete(key)
        else next.set(key, String(value))
    }
    return next
}

export function readFilters(params, defaults) {
    return Object.fromEntries(Object.keys(defaults).map(key => [key, params.get(key) ?? defaults[key]]))
}

/** Flat list of the single filters in a bar (a "More" group counts as its members). */
export function flatFilters(filters) {
    return filters.flatMap(filter => filter.group || [filter])
}

export function isFilterSet(filter, values) {
    const value = values[filter.key]
    return value != null && value !== '' && value !== (filter.defaultValue ?? '')
}

/** The filters "Clear" resets: everything set, except neutral ones such as the sort order. */
export function clearableKeys(filters, values) {
    return flatFilters(filters).filter(filter => !filter.neutral && isFilterSet(filter, values)).map(filter => filter.key)
}

export function optionLabel(filter, value) {
    // A neutral filter (the sort order) has no "any": its default is a real choice with a name.
    if (!filter.neutral && (value === (filter.defaultValue ?? '') || value == null)) return filter.anyLabel || 'Any'
    const found = (filter.options || []).find(option => String(option.value) === String(value ?? filter.defaultValue))
    return found?.label ?? filter.selectedLabel ?? String(value)
}

/** Text on a pill: "Club: Quillmere Athletic", "Status: Any", "More: Verified, Joined". */
export function pillText(filter, values) {
    if (!filter.group) return `${filter.label}: ${optionLabel(filter, values[filter.key])}`
    const set = filter.group.filter(member => isFilterSet(member, values))
    return set.length ? `${filter.label}: ${set.map(member => member.label).join(', ')}` : filter.label
}

/** "1 person", "2 people", "0 clubs". */
export function countLabel(total, one, many) {
    return Number.isFinite(total) ? `${total.toLocaleString('en-GB')} ${total === 1 ? one : many}` : ''
}
