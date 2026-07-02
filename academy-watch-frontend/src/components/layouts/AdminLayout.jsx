
import { useEffect, useRef, useState } from 'react'
import { Outlet } from 'react-router-dom'
import { Navigate } from 'react-router-dom'
import { AlertCircle, KeyRound, Menu, PanelLeftClose, PanelLeftOpen } from 'lucide-react'

import { AdminSidebar } from '@/components/admin/AdminSidebar'
import { SyncOverlay } from '@/components/admin/SyncOverlay'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { useAuth } from '@/context/AuthContext'
import { BackgroundJobsProvider } from '@/context/BackgroundJobsContext'
import { APIService } from '@/lib/api'

const SIDEBAR_COLLAPSE_KEY = 'academy_watch_admin_sidebar_collapsed'

export function AdminLayout() {
    const { token, isAdmin, hasApiKey } = useAuth()
    const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)
    const [collapsed, setCollapsed] = useState(() => {
        if (typeof localStorage === 'undefined') return false
        return localStorage.getItem(SIDEBAR_COLLAPSE_KEY) === 'true'
    })
    // Bootstrap state for the inline "Enter admin API key" screen. Lives in
    // the layout (not a child) so the error survives the hasApiKey flip that
    // APIService.setAdminKey triggers before validation completes.
    const [keyInput, setKeyInput] = useState('')
    const [validatingKey, setValidatingKey] = useState(false)
    const [keyError, setKeyError] = useState(null)
    // A stored key that the server rejects should not silently 403 every admin
    // page — surface the key-entry screen (below) instead. Tracks the last key
    // value we verified so we validate a given key only once per session.
    const [keyRejected, setKeyRejected] = useState(false)
    const validatedKeyRef = useRef(null)

    useEffect(() => {
        if (typeof localStorage === 'undefined') return
        localStorage.setItem(SIDEBAR_COLLAPSE_KEY, collapsed ? 'true' : 'false')
    }, [collapsed])

    // Verify the stored admin key when entering the admin section. Presence of a
    // key is not proof it is correct, so without this a stale/wrong key would let
    // every page load and then 403 with no affordance to replace it. Only an
    // explicit 401/403 flags the key invalid; transient/5xx failures are ignored
    // so a backend blip never locks an admin out.
    useEffect(() => {
        if (!token || !isAdmin || !hasApiKey) return
        const currentKey = APIService.adminKey
        if (!currentKey || validatedKeyRef.current === currentKey) return
        let cancelled = false
        const verify = async () => {
            try {
                await APIService.validateAdminCredentials()
                if (cancelled) return
                validatedKeyRef.current = currentKey
                setKeyRejected(false)
            } catch (error) {
                if (cancelled) return
                if (error?.status === 401 || error?.status === 403) {
                    validatedKeyRef.current = currentKey
                    const baseError = error?.body?.error || error?.message || 'Access denied'
                    setKeyError(`Stored admin key was rejected: ${baseError}. Paste a valid key to continue.`)
                    setKeyRejected(true)
                }
            }
        }
        verify()
        return () => {
            cancelled = true
        }
    }, [token, isAdmin, hasApiKey])

    useEffect(() => {
        const closeOnResize = () => {
            if (window.innerWidth >= 1024) {
                setMobileSidebarOpen(false)
            }
        }
        window.addEventListener('resize', closeOnResize)
        return () => window.removeEventListener('resize', closeOnResize)
    }, [])

    // Only non-admins get redirected home. An admin without a stored API key
    // gets an inline key-entry screen instead (the key lives in localStorage
    // via APIService.setAdminKey — the same mechanism Settings uses).
    if (!token || !isAdmin) {
        return <Navigate to="/" replace />
    }

    const submitKey = async (event) => {
        event.preventDefault()
        const trimmed = (keyInput || '').trim()
        if (!trimmed || validatingKey) return
        setValidatingKey(true)
        setKeyError(null)
        // Same mechanism as AdminSettings.saveKey: store the key (persists to
        // localStorage + emits the auth-changed event), validate it against
        // the backend, and clear it again if the server rejects it.
        APIService.setAdminKey(trimmed)
        try {
            await APIService.validateAdminCredentials()
            setKeyInput('')
            setKeyError(null)
            setKeyRejected(false)
            validatedKeyRef.current = trimmed
        } catch (error) {
            APIService.setAdminKey('')
            validatedKeyRef.current = null
            const baseError = error?.body?.error || error?.message || 'Key rejected by server'
            const detail = error?.body?.detail || ''
            setKeyError(`Admin key not accepted: ${baseError}${detail ? ` — ${detail}` : ''}`)
        } finally {
            setValidatingKey(false)
        }
    }

    if (!hasApiKey || validatingKey || keyRejected) {
        return (
            <div className="min-h-screen bg-secondary flex items-center justify-center p-4">
                <Card className="w-full max-w-md" data-testid="admin-api-key-bootstrap">
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <KeyRound className="h-5 w-5 text-primary" />
                            Enter admin API key
                        </CardTitle>
                        <CardDescription>
                            {keyRejected
                                ? 'The admin API key stored on this device was rejected by the server. Paste a current key to continue — it is kept in local storage and only sent with admin requests.'
                                : 'You are signed in as an admin, but no admin API key is stored on this device. It is kept in local storage and only sent with admin requests.'}
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <form className="space-y-3" onSubmit={submitKey}>
                            {keyError && (
                                <Alert className="border-rose-500 bg-rose-50">
                                    <AlertCircle className="h-4 w-4 text-rose-600" />
                                    <AlertDescription className="text-rose-800">{keyError}</AlertDescription>
                                </Alert>
                            )}
                            <div className="space-y-2">
                                <Label htmlFor="admin-bootstrap-key-input">Admin API key</Label>
                                <Input
                                    id="admin-bootstrap-key-input"
                                    data-testid="admin-api-key-input"
                                    type="password"
                                    value={keyInput}
                                    onChange={(e) => setKeyInput(e.target.value)}
                                    placeholder="Paste the admin API key"
                                    autoComplete="off"
                                    autoFocus
                                />
                            </div>
                            <Button
                                type="submit"
                                className="w-full"
                                disabled={validatingKey || !keyInput.trim()}
                                data-testid="admin-api-key-save"
                            >
                                {validatingKey ? 'Validating…' : 'Save key & continue'}
                            </Button>
                        </form>
                    </CardContent>
                </Card>
            </div>
        )
    }

    return (
        <BackgroundJobsProvider>
            <div className="flex min-h-screen bg-secondary">
                <AdminSidebar
                    collapsed={collapsed}
                    className="hidden lg:flex"
                />

                <Sheet open={mobileSidebarOpen} onOpenChange={setMobileSidebarOpen}>
                    <SheetContent
                        side="left"
                        className="p-0 w-72 sm:w-80 lg:hidden"
                        data-testid="admin-sidebar-sheet"
                    >
                        <SheetHeader className="sr-only">
                            <SheetTitle>Admin menu</SheetTitle>
                        </SheetHeader>
                        <AdminSidebar onNavigate={() => setMobileSidebarOpen(false)} />
                    </SheetContent>
                </Sheet>

                <div className="flex-1 min-w-0 flex flex-col">
                    <header className="sticky top-0 z-20 h-16 border-b bg-card/90 backdrop-blur flex items-center px-4 sm:px-6 justify-between gap-4">
                        <div className="flex items-center gap-3 min-w-0">
                            <Button
                                data-testid="admin-menu-toggle"
                                className="md:hidden"
                                variant="ghost"
                                size="icon"
                                aria-label="Open admin menu"
                                onClick={() => setMobileSidebarOpen(true)}
                            >
                                <Menu className="h-5 w-5" />
                            </Button>
                            <Button
                                data-testid="admin-collapse-toggle"
                                className="hidden lg:inline-flex"
                                variant="ghost"
                                size="icon"
                                aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
                                onClick={() => setCollapsed((prev) => !prev)}
                            >
                                {collapsed ? <PanelLeftOpen className="h-5 w-5" /> : <PanelLeftClose className="h-5 w-5" />}
                            </Button>
                            <div className="min-w-0">
                                <h1 className="text-lg sm:text-xl font-semibold text-foreground truncate">Admin Dashboard</h1>
                                <p className="text-xs text-muted-foreground hidden sm:block">Control center for journalists, loans, and newsletters</p>
                            </div>
                        </div>
                        <div className="flex items-center gap-4 text-sm text-muted-foreground">
                            <span className="hidden sm:inline">Logged in as Admin</span>
                        </div>
                    </header>
                    <div className="relative flex-1">
                        <SyncOverlay />
                        <main className="p-4 sm:p-6">
                            <Outlet />
                        </main>
                    </div>
                </div>
            </div>
        </BackgroundJobsProvider>
    )
}
