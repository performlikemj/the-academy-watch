import { Link } from 'react-router-dom'
import { Search, Star, Trophy, Newspaper, Users, Globe } from 'lucide-react'

// Fan front door on mobile: the strongest existing destinations one tap away.
// Pure navigation to routes the app already has — no new data sources.
const TILES = [
  { to: '/scout', label: 'Discover', sub: 'Rank talent', icon: Search },
  { to: '/academy', label: 'Academies', sub: 'Cohorts', icon: Users },
  { to: '/newsletters', label: 'Newsletters', sub: 'Weekly reports', icon: Newspaper },
  { to: '/dream-team', label: 'Dream XI', sub: 'Build a side', icon: Trophy },
  { to: '/teams', label: 'Clubs', sub: 'Follow & subscribe', icon: Globe },
  { to: '/scout/watchlist', label: 'Watchlist', sub: 'Your radar', icon: Star },
]

/** Mobile-only (< sm) grid of primary entry points, shown high on Home. */
export function MobileQuickNav({ className = '' }) {
  return (
    <nav aria-label="Explore" className={`grid grid-cols-2 gap-3 ${className}`}>
      {TILES.map(({ to, label, sub, icon: Icon }) => (
        <Link
          key={to}
          to={to}
          className="group flex min-h-[76px] flex-col justify-between rounded-xl border border-border bg-card p-3.5 no-underline shadow-sm transition-colors hover:border-primary/30 active:bg-secondary/60"
        >
          <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10">
            <Icon className="h-5 w-5 text-primary" />
          </span>
          <span className="mt-2">
            <span className="block text-sm font-semibold text-foreground">{label}</span>
            <span className="block text-xs text-muted-foreground">{sub}</span>
          </span>
        </Link>
      ))}
    </nav>
  )
}

export default MobileQuickNav
