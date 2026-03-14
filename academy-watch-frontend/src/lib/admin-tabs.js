const ALL_ADMIN_TABS = ['newsletters', 'loans', 'tools', 'settings']

export function getAdminTabs({ includeSandbox = true } = {}) {
  if (includeSandbox) return ALL_ADMIN_TABS
  return ALL_ADMIN_TABS.filter((tab) => tab !== 'tools')
}

export function resolveAdminTab({
  searchParams,
  defaultTab = 'newsletters',
  allowedTabs = ALL_ADMIN_TABS,
  forcedTab = null,
} = {}) {
  const allowedSet = new Set(allowedTabs && allowedTabs.length ? allowedTabs : ALL_ADMIN_TABS)

  if (forcedTab && allowedSet.has(forcedTab)) {
    return forcedTab
  }

  const candidate = searchParams?.get ? searchParams.get('tab') : null
  if (candidate && allowedSet.has(candidate)) return candidate

  if (allowedSet.has(defaultTab)) return defaultTab
  return 'newsletters'
}

export const ADMIN_TAB_KEYS = ALL_ADMIN_TABS
