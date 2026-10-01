import { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { cn } from '@/lib/utils'
import {
    LayoutDashboard,
    Mail,
    Users,
    Settings,
    LogOut,
    Home,
    Shield,
    Megaphone,
    GraduationCap,
    Settings2,
    FlaskConical,
    ChevronDown,
    Video,
    Inbox,
    Sprout,
    Trophy,
    Wrench,
    UserCog,
    Star,
    Landmark,
    HandHeart,
    ShieldCheck,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from '@/components/ui/collapsible'
import { useAuthUI } from '@/context/AuthContext'
import { fetchInboxCounts } from '@/pages/admin/AdminInbox'
import { APIService } from '@/lib/api'

// --- p2-b3 begin ---
import { useControlFlags } from '@/components/admin/B3Control'
// --- p2-b3 end ---

const GROUPS_KEY = 'academy_watch_admin_sidebar_groups'
const BRAND_LOGO_SRC = '/assets/loan_army_assets/apple-touch-icon.png'

// Control-room navigation, grouped like the Floodlight boards. Every admin
// route stays reachable; the API-Football era tools sit in a collapsible
// "Legacy tools" group at the bottom.
const sidebarGroups = [
    {
        label: 'Overview',
        items: [
            { icon: LayoutDashboard, label: 'Today', href: '/admin/dashboard' },
            { icon: Mail, label: 'Interest sign-ups', href: '/admin/interest' },
        ],
    },
    {
        label: 'Review',
        items: [
            { icon: Inbox, label: 'Review queue', href: '/admin/inbox', badge: 'inbox' },
            { icon: ShieldCheck, label: 'Trust & safety', href: '/admin/trust', badge: 'trust' },
        ],
    },
    {
        label: 'Clubs & people',
        items: [
            { icon: Landmark, label: 'Clubs', href: '/admin/local-clubs' },
            { icon: Shield, label: 'Club identities', href: '/admin/club-identities' },
            { icon: Star, label: 'Showcase', href: '/admin/showcase' },
            { icon: UserCog, label: 'Accounts & writers', href: '/admin/users' },
            { icon: Users, label: 'Players', href: '/admin/players' },
            { icon: Shield, label: 'Teams', href: '/admin/teams' },
        ],
    },
    {
        label: 'Operations',
        items: [
            { icon: Video, label: 'Film Room', href: '/admin/video' },
            { icon: HandHeart, label: 'Funding registry', href: '/admin/funding' },
            { icon: Wrench, label: 'Operations', href: '/admin/operations' },
            { icon: Settings, label: 'Settings', href: '/admin/settings' },
        ],
    },
    {
        label: 'Legacy tools',
        collapsible: true,
        items: [
            { icon: Mail, label: 'Newsletters', href: '/admin/newsletters' },
            { icon: Megaphone, label: 'Sponsors', href: '/admin/sponsors' },
            { icon: Trophy, label: 'Youth leagues', href: '/admin/academy' },
            { icon: GraduationCap, label: 'Cohorts', href: '/admin/cohorts' },
            { icon: Sprout, label: 'Seeding & rebuild', href: '/admin/seeding' },
            { icon: Settings2, label: 'API & configs', href: '/admin/tools' },
            { icon: FlaskConical, label: 'Classifier tester', href: '/admin/sandbox' },
        ],
    },
]

const isItemActive = (pathname, href) => pathname === href || pathname.startsWith(`${href}/`)

function loadGroupState() {
    try {
        const stored = localStorage.getItem(GROUPS_KEY)
        return stored ? JSON.parse(stored) : {}
    } catch {
        return {}
    }
}

function saveGroupState(state) {
    try {
        localStorage.setItem(GROUPS_KEY, JSON.stringify(state))
    } catch { /* ignore */ }
}

export function AdminSidebar({ className, collapsed = false, onNavigate }) {
    // --- p2-b3 begin ---
    const flags = useControlFlags()
    const groups = sidebarGroups.map(group => ({ ...group, items: [...group.items] }))
    if (flags?.admin_programs) groups[2].items.unshift({ icon: Landmark, label: 'Programs', href: '/admin/programs' })
    if (flags?.admin_people) groups[2].items.unshift({ icon: Users, label: 'People', href: '/admin/people' })
    if (flags?.admin_safety) groups[1].items.push({ icon: ShieldCheck, label: 'Safeguarding', href: '/admin/safety' })
    if (flags?.admin_business) groups[3].items.push({ icon: Landmark, label: 'Business & data', href: '/admin/business' })
    // --- p2-b3 end ---
    const location = useLocation()
    const { logout } = useAuthUI()
    const [groupOpen, setGroupOpen] = useState(() => loadGroupState())
    const [inboxCount, setInboxCount] = useState(0)
    const [trustCount, setTrustCount] = useState(0)

    useEffect(() => {
        saveGroupState(groupOpen)
    }, [groupOpen])

    useEffect(() => {
        let cancelled = false
        const refresh = () => {
            fetchInboxCounts()
                .then((counts) => { if (!cancelled) setInboxCount(counts?.total || 0) })
                .catch(() => { /* badge is best-effort */ })
        }
        refresh()
        const interval = setInterval(refresh, 120000)
        return () => { cancelled = true; clearInterval(interval) }
    }, [location.pathname])

    useEffect(() => {
        let cancelled = false
        const refresh = async () => {
            try {
                const [verifications, reports] = await Promise.all([
                    APIService.adminListScoutVerifications({ status: 'pending', limit: 1 }),
                    APIService.adminListContentReports({ status: 'open', limit: 1 }),
                ])
                if (!cancelled) {
                    setTrustCount((verifications?.total || 0) + (reports?.total || 0))
                }
            } catch { /* badge is best-effort */ }
        }
        refresh()
        const interval = setInterval(refresh, 120000)
        return () => { cancelled = true; clearInterval(interval) }
    }, [location.pathname])

    const handleNavigate = () => {
        if (onNavigate) onNavigate()
    }

    const isGroupActive = (group) =>
        group.items.some((item) => isItemActive(location.pathname, item.href))

    const isOpen = (group) => {
        if (!group.collapsible) return true
        if (groupOpen[group.label] !== undefined) return groupOpen[group.label]
        return isGroupActive(group)
    }

    const toggleGroup = (group) => {
        setGroupOpen((prev) => ({ ...prev, [group.label]: !isOpen(group) }))
    }

    const badgeValue = (item) => {
        if (item.badge === 'inbox') return inboxCount
        if (item.badge === 'trust') return trustCount
        return 0
    }

    const renderItem = (item) => {
        const active = isItemActive(location.pathname, item.href)
        const count = badgeValue(item)
        return (
            <Link
                key={item.href}
                to={item.href}
                onClick={handleNavigate}
                aria-current={active ? 'page' : undefined}
                title={collapsed ? item.label : undefined}
                className={cn(
                    'group flex h-[34px] items-center gap-3 rounded-[7px] px-2.5 text-sm no-underline transition-colors duration-150 hover:no-underline',
                    'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gold',
                    active
                        ? 'bg-chalk/[0.08] text-chalk'
                        : 'text-muted-dark hover:bg-chalk/[0.04] hover:text-chalk',
                    collapsed && 'justify-center px-0'
                )}
            >
                <item.icon className={cn('h-4 w-4 shrink-0', active ? 'text-gold' : 'opacity-70')} aria-hidden="true" />
                {collapsed ? (
                    <span className="sr-only">{item.label}</span>
                ) : (
                    <span className="truncate">{item.label}</span>
                )}
                {!collapsed && item.badge === 'inbox' && count > 0 && (
                    <span data-testid="sidebar-inbox-badge" className="ml-auto font-mono text-[11px] tabular-nums text-gold">
                        {count > 99 ? '99+' : count}
                    </span>
                )}
                {!collapsed && item.badge === 'trust' && count > 0 && (
                    <span data-testid="sidebar-trust-badge" className="ml-auto font-mono text-[11px] tabular-nums text-gold">
                        {count > 99 ? '99+' : count}
                    </span>
                )}
            </Link>
        )
    }

    const groupLabelClass = 'font-mono text-[10.5px] font-medium uppercase tracking-[0.18em] text-[#8C9791]'

    return (
        <nav
            aria-label="Admin"
            className={cn(
                'dark min-h-screen shrink-0 border-r border-hairline-dark bg-night text-chalk transition-[width] duration-200 ease-in-out flex flex-col',
                collapsed ? 'w-16' : 'w-[260px]',
                className
            )}
            data-state={collapsed ? 'collapsed' : 'expanded'}
        >
            <div className={cn('flex flex-1 flex-col gap-5 px-[18px] py-6', collapsed && 'px-2')}>
                <Link
                    to="/admin/dashboard"
                    onClick={handleNavigate}
                    className={cn('flex items-center gap-3 px-2 no-underline hover:no-underline', collapsed && 'justify-center px-0')}
                >
                    <img src={BRAND_LOGO_SRC} alt="The Academy Watch logo" className="h-8 w-8 shrink-0 rounded-lg" />
                    {!collapsed && (
                        <span className="font-mono text-[11px] uppercase tracking-[0.2em] text-gold">Control room</span>
                    )}
                </Link>

                {groups.map((group) => {
                    if (collapsed) {
                        return (
                            <div key={group.label} className="flex flex-col gap-0.5 border-t border-hairline-dark pt-3 first-of-type:border-t-0">
                                {group.items.map(renderItem)}
                            </div>
                        )
                    }

                    if (!group.collapsible) {
                        return (
                            <div key={group.label} className="flex flex-col gap-0.5">
                                <span className={cn(groupLabelClass, 'px-2.5 pb-1.5')}>{group.label}</span>
                                {group.items.map(renderItem)}
                            </div>
                        )
                    }

                    const open = isOpen(group)
                    return (
                        <Collapsible
                            key={group.label}
                            open={open}
                            onOpenChange={() => toggleGroup(group)}
                            className="mt-auto border-t border-hairline-dark pt-3"
                        >
                            <CollapsibleTrigger asChild>
                                <button
                                    type="button"
                                    className="flex w-full items-center justify-between rounded-[7px] px-2.5 py-2 text-left text-[13px] text-[#8C9791] transition-colors hover:text-chalk"
                                >
                                    <span>{group.label}</span>
                                    <ChevronDown className={cn('h-3.5 w-3.5 transition-transform duration-200', open && 'rotate-180')} aria-hidden="true" />
                                </button>
                            </CollapsibleTrigger>
                            <CollapsibleContent>
                                <div className="flex flex-col gap-0.5 pt-1">
                                    {group.items.map(renderItem)}
                                </div>
                            </CollapsibleContent>
                        </Collapsible>
                    )
                })}

                <div
                    className={cn(
                        'flex gap-1 border-t border-hairline-dark pt-3',
                        collapsed ? 'flex-col items-center' : 'items-center justify-between'
                    )}
                    role="group"
                    aria-label="Account"
                >
                    <Link
                        to="/"
                        onClick={handleNavigate}
                        title={collapsed ? 'Public site' : undefined}
                        className={cn(
                            'flex h-[34px] items-center gap-2.5 rounded-[7px] px-2.5 text-sm text-muted-dark no-underline transition-colors hover:bg-chalk/[0.04] hover:text-chalk hover:no-underline',
                            collapsed && 'justify-center px-0'
                        )}
                    >
                        <Home className="h-4 w-4 opacity-70" aria-hidden="true" />
                        {collapsed ? <span className="sr-only">Public site</span> : <span>Public site</span>}
                    </Link>
                    <Button
                        variant="ghost"
                        className={cn(
                            'h-[34px] gap-2.5 rounded-[7px] px-2.5 text-sm font-normal text-[#E9967A] hover:bg-[#E9967A]/10 hover:text-[#E9967A]',
                            collapsed && 'justify-center px-0'
                        )}
                        onClick={() => {
                            if (onNavigate) onNavigate()
                            logout()
                        }}
                    >
                        <LogOut className="h-4 w-4" aria-hidden="true" />
                        {collapsed ? <span className="sr-only">Log out</span> : <span>Log out</span>}
                    </Button>
                </div>
            </div>
        </nav>
    )
}
