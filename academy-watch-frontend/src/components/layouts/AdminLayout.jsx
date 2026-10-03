
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
import { useNightSurface } from '@/hooks/useNightSurface'
import { APIService } from '@/lib/api'

const SIDEBAR_COLLAPSE_KEY = 'academy_watch_admin_sidebar_collapsed'

export function AdminLayout() {
    const { token, isAdmin, hasApiKey } = useAuth()
    useNightSurface()
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
            <div className="flex min-h-screen items-center justify-center bg-night px-4 py-16">
                <Card className="w-full max-w-md gap-5 px-2 py-8" data-testid="admin-api-key-bootstrap">
                    <CardHeader>
                        <p className="eyebrow flex items-center gap-2">
                            <KeyRound className="h-3.5 w-3.5" aria-hidden="true" />
                            Control room
                        </p>
                        <CardTitle className="text-4xl">
                            Enter admin API key
                        </CardTitle>
                        <CardDescription className="leading-relaxed">
                            {keyRejected
                                ? 'The admin API key stored on this device was rejected by the server. Paste a current key to continue — it is kept in local storage and only sent with admin requests.'
                                : 'You are signed in as an admin, but no admin API key is stored on this device. It is kept in local storage and only sent with admin requests.'}
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <form className="space-y-4" onSubmit={submitKey}>
                            {keyError && (
                                <Alert className="border-rose-500 bg-rose-50">
                                    <AlertCircle className="h-4 w-4 text-rose-600" />
                                    <AlertDescription className="text-rose-800">{keyError}</AlertDescription>
                                </Alert>
                            )}
                            <div className="space-y-2">
                                <Label htmlFor="admin-bootstrap-key-input" className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted-dark">Admin API key</Label>
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
            <div className="flex min-h-screen bg-night text-chalk">
                <AdminSidebar
                    collapsed={collapsed}
                    className="sticky top-0 hidden h-screen self-start overflow-y-auto overscroll-contain lg:flex"
                />

                <Sheet open={mobileSidebarOpen} onOpenChange={setMobileSidebarOpen}>
                    <SheetContent
                        side="left"
                        className="h-dvh w-72 overflow-y-auto overscroll-contain border-hairline-dark bg-night p-0 sm:w-80 lg:hidden"
                        data-testid="admin-sidebar-sheet"
                    >
                        <SheetHeader className="sr-only">
                            <SheetTitle>Admin menu</SheetTitle>
                        </SheetHeader>
                        <AdminSidebar onNavigate={() => setMobileSidebarOpen(false)} className="min-h-full w-full shrink-0 border-r-0" />
                    </SheetContent>
                </Sheet>

                <div className="flex min-w-0 flex-1 flex-col">
                    <header className="sticky top-0 z-20 flex h-14 items-center justify-between gap-4 border-b border-hairline-dark bg-night/90 px-4 backdrop-blur sm:px-8 lg:px-14">
                        <div className="flex min-w-0 items-center gap-3">
                            <Button
                                data-testid="admin-menu-toggle"
                                className="lg:hidden"
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
                            <p className="truncate text-sm text-muted-dark">
                                <span className="sr-only">Admin Dashboard · </span>
                                Control room
                            </p>
                        </div>
                        <span className="hidden text-[13px] text-muted-dark sm:inline">Signed in as admin</span>
                    </header>
                    <div className="relative flex-1">
                        <SyncOverlay />
                        <main className="fl-admin-main px-4 pb-28 pt-8 sm:px-8 lg:px-14 lg:pt-11">
                            <Outlet />
                        </main>
                    </div>
                </div>
            </div>
        </BackgroundJobsProvider>
    )
}
