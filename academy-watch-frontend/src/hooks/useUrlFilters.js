import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { nextFilterParams, readFilters } from '@/lib/url-filters'

/**
 * Filter values kept in the query string. `defaults` must be a stable object
 * ({ key: defaultValue }). A pick pushes a history entry, so back/forward walk
 * the filters; pass { replace: true } for typing.
 */
export function useUrlFilters(defaults) {
    const [params, setParams] = useSearchParams()
    const values = useMemo(() => readFilters(params, defaults), [params, defaults])
    const set = useCallback((changes, { replace = false } = {}) => {
        setParams(current => nextFilterParams(current, changes, defaults), { replace })
    }, [setParams, defaults])
    return [values, set]
}
