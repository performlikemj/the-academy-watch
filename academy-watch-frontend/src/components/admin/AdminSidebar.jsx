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
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from '@/components/ui/collapsible'
import { useAuthUI } from '@/context/AuthContext'
import { fetchInboxCounts } from '@/pages/admin/AdminInbox'

const GROUPS_KEY = 'academy_watch_admin_sidebar_groups'

const sidebarGroups = [
    {
        label: null,
        items: [
            { icon: LayoutDashboard, label: 'Dashboard', href: '/admin/dashboard' },
            { icon: Inbox, label: 'Inbox', href: '/admin/inbox', badge: 'inbox' },
        ],
    },
    {
        label: 'Academy Data',
        icon: GraduationCap,
        items: [
            { icon: Users, label: 'Players', href: '/admin/players' },
            { icon: Shield, label: 'Teams', href: '/admin/teams' },
            { icon: Trophy, label: 'Youth Leagues', href: '/admin/academy' },
            { icon: GraduationCap, label: 'Cohorts', href: '/admin/cohorts' },
            { icon: Sprout, label: 'Seeding & Rebuild', href: '/admin/seeding' },
        ],
    },
    {
        label: 'Content',
        icon: Mail,
        items: [
            { icon: Mail, label: 'Newsletters', href: '/admin/newsletters' },
            { icon: Megaphone, label: 'Sponsors', href: '/admin/sponsors' },
        ],
    },
    {
        label: 'People',
        icon: UserCog,
        items: [
            { icon: UserCog, label: 'Users & Writers', href: '/admin/users' },
        ],
    },
    {
        label: 'Club Services',
        icon: Video,
        items: [
            { icon: Video, label: 'Film Room', href: '/admin/video' },
        ],
    },
    {
        label: 'System',
        icon: Settings,
        items: [
            { icon: Wrench, label: 'Operations', href: '/admin/operations' },
            { icon: Settings2, label: 'API & Configs', href: '/admin/tools' },
            { icon: FlaskConical, label: 'Classifier Tester', href: '/admin/sandbox' },
            { icon: Settings, label: 'Settings', href: '/admin/settings' },
        ],
    },
]

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
    const location = useLocation()
    const { logout } = useAuthUI()
    const [groupOpen, setGroupOpen] = useState(() => loadGroupState())
    const [inboxCount, setInboxCount] = useState(0)

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

    const handleNavigate = () => {
        if (onNavigate) onNavigate()
    }

    const isGroupActive = (group) =>
        group.items.some((item) => location.pathname === item.href)

    const isOpen = (group) => {
        if (!group.label) return true
        if (groupOpen[group.label] !== undefined) return groupOpen[group.label]
        return isGroupActive(group)
    }

    const toggleGroup = (label) => {
        setGroupOpen((prev) => ({ ...prev, [label]: !isOpen({ label, items: [] }) }))
    }

    const renderItem = (item) => (
        <Link key={item.href} to={item.href}>
            <Button
                variant={location.pathname === item.href ? 'secondary' : 'ghost'}
                className={cn(
                    'w-full justify-start gap-3',
                    collapsed && 'justify-center px-2'
                )}
                aria-current={location.pathname === item.href ? 'page' : undefined}
                onClick={handleNavigate}
            >
                <item.icon className="h-4 w-4 shrink-0" />
                {!collapsed && <span className="truncate">{item.label}</span>}
                {!collapsed && item.badge === 'inbox' && inboxCount > 0 && (
                    <span
                        data-testid="sidebar-inbox-badge"
                        className="ml-auto inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1.5 text-[11px] font-bold tabular-nums text-primary-foreground"
                    >
                        {inboxCount > 99 ? '99+' : inboxCount}
                    </span>
                )}
            </Button>
        </Link>
    )

    return (
        <div
            className={cn(
                'pb-10 min-h-screen bg-card border-r shadow-sm transition-[width] duration-200 ease-in-out flex flex-col',
                collapsed ? 'w-16' : 'w-64',
                className
            )}
            data-state={collapsed ? 'collapsed' : 'expanded'}
        >
            <div className="space-y-1 py-4 flex-1 flex flex-col">
                <div className={cn('px-3 py-2', collapsed && 'px-2')}>
                    {/* Logo */}
                    <div
                        className={cn(
                            'flex items-center gap-3 px-3 mb-6 transition-opacity',
                            collapsed ? 'justify-center' : 'justify-start'
                        )}
                    >
                        <div className="h-9 w-9 rounded-lg bg-primary flex items-center justify-center">
                            <GraduationCap className="h-5 w-5 text-primary-foreground" />
                        </div>
                        {!collapsed && (
                            <h2 className="text-lg font-bold tracking-tight">The Academy Watch</h2>
                        )}
                    </div>

                    {/* Groups */}
                    <div className="space-y-1">
                        {sidebarGroups.map((group, gi) => {
                            if (!group.label) {
                                return (
                                    <div key={gi}>
                                        {group.items.map(renderItem)}
                                    </div>
                                )
                            }

                            if (collapsed) {
                                return (
                                    <div key={gi} className="space-y-1">
                                        {gi > 0 && <hr className="my-2 border-border" />}
                                        {group.items.map(renderItem)}
                                    </div>
                                )
                            }

                            const open = isOpen(group)
                            return (
                                <Collapsible key={gi} open={open} onOpenChange={() => toggleGroup(group.label)}>
                                    <CollapsibleTrigger asChild>
                                        <button className="flex items-center justify-between w-full px-3 py-2 mt-3 text-xs font-semibold tracking-tight text-muted-foreground uppercase hover:text-foreground transition-colors">
                                            <span>{group.label}</span>
                                            <ChevronDown
                                                className={cn(
                                                    'h-3.5 w-3.5 transition-transform',
                                                    open && 'rotate-180'
                                                )}
                                            />
                                        </button>
                                    </CollapsibleTrigger>
                                    <CollapsibleContent>
                                        <div className="space-y-1">
                                            {group.items.map(renderItem)}
                                        </div>
                                    </CollapsibleContent>
                                </Collapsible>
                            )
                        })}
                    </div>
                </div>

                {/* Bottom section */}
                <div className={cn('px-3 py-2 mt-auto', collapsed && 'px-2')}>
                    {!collapsed && (
                        <h2 className="mb-2 px-3 text-sm font-semibold tracking-tight text-muted-foreground">
                            Account
                        </h2>
                    )}
                    <div className="space-y-1">
                        <Link to="/">
                            <Button
                                variant="ghost"
                                className={cn(
                                    'w-full justify-start gap-3',
                                    collapsed && 'justify-center px-2'
                                )}
                                onClick={onNavigate}
                            >
                                <Home className="h-4 w-4" />
                                {!collapsed && <span>Public Site</span>}
                            </Button>
                        </Link>
                        <Button
                            variant="ghost"
                            className={cn(
                                'w-full justify-start gap-3 text-rose-600 hover:text-rose-600 hover:bg-rose-50',
                                collapsed && 'justify-center px-2'
                            )}
                            onClick={() => {
                                if (onNavigate) onNavigate()
                                logout()
                            }}
                        >
                            <LogOut className="h-4 w-4" />
                            {!collapsed && <span>Logout</span>}
                        </Button>
                    </div>
                </div>
            </div>
        </div>
    )
}
