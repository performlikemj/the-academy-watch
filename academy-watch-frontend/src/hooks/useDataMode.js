import { useEffect, useState } from 'react'
import { APIService } from '@/lib/api'

export function useDataMode() {
  const [mode, setMode] = useState({ api_football_frozen: false, newsletters_frozen: false })
  useEffect(() => {
    let active = true
    APIService.getDataMode().then((value) => { if (active) setMode(value) }).catch(() => {})
    return () => { active = false }
  }, [])
  return mode
}
