import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetClose,
} from '@/components/ui/sheet'
import { useAuth, useAuthUI } from '@/context/AuthContext'
import { useGlobalSearchContext } from '@/context/GlobalSearchContext'
import { isNativeApp } from '@/lib/platform'
import {
  Home,
  Compass,
  Search,
  ListChecks,
  CircleUser,
  Users,
  FileText,
  Trophy,
  UserPlus,
  MessageCircle,
  UserCog,
  Settings,
  CreditCard,
  PenSquare,
  ClipboardCheck,
  LogIn,
  LogOut,
  ChevronRight,
} from 'lucide-react'

// The iOS-style bottom tab bar. Mobile-only (`md:hidden`); desktop keeps the
// existing top nav untouched. Fixed to the bottom with a safe-area inset so it
// clears the iPhone home indicator. Sits above page content (z-40) but below
// dialogs/sheets (z-50).

function tabClasses(active) {
  return (
    'flex h-full min-h-[44px] flex-col items-center justify-center gap-0.5 ' +
    'px-1 transition-colors focus-visible:outline-none focus-visible:ring-2 ' +
    'focus-visible:ring-ring ' +
    (active ? 'text-primary' : 'text-muted-foreground hover:text-foreground')
  )
}

function TabLabel({ children }) {
  return <span className="text-[11px] font-medium leading-none">{children}</span>
}

// A single row inside the More sheet — icon + label + chevron, 48px min height,
// styled like an iOS settings list row.
function MoreRow({ icon: Icon, label, to, onSelect }) {
  const inner = (
    <>
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-secondary text-foreground">
        <Icon className="h-4 w-4" />
      </span>
      <span className="flex-1 text-left text-[15px] font-medium text-foreground">{label}</span>
      <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
    </>
  )
  const rowClass =
    'flex min-h-[48px] w-full items-center gap-3 rounded-xl px-3 py-2 ' +
    'transition-colors hover:bg-secondary active:bg-secondary no-underline hover:no-underline'
  if (to) {
    return (
      <SheetClose asChild>
        <Link to={to} className={rowClass} onClick={onSelect}>
          {inner}
        </Link>
      </SheetClose>
    )
  }
  return (
    <button type="button" className={rowClass} onClick={onSelect}>
      {inner}
    </button>
  )
}

function MoreGroup({ title, children }) {
  return (
    <div className="space-y-1">
      <p className="px-3 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </p>
      <div className="space-y-0.5">{children}</div>
    </div>
  )
}

export function MobileTabBar() {
  const location = useLocation()
  const { open: openSearch } = useGlobalSearchContext()
  const { token, isAdmin, hasApiKey, isJournalist, isCurator } = useAuth()
  const { openLoginModal, logout } = useAuthUI()
  const [moreOpen, setMoreOpen] = useState(false)

  const native = isNativeApp()
  // Same unlock rule as the desktop nav — and never in the native app,
  // where admin is excluded entirely.
  const adminUnlocked = !native && !!token && isAdmin && hasApiKey
  const path = location.pathname

  const isHome = path === '/'
  const isFollowing = path.startsWith('/scout/lists') || path.startsWith('/scout/watchlist')
  const isDiscover = !isFollowing && path.startsWith('/scout')

  return (
    <>
      <nav
        aria-label="Primary"
        className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-card/95 backdrop-blur supports-[backdrop-filter]:bg-card/80 pb-[env(safe-area-inset-bottom)] md:hidden"
      >
        <ul className="grid h-14 grid-cols-5">
          <li className="contents">
            <Link
              to="/"
              className={tabClasses(isHome)}
              aria-label="Home"
              aria-current={isHome ? 'page' : undefined}
            >
              <Home className="h-5 w-5" aria-hidden="true" />
              <TabLabel>Home</TabLabel>
            </Link>
          </li>
          <li className="contents">
            <Link
              to="/scout"
              className={tabClasses(isDiscover)}
              aria-label="Discover"
              aria-current={isDiscover ? 'page' : undefined}
            >
              <Compass className="h-5 w-5" aria-hidden="true" />
              <TabLabel>Discover</TabLabel>
            </Link>
          </li>
          <li className="contents">
            <button
              type="button"
              onClick={openSearch}
              className={tabClasses(false)}
              aria-label="Search"
            >
              <Search className="h-5 w-5" aria-hidden="true" />
              <TabLabel>Search</TabLabel>
            </button>
          </li>
          <li className="contents">
            <Link
              to="/scout/lists"
              className={tabClasses(isFollowing)}
              aria-label="Following"
              aria-current={isFollowing ? 'page' : undefined}
            >
              <ListChecks className="h-5 w-5" aria-hidden="true" />
              <TabLabel>Following</TabLabel>
            </Link>
          </li>
          <li className="contents">
            <button
              type="button"
              onClick={() => setMoreOpen(true)}
              className={tabClasses(moreOpen)}
              aria-label="More"
              aria-haspopup="dialog"
              aria-expanded={moreOpen}
            >
              <CircleUser className="h-5 w-5" aria-hidden="true" />
              <TabLabel>More</TabLabel>
            </button>
          </li>
        </ul>
      </nav>

      <Sheet open={moreOpen} onOpenChange={setMoreOpen}>
        <SheetContent
          side="bottom"
          className="max-h-[85dvh] gap-0 overflow-y-auto rounded-t-2xl pb-[max(env(safe-area-inset-bottom),1rem)]"
        >
          <div className="mx-auto mt-2 h-1 w-10 shrink-0 rounded-full bg-border" aria-hidden="true" />
          <SheetHeader className="pb-2">
            <SheetTitle>More</SheetTitle>
            <SheetDescription className="sr-only">
              Browse teams, newsletters, and account options.
            </SheetDescription>
          </SheetHeader>

          <div className="space-y-5 px-4 pb-2">
            <MoreGroup title="Explore">
              <MoreRow icon={Users} label="Teams" to="/teams" />
              <MoreRow icon={FileText} label="Newsletters" to="/newsletters" />
              <MoreRow icon={Trophy} label="Dream XI" to="/dream-team" />
              <MoreRow icon={UserPlus} label="Journalists" to="/journalists" />
            </MoreGroup>

            <MoreGroup title="Take part">
              <MoreRow icon={MessageCircle} label="Submit a Take" to="/submit-take" />
            </MoreGroup>

            {(isJournalist || isCurator) && (
              <MoreGroup title="Your dashboards">
                {isJournalist && (
                  <MoreRow icon={PenSquare} label="Writer Dashboard" to="/writer/dashboard" />
                )}
                {isCurator && (
                  <MoreRow icon={ClipboardCheck} label="Curator" to="/curator/dashboard" />
                )}
              </MoreGroup>
            )}

            <MoreGroup title="Account">
              {token && <MoreRow icon={UserCog} label="Settings" to="/settings" />}
              {adminUnlocked && <MoreRow icon={Settings} label="Admin" to="/admin" />}
              {!native && <MoreRow icon={CreditCard} label="Pricing" to="/pricing" />}
              {token ? (
                <MoreRow
                  icon={LogOut}
                  label="Sign out"
                  onSelect={() => {
                    setMoreOpen(false)
                    logout()
                  }}
                />
              ) : (
                <MoreRow
                  icon={LogIn}
                  label="Sign in"
                  onSelect={() => {
                    setMoreOpen(false)
                    openLoginModal()
                  }}
                />
              )}
            </MoreGroup>
          </div>
        </SheetContent>
      </Sheet>
    </>
  )
}

export default MobileTabBar
