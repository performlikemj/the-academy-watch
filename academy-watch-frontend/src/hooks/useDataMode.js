import { useEffect, useState } from 'react'
import { APIService } from '@/lib/api'

const defaultMode = { api_football_frozen: false, newsletters_frozen: false }
let modeRequest

export function loadDataMode() {
  modeRequest ??= APIService.getDataMode().catch(() => defaultMode)
  return modeRequest
}

export function useDataMode() {
  const [mode, setMode] = useState(defaultMode)
  useEffect(() => {
    let active = true
    loadDataMode().then((value) => { if (active) setMode(value) })
    return () => { active = false }
  }, [])
  return mode
}
