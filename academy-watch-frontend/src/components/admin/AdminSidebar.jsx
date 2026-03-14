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
    MessageSquarePlus,
    GraduationCap,
    Settings2,
    FlaskConical,
    ChevronDown,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from '@/components/ui/collapsible'
import { useAuthUI } from '@/context/AuthContext'

const GROUPS_KEY = 'academy_watch_admin_sidebar_groups'

const sidebarGroups = [
    {
        label: null,
        items: [
            { icon: LayoutDashboard, label: 'Dashboard', href: '/admin/dashboard' },
        ],
    },
    {
        label: 'Academy Data',
        icon: GraduationCap,
        items: [
            { icon: Users, label: 'Players', href: '/admin/players' },
            { icon: Shield, label: 'Teams', href: '/admin/teams' },
            { icon: GraduationCap, label: 'Academy', href: '/admin/academy' },
            { icon: Users, label: 'Cohorts', href: '/admin/cohorts' },
        ],
    },
    {
        label: 'Content',
        icon: Mail,
        items: [
            { icon: Mail, label: 'Newsletters', href: '/admin/newsletters' },
            { icon: MessageSquarePlus, label: 'Curation', href: '/admin/curation' },
            { icon: Megaphone, label: 'Sponsors', href: '/admin/sponsors' },
        ],
    },
    {
        label: 'System',
        icon: Settings,
        items: [
            { icon: Settings2, label: 'Tools', href: '/admin/tools' },
            { icon: FlaskConical, label: 'Sandbox', href: '/admin/sandbox' },
            { icon: Users, label: 'Users', href: '/admin/users' },
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

    useEffect(() => {
        saveGroupState(groupOpen)
    }, [groupOpen])

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
