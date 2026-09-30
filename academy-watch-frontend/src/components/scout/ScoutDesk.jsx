import { NavLink } from 'react-router-dom'
import { useContactRail } from '@/hooks/useContactRail.js'
import { useNightSurface } from '@/hooks/useNightSurface'
import { cn } from '@/lib/utils'

/**
 * Floodlight scout desk chrome: a night surface, the desk's own sub-nav and
 * an editorial page header. Presentational only — pages keep their data,
 * API calls and actions.
 */

const DESK_LINKS = [
    { to: '/scout', label: 'Discover', end: true },
    { to: '/scout/watchlist', label: 'Watchlist' },
    { to: '/scout/lists', label: 'Lists' },
    { to: '/introductions', label: 'Introductions', contactRailOnly: true },
    { to: '/scout/verification', label: 'Verification' },
]

export function ScoutDeskNav({ className }) {
    const contactRail = useContactRail()
    const links = DESK_LINKS.filter((link) => !link.contactRailOnly || contactRail === true)
    return (
        <nav aria-label="Scout desk" className={cn('border-b border-hairline-dark', className)}>
            <div className="floodlight-container flex items-center gap-7 overflow-x-auto sm:gap-8 [scrollbar-width:none]">
                {links.map((link) => (
                    <NavLink
                        key={link.to}
                        to={link.to}
                        end={link.end}
                        className={({ isActive }) => cn(
                            'relative shrink-0 py-4 text-[14.5px] no-underline transition-colors duration-150 hover:no-underline',
                            isActive
                                ? 'text-chalk after:absolute after:inset-x-0 after:bottom-[-1px] after:h-px after:bg-gold'
                                : 'text-muted-dark hover:text-chalk'
                        )}
                    >
                        {link.label}
                    </NavLink>
                ))}
            </div>
        </nav>
    )
}

export function ScoutSurface({ children, className, showNav = true }) {
    useNightSurface()
    return (
        <div className={cn('min-h-screen bg-night text-chalk', className)}>
            {showNav ? <ScoutDeskNav /> : null}
            {children}
        </div>
    )
}

export function ScoutHeader({ eyebrow, title, accent, lede, actions, children, className }) {
    return (
        <header className={cn('flex flex-col gap-6 pb-8 pt-10 sm:pt-12', className)}>
            <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
                <div className="min-w-0">
                    {eyebrow ? <p className="eyebrow mb-4">{eyebrow}</p> : null}
                    <h1 className="display text-[2.75rem] leading-[.95] text-chalk sm:text-6xl lg:text-[4.5rem]">
                        {title}
                        {accent ? <> <em className="text-gold">{accent}</em></> : null}
                    </h1>
                    {lede ? <p className="mt-4 max-w-2xl text-[15px] leading-relaxed text-muted-dark">{lede}</p> : null}
                </div>
                {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2 lg:justify-end">{actions}</div> : null}
            </div>
            {children}
        </header>
    )
}

export function DeskSectionTitle({ title, count, action, as: Tag = 'h2', className, id }) {
    return (
        <div className={cn('flex items-baseline justify-between gap-4 border-b border-chalk pb-3', className)}>
            <Tag id={id} className="display text-[1.875rem] leading-none text-chalk sm:text-[2.125rem]">{title}</Tag>
            <div className="flex items-baseline gap-4">
                {count != null ? <span className="font-mono text-[11px] uppercase tracking-[0.16em] text-[#8C9791]">{count}</span> : null}
                {action}
            </div>
        </div>
    )
}

// Outline pill used for secondary desk actions (Watchlist, Lists, Export…).
export const deskPillClass = 'h-10 rounded-full border-chalk/30 bg-transparent px-4 text-[13.5px] font-normal text-chalk hover:border-chalk/60 hover:bg-chalk/[0.04] hover:text-chalk'
