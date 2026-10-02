import { useEffect, useState } from 'react'
import { displaySeasonFromDirectory } from '@/lib/seasons'
import { getSeasonDirectory } from '@/lib/seasonDirectory'

export function useSeasonDirectory() {
  const [state, setState] = useState({ directory: null, ready: false, error: false })
  useEffect(() => {
    let live = true
    getSeasonDirectory()
      .then((directory) => { if (live) setState({ directory, ready: true, error: false }) })
      .catch(() => { if (live) setState({ directory: null, ready: true, error: true }) })
    return () => { live = false }
  }, [])
  const value = state.directory?.current_season
  const currentSeason = value != null && Number.isInteger(Number(value)) ? Number(value) : undefined
  return { ...state, currentSeason, displaySeason: displaySeasonFromDirectory(state.directory) }
}
