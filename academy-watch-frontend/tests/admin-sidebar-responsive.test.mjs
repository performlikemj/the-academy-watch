import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'

const layoutFile = new URL('../src/components/layouts/AdminLayout.jsx', import.meta.url)
const sidebarFile = new URL('../src/components/admin/AdminSidebar.jsx', import.meta.url)

test('admin layout exposes a mobile-only sidebar toggle', async () => {
  const src = await fs.readFile(layoutFile, 'utf8')

  assert.match(
    src,
    /data-testid=\"admin-menu-toggle\"/,
    'header should include a toggle control for opening the sidebar'
  )

  const toggleSection = src.split('data-testid="admin-menu-toggle"')[1] || ''
  assert.match(toggleSection, /md:hidden/, 'mobile toggle should be hidden at md and up to avoid duplicate chrome on desktop')
})

test('admin layout provides a desktop collapse control and sidebar supports a collapsed state', async () => {
  const layoutSrc = await fs.readFile(layoutFile, 'utf8')
  const sidebarSrc = await fs.readFile(sidebarFile, 'utf8')

  assert.match(
    layoutSrc,
    /data-testid=\"admin-collapse-toggle\"/,
    'desktop header should surface a collapse/expand control for the admin sidebar'
  )

  const collapseSection = layoutSrc.split('data-testid="admin-collapse-toggle"')[1] || ''
  assert.match(collapseSection, /(hidden lg:inline-flex|lg:inline-flex hidden)/, 'collapse control should only appear on large screens where the persistent sidebar renders')

  assert.ok(sidebarSrc.includes('collapsed ?'), 'AdminSidebar should accept a collapsed flag to shrink labels for more workspace')
})
