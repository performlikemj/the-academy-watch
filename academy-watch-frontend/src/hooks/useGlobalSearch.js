import * as React from "react"

const RECENT_SEARCHES_KEY = 'gol-recent-searches'
const MAX_RECENT_SEARCHES = 5

/**
 * Hook for managing global search state and keyboard shortcuts
 * @returns {object} - { isOpen, open, close, toggle, recentSearches, addRecentSearch, clearRecentSearches }
 */
export function useGlobalSearch() {
  const [isOpen, setIsOpen] = React.useState(false)
  const [recentSearches, setRecentSearches] = React.useState([])

  // Load recent searches from localStorage on mount
  React.useEffect(() => {
    try {
      const stored = localStorage.getItem(RECENT_SEARCHES_KEY)
      if (stored) {
        const parsed = JSON.parse(stored)
        if (Array.isArray(parsed)) {
          setRecentSearches(parsed.slice(0, MAX_RECENT_SEARCHES))
        }
      }
    } catch {
      // Ignore localStorage errors
    }
  }, [])

  // Save recent searches to localStorage
  const saveRecentSearches = React.useCallback((searches) => {
    try {
      localStorage.setItem(RECENT_SEARCHES_KEY, JSON.stringify(searches))
    } catch {
      // Ignore localStorage errors
    }
  }, [])

  // Add a search to recent searches
  const addRecentSearch = React.useCallback((search) => {
    if (!search || typeof search !== 'object') return

    setRecentSearches((prev) => {
      // Remove duplicate if exists
      const filtered = prev.filter(
        (s) => !(s.type === search.type && s.id === search.id)
      )
      // Add to front, limit to max
      const updated = [search, ...filtered].slice(0, MAX_RECENT_SEARCHES)
      saveRecentSearches(updated)
      return updated
    })
  }, [saveRecentSearches])

  // Clear recent searches
  const clearRecentSearches = React.useCallback(() => {
    setRecentSearches([])
    try {
      localStorage.removeItem(RECENT_SEARCHES_KEY)
    } catch {
      // Ignore
    }
  }, [])

  // Keyboard shortcut handler
  React.useEffect(() => {
    const handleKeyDown = (e) => {
      // Cmd+K (Mac) or Ctrl+K (Windows/Linux)
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setIsOpen((prev) => !prev)
      }
      // Escape to close
      if (e.key === 'Escape' && isOpen) {
        setIsOpen(false)
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isOpen])

  const open = React.useCallback(() => setIsOpen(true), [])
  const close = React.useCallback(() => setIsOpen(false), [])
  const toggle = React.useCallback(() => setIsOpen((prev) => !prev), [])

  return {
    isOpen,
    open,
    close,
    toggle,
    setIsOpen,
    recentSearches,
    addRecentSearch,
    clearRecentSearches,
  }
}

export default useGlobalSearch
