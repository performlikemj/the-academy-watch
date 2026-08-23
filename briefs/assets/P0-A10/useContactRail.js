import { useEffect, useState } from 'react'
import { APIService } from '@/lib/api'
import { loadContactRail, peekContactRail } from '@/lib/contact-flags'

// null = not known yet, true/false once /api/features answered. Entry points render only on `=== true`.
export function useContactRail() {
  const [enabled, setEnabled] = useState(() => peekContactRail())
  useEffect(() => {
    let live = true
    loadContactRail(() => APIService.getFeatures()).then((value) => {
      if (live) setEnabled(value)
    })
    return () => { live = false }
  }, [])
  return enabled
}
