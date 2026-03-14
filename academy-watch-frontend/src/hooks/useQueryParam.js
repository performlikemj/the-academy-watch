import { useMemo } from 'react'
import { useLocation } from 'react-router-dom'

export function useQueryParam(name, defaultValue = null) {
  const { search } = useLocation()
  return useMemo(() => {
    const params = new URLSearchParams(search)
    return params.get(name) ?? defaultValue
  }, [search, name, defaultValue])
}
