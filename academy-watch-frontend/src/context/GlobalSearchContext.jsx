import { createContext, useContext } from 'react'

export const GlobalSearchContext = createContext({
  isOpen: false,
  open: () => {},
  close: () => {},
  toggle: () => {},
  recentSearches: [],
  addRecentSearch: () => {},
  clearRecentSearches: () => {},
})

export function useGlobalSearchContext() {
  return useContext(GlobalSearchContext)
}
