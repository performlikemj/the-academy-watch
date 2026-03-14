export function getAdminQuickLinks() {
  return [
    { label: 'API Key', href: '#admin-api' },
    { label: 'Newsletters', href: '/admin?tab=newsletters', spa: true },
    { label: 'Loans', href: '/admin?tab=loans', spa: true },
    { label: 'Sandbox checks', href: '/admin/sandbox', spa: true },
    { label: 'Tools', href: '/admin?tab=tools', spa: true },
    { label: 'Settings', href: '/admin?tab=settings', spa: true },
  ]
}
