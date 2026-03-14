import { useState, useEffect } from 'react'
import { useAuth, useAuthUI } from '@/context/AuthContext'
import { APIService } from '@/lib/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { KeyRound, LogIn, AlertCircle, CheckCircle2 } from 'lucide-react'

export function AdminSettings() {
    const { authToken, logout } = useAuth()
    const { openLoginModal } = useAuthUI()

    // API Key state
    const [adminKey, setAdminKey] = useState(APIService.adminKey || '')
    const [adminKeyInput, setAdminKeyInput] = useState('')
    const [showKeyValue, setShowKeyValue] = useState(false)
    const [editingKey, setEditingKey] = useState(!APIService.adminKey)
    const [validatingKey, setValidatingKey] = useState(false)
    const [initialKeyValidated, setInitialKeyValidated] = useState(false)

    // Newsletter settings state
    const [settings, setSettings] = useState({
        brave_soft_rank: true,
        brave_site_boost: true,
        brave_cup_synonyms: true,
        search_strict_range: false,
    })

    // Message state
    const [message, setMessage] = useState(null)

    const hasAdminToken = Boolean(authToken && APIService.isAdmin())
    const hasStoredKey = Boolean(adminKey)
    const adminReady = hasAdminToken && hasStoredKey

    const maskedKey = adminKey ? adminKey.slice(0, 8) + '•'.repeat(Math.max(0, adminKey.length - 12)) + adminKey.slice(-4) : ''

    // Load settings on mount
    useEffect(() => {
        const loadSettings = async () => {
            if (!adminReady) return
            try {
                const config = await APIService.getNewsletterConfig()
                if (config) {
                    setSettings(config)
                }
            } catch (error) {
                console.warn('Failed to load settings', error)
            }
        }
        loadSettings()
    }, [adminReady])

    // Verify existing key on mount
    useEffect(() => {
        if (!hasAdminToken || !adminKey || initialKeyValidated) return

        let cancelled = false
        const verifyExistingKey = async () => {
            try {
                await APIService.validateAdminCredentials()
                if (!cancelled) {
                    setMessage({ type: 'success', text: 'Admin access verified' })
                    setInitialKeyValidated(true)
                }
            } catch (error) {
                if (cancelled) return
                const baseError = error?.body?.error || error.message || 'Verification failed'
                const detail = error?.body?.detail || ''
                setMessage({
                    type: 'error',
                    text: `Stored admin key was rejected: ${baseError}${detail ? ` — ${detail}` : ''}`
                })
                setEditingKey(true)
                setInitialKeyValidated(true)
            }
        }
        verifyExistingKey()
        return () => {
            cancelled = true
        }
    }, [hasAdminToken, adminKey, initialKeyValidated])

    const saveKey = async () => {
        const trimmed = (adminKeyInput || '').trim()
        if (!trimmed) {
            clearKey()
            return
        }
        const previousKey = adminKey
        setValidatingKey(true)
        setMessage({ type: 'info', text: 'Validating admin API key…' })
        APIService.setAdminKey(trimmed)
        try {
            await APIService.validateAdminCredentials()
            setAdminKey(trimmed)
            setAdminKeyInput('')
            setEditingKey(false)
            setShowKeyValue(false)
            setMessage({ type: 'success', text: 'Admin key saved and verified' })
            setInitialKeyValidated(true)
        } catch (error) {
            APIService.setAdminKey(previousKey || '')
            setAdminKey(previousKey || '')
            setAdminKeyInput(trimmed)
            const baseError = error?.body?.error || error.message || 'Key rejected by server'
            const detail = error?.body?.detail || (error?.body?.reference ? `Reference: ${error.body.reference}` : '')
            setMessage({
                type: 'error',
                text: `Admin key not accepted: ${baseError}${detail ? ` — ${detail}` : ''}`
            })
            setEditingKey(true)
        } finally {
            setValidatingKey(false)
        }
    }

    const clearKey = () => {
        APIService.setAdminKey('')
        setAdminKey('')
        setAdminKeyInput('')
        setEditingKey(true)
        setShowKeyValue(false)
        setMessage({ type: 'success', text: 'Admin key cleared' })
        setInitialKeyValidated(false)
    }

    const startEditingKey = () => {
        setEditingKey(true)
        setAdminKeyInput(adminKey || '')
        setShowKeyValue(false)
    }

    const saveSettings = async () => {
        try {
            await APIService.adminUpdateConfig(settings)
            setMessage({ type: 'success', text: 'Settings updated successfully' })
        } catch (error) {
            console.error('Failed to update admin settings', error)
            setMessage({ type: 'error', text: 'Failed to update settings' })
        }
    }

    const triggerLogout = ({ clearAdminKey }) => {
        logout()
        if (clearAdminKey) {
            clearKey()
        }
    }

    return (
        <div className="space-y-6">
            <div>
                <h2 className="text-3xl font-bold tracking-tight">Settings</h2>
                <p className="text-muted-foreground mt-1">Manage your admin access and newsletter configuration</p>
            </div>

            {/* Message Display */}
            {message && (
                <Alert className={message.type === 'error' ? 'border-rose-500 bg-rose-50' : message.type === 'success' ? 'border-emerald-500 bg-emerald-50' : 'border-primary/20 bg-primary/5'}>
                    {message.type === 'error' ? <AlertCircle className="h-4 w-4 text-rose-600" /> : <CheckCircle2 className="h-4 w-4 text-emerald-600" />}
                    <AlertDescription className={message.type === 'error' ? 'text-rose-800' : message.type === 'success' ? 'text-emerald-800' : 'text-primary'}>
                        {message.text}
                    </AlertDescription>
                </Alert>
            )}

            {/* Admin Status Card */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <LogIn className="h-5 w-5" />
                        Admin Authentication
                    </CardTitle>
                    <CardDescription>Sign in as an admin and configure your API key</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    {/* Status Indicators */}
                    <div className="grid gap-3">
                        <div className="flex items-center gap-3 p-3 rounded-lg border bg-muted/40">
                            <div className={`h-2 w-2 rounded-full ${hasAdminToken ? 'bg-emerald-500' : 'bg-muted-foreground/50'}`} />
                            <div className="flex-1">
                                <div className="text-sm font-medium">Admin User Token</div>
                                <p className="text-xs text-muted-foreground">Sign in with an approved admin email</p>
                            </div>
                        </div>
                        <div className="flex items-center gap-3 p-3 rounded-lg border bg-muted/40">
                            <div className={`h-2 w-2 rounded-full ${hasStoredKey ? 'bg-emerald-500' : 'bg-muted-foreground/50'}`} />
                            <div className="flex-1">
                                <div className="text-sm font-medium">API Key</div>
                                <p className="text-xs text-muted-foreground">Required for admin operations</p>
                            </div>
                        </div>
                    </div>

                    {/* Action Buttons */}
                    {!adminReady && (
                        <div className="flex flex-wrap gap-2 pt-2">
                            {!hasAdminToken ? (
                                authToken ? (
                                    <Button
                                        size="sm"
                                        variant="outline"
                                        onClick={() => {
                                            triggerLogout({ clearAdminKey: true })
                                        }}
                                    >
                                        Log out
                                    </Button>
                                ) : (
                                    <Button size="sm" onClick={openLoginModal}>
                                        <LogIn className="mr-1 h-4 w-4" /> Sign in as admin
                                    </Button>
                                )
                            ) : null}
                            {hasAdminToken && !hasStoredKey && !editingKey && (
                                <Button size="sm" variant="outline" onClick={startEditingKey}>
                                    <KeyRound className="mr-1 h-4 w-4" /> Add API key
                                </Button>
                            )}
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* API Key Management */}
            {hasAdminToken && (
                <Card>
                    <CardHeader>
                        <div className="flex items-start justify-between gap-3">
                            <div>
                                <CardTitle className="flex items-center gap-2">
                                    <KeyRound className="h-5 w-5 text-primary" />
                                    API Key
                                </CardTitle>
                                <CardDescription>
                                    Stored locally; only sent when you trigger an admin action
                                </CardDescription>
                            </div>
                            {hasStoredKey && !editingKey && (
                                <Button size="sm" variant="ghost" type="button" onClick={() => setShowKeyValue(v => !v)}>
                                    {showKeyValue ? 'Hide key' : 'Reveal key'}
                                </Button>
                            )}
                        </div>
                    </CardHeader>
                    <CardContent>
                        {hasStoredKey && !editingKey ? (
                            <div className="rounded-md border bg-muted/40 p-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                                <code className="font-mono text-sm break-all">
                                    {showKeyValue ? adminKey : maskedKey}
                                </code>
                                <div className="flex flex-wrap gap-2">
                                    <Button size="sm" variant="secondary" type="button" onClick={startEditingKey}>
                                        Replace
                                    </Button>
                                    <Button size="sm" variant="ghost" type="button" onClick={clearKey}>
                                        Clear
                                    </Button>
                                </div>
                            </div>
                        ) : (
                            <form
                                className="space-y-3"
                                onSubmit={async (event) => {
                                    event.preventDefault()
                                    await saveKey()
                                }}
                            >
                                <div className="space-y-2">
                                    <Label htmlFor="admin-key-input" className="text-sm font-medium">
                                        Admin API key
                                    </Label>
                                    <Input
                                        id="admin-key-input"
                                        type={showKeyValue ? 'text' : 'password'}
                                        value={adminKeyInput}
                                        onChange={(e) => setAdminKeyInput(e.target.value)}
                                        placeholder="Paste the admin API key"
                                        autoComplete="off"
                                    />
                                </div>
                                <div className="flex flex-wrap items-center gap-2">
                                    <Button type="submit" size="sm" disabled={validatingKey}>
                                        {validatingKey ? 'Validating…' : 'Save key'}
                                    </Button>
                                    {hasStoredKey && (
                                        <Button
                                            type="button"
                                            size="sm"
                                            variant="ghost"
                                            onClick={() => {
                                                setEditingKey(false)
                                                setAdminKeyInput('')
                                                setShowKeyValue(false)
                                            }}
                                        >
                                            Cancel
                                        </Button>
                                    )}
                                </div>
                            </form>
                        )}
                    </CardContent>
                </Card>
            )}

            {/* Newsletter Settings */}
            {adminReady && (
                <Card>
                    <CardHeader>
                        <CardTitle>Newsletter Settings</CardTitle>
                        <CardDescription>Configure search and generation parameters</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <div className="space-y-3">
                            {[
                                ['brave_soft_rank', 'Soft Rank (quality-first ordering)'],
                                ['brave_site_boost', 'Site Boost (local/club sources)'],
                                ['brave_cup_synonyms', 'Cup Synonyms (EFL/FA/League)'],
                                ['search_strict_range', 'Strict Date Window (drop undated)'],
                            ].map(([k, label]) => (
                                <label key={k} className="flex items-center gap-3 p-3 rounded-lg border bg-muted/20 hover:bg-muted/40 transition-colors cursor-pointer">
                                    <input
                                        type="checkbox"
                                        checked={!!settings[k]}
                                        onChange={(e) => setSettings({ ...settings, [k]: e.target.checked })}
                                        className="h-4 w-4 rounded border-border"
                                    />
                                    <span className="text-sm font-medium">{label}</span>
                                </label>
                            ))}
                        </div>

                        <div className="pt-4 border-t">
                            <h3 className="text-sm font-medium mb-3">Newsletter Generation Preference</h3>
                            <div className="flex flex-col gap-2">
                                <label className="flex items-center gap-3 p-3 rounded-lg border bg-muted/20 hover:bg-muted/40 transition-colors cursor-pointer">
                                    <input
                                        type="radio"
                                        name="newsletter_generation_preference"
                                        checked={settings.newsletter_generation_preference !== 'always_run'}
                                        onChange={() => setSettings({ ...settings, newsletter_generation_preference: 'always_ask' })}
                                        className="h-4 w-4 border-border"
                                    />
                                    <div>
                                        <div className="text-sm font-medium">Always Ask (Default)</div>
                                        <div className="text-xs text-muted-foreground">Warn if players have pending games before generating</div>
                                    </div>
                                </label>
                                <label className="flex items-center gap-3 p-3 rounded-lg border bg-muted/20 hover:bg-muted/40 transition-colors cursor-pointer">
                                    <input
                                        type="radio"
                                        name="newsletter_generation_preference"
                                        checked={settings.newsletter_generation_preference === 'always_run'}
                                        onChange={() => setSettings({ ...settings, newsletter_generation_preference: 'always_run' })}
                                        className="h-4 w-4 border-border"
                                    />
                                    <div>
                                        <div className="text-sm font-medium">Always Run</div>
                                        <div className="text-xs text-muted-foreground">Generate immediately, ignoring pending games</div>
                                    </div>
                                </label>
                            </div>
                        </div>
                        <Button onClick={saveSettings}>Save Settings</Button>
                    </CardContent>
                </Card>
            )}

            {/* Locked State */}
            {!hasAdminToken && (
                <Card>
                    <CardContent className="pt-6">
                        <div className="rounded-lg border border-dashed bg-muted/40 p-6 text-sm text-muted-foreground space-y-3">
                            <p>Admin tools are locked. Sign in with an approved admin email and configure the API key to access settings.</p>
                        </div>
                    </CardContent>
                </Card>
            )}
        </div>
    )
}
