import React, { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Loader2, Mail, ArrowRight, CheckCircle } from 'lucide-react'
import { APIService } from '@/lib/api'
import { useAuthUI } from '@/context/AuthContext'

export function WriterLogin() {
    const navigate = useNavigate()
    const location = useLocation()
    const { syncAuth } = useAuthUI() // Assuming syncAuth is available or I need to access context directly
    // Actually useAuthUI exposes openLoginModal etc. I might need to access the raw context or just rely on the global event listener in App.jsx
    // App.jsx listens to 'auth-change' event. APIService.verifyAuthCode triggers it?
    // Let's check APIService.verifyAuthCode.

    const [email, setEmail] = useState('')
    const [code, setCode] = useState('')
    const [step, setStep] = useState('email') // email | code
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState('')

    const handleRequestCode = async (e) => {
        e.preventDefault()
        setLoading(true)
        setError('')
        try {
            await APIService.requestAuthCode(email)
            setStep('code')
        } catch (err) {
            setError(err.message || 'Failed to request code')
        } finally {
            setLoading(false)
        }
    }

    const handleVerifyCode = async (e) => {
        e.preventDefault()
        setLoading(true)
        setError('')
        try {
            const response = await APIService.verifyAuthCode(email, code)
            // The APIService usually dispatches an event or updates local storage.
            // If it returns the token/user, we might need to manually trigger update if App.jsx doesn't catch it automatically from this specific call if it's different.
            // But APIService.verifyAuthCode usually handles storage.

            // Redirect to dashboard
            navigate('/writer/dashboard')
        } catch (err) {
            setError(err.message || 'Invalid code')
        } finally {
            setLoading(false)
        }
    }

    return (
        <div className="min-h-screen flex items-center justify-center bg-background py-12 px-4 sm:px-6 lg:px-8">
            <Card className="w-full max-w-md">
                <CardHeader className="space-y-1">
                    <CardTitle className="text-2xl font-bold text-center">Writer Portal</CardTitle>
                    <CardDescription className="text-center">
                        {step === 'email'
                            ? 'Enter your email to access your writer dashboard'
                            : `Enter the code sent to ${email}`
                        }
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    {error && (
                        <div className="mb-4 p-3 text-sm text-rose-600 bg-rose-50 rounded-md border border-rose-200">
                            {error}
                        </div>
                    )}

                    {step === 'email' ? (
                        <form onSubmit={handleRequestCode} className="space-y-4">
                            <div className="space-y-2">
                                <Label htmlFor="email">Email</Label>
                                <Input
                                    id="email"
                                    type="email"
                                    placeholder="name@example.com"
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    required
                                    disabled={loading}
                                />
                            </div>
                            <Button type="submit" className="w-full" disabled={loading}>
                                {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Mail className="mr-2 h-4 w-4" />}
                                Send Login Code
                            </Button>
                        </form>
                    ) : (
                        <form onSubmit={handleVerifyCode} className="space-y-4">
                            <div className="space-y-2">
                                <Label htmlFor="code">Verification Code</Label>
                                <Input
                                    id="code"
                                    type="text"
                                    placeholder="123456"
                                    value={code}
                                    onChange={(e) => setCode(e.target.value)}
                                    required
                                    disabled={loading}
                                    className="text-center text-lg tracking-widest"
                                />
                            </div>
                            <Button type="submit" className="w-full" disabled={loading}>
                                {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <CheckCircle className="mr-2 h-4 w-4" />}
                                Verify & Login
                            </Button>
                            <Button
                                type="button"
                                variant="ghost"
                                className="w-full"
                                onClick={() => setStep('email')}
                                disabled={loading}
                            >
                                Back to Email
                            </Button>
                        </form>
                    )}
                </CardContent>
            </Card>
        </div>
    )
}
