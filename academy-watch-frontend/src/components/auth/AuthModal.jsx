import { useState, useEffect } from 'react'
import { useAuth, useAuthUI } from '@/context/AuthContext'
import { APIService } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
    DialogFooter,
} from '@/components/ui/dialog'
import { Loader2, LogOut, AlertCircle, CheckCircle } from 'lucide-react'

export function AuthModal() {
    const { isLoginModalOpen, closeLoginModal, logout } = useAuthUI()
    const auth = useAuth()
    const [email, setEmail] = useState('')
    const [code, setCode] = useState('')
    const [requestSent, setRequestSent] = useState(false)
    const [busy, setBusy] = useState(false)
    const [status, setStatus] = useState(null)
    const [displayNameInput, setDisplayNameInput] = useState(auth.displayName || '')
    const [displayNameBusy, setDisplayNameBusy] = useState(false)
    const [displayNameStatus, setDisplayNameStatus] = useState(null)

    useEffect(() => {
        if (!isLoginModalOpen) {
            setEmail('')
            setCode('')
            setRequestSent(false)
            setStatus(null)
            setDisplayNameStatus(null)
        }
    }, [isLoginModalOpen])

    useEffect(() => {
        setDisplayNameInput(auth.displayName || '')
    }, [auth.displayName, auth.token])

    const handleRequest = async (event) => {
        event.preventDefault()
        const trimmed = (email || '').trim().toLowerCase()
        if (!trimmed) {
            setStatus({ type: 'error', message: 'Enter the email you use for The Academy Watch.' })
            return
        }
        setBusy(true)
        try {
            await APIService.requestLoginCode(trimmed)
            setStatus({ type: 'success', message: 'Code sent! Check your email within five minutes.' })
            setRequestSent(true)
        } catch (error) {
            setStatus({ type: 'error', message: error?.body?.error || error.message || 'Failed to send login code.' })
        } finally {
            setBusy(false)
        }
    }

    const handleVerify = async (event) => {
        event.preventDefault()
        const trimmedEmail = (email || '').trim().toLowerCase()
        const trimmedCode = (code || '').trim()
        if (!trimmedEmail || !trimmedCode) {
            setStatus({ type: 'error', message: 'Enter both email and code to continue.' })
            return
        }
        setBusy(true)
        try {
            const result = await APIService.verifyLoginCode(trimmedEmail, trimmedCode)
            const confirmed = !!result?.display_name_confirmed
            setStatus({ type: 'success', message: confirmed ? 'Signed in! Welcome back.' : 'Signed in! Pick a display name to finish.' })
            setRequestSent(false)
            setCode('')
            if (!confirmed) {
                setDisplayNameInput(result?.display_name || auth.displayName || '')
                setDisplayNameStatus(null)
            } else {
                setTimeout(() => {
                    closeLoginModal()
                }, 700)
            }
        } catch (error) {
            setStatus({ type: 'error', message: error?.body?.error || error.message || 'Verification failed. Try again.' })
        } finally {
            setBusy(false)
        }
    }

    const handleDisplayNameSave = async (event) => {
        event.preventDefault()
        const trimmed = (displayNameInput || '').trim()
        if (trimmed.length < 3) {
            setDisplayNameStatus({ type: 'error', message: 'Display name must be at least 3 characters.' })
            return
        }
        setDisplayNameBusy(true)
        try {
            await APIService.updateDisplayName(trimmed)
            await APIService.refreshProfile().catch(() => { })
            setDisplayNameStatus({ type: 'success', message: 'Display name updated.' })
        } catch (error) {
            setDisplayNameStatus({ type: 'error', message: error?.body?.error || error.message || 'Failed to update display name.' })
        } finally {
            setDisplayNameBusy(false)
        }
    }

    return (
        <Dialog open={isLoginModalOpen} onOpenChange={(open) => { if (!open) closeLoginModal() }}>
            <DialogContent className="max-w-[calc(100vw-2rem)] sm:max-w-md">
                <DialogHeader>
                    <DialogTitle className="text-lg">{auth.token ? 'Account' : 'Sign in to The Academy Watch'}</DialogTitle>
                    <DialogDescription className="text-sm">
                        {auth.token
                            ? 'Update your display name or sign out of your session.'
                            : 'We\u2019ll email you a one-time code to finish signing in.'}
                    </DialogDescription>
                </DialogHeader>

                {auth.token ? (
                    <div className="space-y-5">
                        <div className="rounded-lg border bg-muted/40 p-4 text-sm">
                            <div className="font-medium text-foreground">Signed in as {auth.displayName || 'GOL supporter'}</div>
                            {auth.isAdmin && (
                                <div className="text-sm text-muted-foreground mt-1">
                                    Admin access: {auth.hasApiKey ? 'ready' : 'missing API key'}
                                </div>
                            )}
                        </div>
                        <form className="space-y-4" onSubmit={handleDisplayNameSave}>
                            <div className="space-y-2">
                                <Label htmlFor="display-name" className="text-sm font-medium">Display name</Label>
                                <Input
                                    id="display-name"
                                    className="h-11"
                                    value={displayNameInput}
                                    onChange={(e) => setDisplayNameInput(e.target.value)}
                                    maxLength={40}
                                    placeholder="Your public name"
                                    autoComplete="nickname"
                                    autoCapitalize="words"
                                />
                            </div>
                            {displayNameStatus && (
                                <p className={`text-sm ${displayNameStatus.type === 'error' ? 'text-red-600' : 'text-emerald-600'}`}>
                                    {displayNameStatus.message}
                                </p>
                            )}
                            <div className="flex items-center gap-3">
                                <Button type="submit" disabled={displayNameBusy} className="h-11 px-6">
                                    {displayNameBusy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Save
                                </Button>
                                <Button variant="ghost" type="button" className="h-11" onClick={() => setDisplayNameInput(auth.displayName || '')}>
                                    Reset
                                </Button>
                            </div>
                        </form>
                    </div>
                ) : (
                    <div className="space-y-5">
                        <form className="space-y-4" onSubmit={handleRequest}>
                            <div className="space-y-2">
                                <Label htmlFor="login-email" className="text-sm font-medium">Email</Label>
                                <Input
                                    id="login-email"
                                    className="h-12 text-base"
                                    type="email"
                                    autoComplete="email"
                                    inputMode="email"
                                    spellCheck="false"
                                    autoCapitalize="none"
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    placeholder="you@example.com"
                                    required
                                />
                            </div>
                            <Button type="submit" disabled={busy} className="h-12 w-full text-base">
                                {busy && !requestSent ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                                Send login code
                            </Button>
                        </form>

                        {requestSent && (
                            <form className="space-y-4" onSubmit={handleVerify}>
                                <div className="space-y-2">
                                    <Label htmlFor="login-code" className="text-sm font-medium">Verification code</Label>
                                    <Input
                                        id="login-code"
                                        className="h-12 text-base tracking-wide font-mono"
                                        value={code}
                                        onChange={(e) => setCode(e.target.value)}
                                        placeholder="Enter the 11-character code"
                                        autoComplete="one-time-code"
                                        inputMode="text"
                                        spellCheck="false"
                                        autoCapitalize="none"
                                        autoCorrect="off"
                                    />
                                </div>
                                <Button type="submit" disabled={busy} className="h-12 w-full text-base">
                                    {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                                    Verify & sign in
                                </Button>
                            </form>
                        )}

                        {status && (
                            <Alert className={`border ${status.type === 'error' ? 'border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/50 dark:text-red-400' : 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-400'}`}>
                                {status.type === 'error' ? <AlertCircle className="h-4 w-4" /> : <CheckCircle className="h-4 w-4" />}
                                <AlertDescription className="text-sm">{status.message}</AlertDescription>
                            </Alert>
                        )}
                    </div>
                )}

                <DialogFooter className="flex-col-reverse gap-2 sm:flex-row sm:justify-between">
                    {auth.token ? (
                        <Button variant="ghost" className="h-11 w-full sm:w-auto" onClick={() => { logout(); closeLoginModal() }}>
                            <LogOut className="mr-2 h-4 w-4" /> Log out
                        </Button>
                    ) : requestSent ? (
                        <Button variant="ghost" className="h-11 w-full sm:w-auto" onClick={() => { setRequestSent(false); setCode(''); setStatus(null) }}>
                            Back
                        </Button>
                    ) : <span className="hidden sm:block" />}
                    <Button variant="outline" className="h-11 w-full sm:w-auto" onClick={closeLoginModal}>Close</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}
