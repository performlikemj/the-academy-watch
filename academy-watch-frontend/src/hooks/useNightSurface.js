import { useLayoutEffect } from 'react'
import '@/styles/floodlight-night.css'

const NIGHT_CLASSES = ['dark', 'fl-night']

/**
 * Put the whole document on a Floodlight night surface while the calling
 * route is mounted (scout desk, admin control room). Scoping to <html> keeps
 * portalled Radix content — dialogs, selects, popovers — on the same surface.
 */
export function useNightSurface() {
  useLayoutEffect(() => {
    const root = document.documentElement
    NIGHT_CLASSES.forEach((name) => root.classList.add(name))
    return () => NIGHT_CLASSES.forEach((name) => root.classList.remove(name))
  }, [])
}
