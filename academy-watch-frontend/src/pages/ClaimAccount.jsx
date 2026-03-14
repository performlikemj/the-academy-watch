import React, { useState, useEffect } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from '@/components/ui/card'
import { Loader2, CheckCircle, XCircle, User } from 'lucide-react'
import { APIService } from '@/lib/api'

export function ClaimAccount() {
    const [searchParams] = useSearchParams()
    const navigate = useNavigate()
    const token = searchParams.get('token')

    // Status: 'validating' | 'valid' | 'invalid' | 'claiming' | 'success'
    const [status, setStatus] = useState('validating')
    const [accountInfo, setAccountInfo] = useState(null)
    const [error, setError] = useState(null)

    useEffect(() => {
        if (token) {
            validateToken()
        } else {
            setStatus('invalid')
            setError('No claim token provided')
        }
    }, [token])

    const validateToken = async () => {
        try {
            setStatus('validating')
            const result = await APIService.validateClaimToken(token)
            setAccountInfo(result)
            setStatus('valid')
        } catch (err) {
            setError(err.message || 'Invalid or expired token')
            setStatus('invalid')
        }
    }

    const handleClaim = async () => {
        try {
            setStatus('claiming')
            const result = await APIService.completeAccountClaim(token)

            // Store the auth token
            APIService.setUserToken(result.token, {
                isAdmin: false,
                isJournalist: true,
                displayName: result.user?.display_name
            })

            setStatus('success')

            // Redirect to writer dashboard after a short delay
            setTimeout(() => {
                navigate('/writer/dashboard')
            }, 2000)
        } catch (err) {
            setError(err.message || 'Failed to claim account')
            setStatus('invalid')
        }
    }

    // Validating state
    if (status === 'validating') {
        return (
            <div className="min-h-screen flex items-center justify-center bg-background p-4">
                <Card className="w-full max-w-md">
                    <CardContent className="pt-6">
                        <div className="flex flex-col items-center gap-4">
                            <Loader2 className="h-12 w-12 animate-spin text-primary" />
                            <p className="text-lg text-muted-foreground">Validating your claim link...</p>
                        </div>
                    </CardContent>
                </Card>
            </div>
        )
    }

    // Invalid/Error state
    if (status === 'invalid') {
        return (
            <div className="min-h-screen flex items-center justify-center bg-background p-4">
                <Card className="w-full max-w-md">
                    <CardHeader>
                        <div className="flex items-center gap-3">
                            <XCircle className="h-8 w-8 text-rose-500" />
                            <CardTitle className="text-rose-700">Unable to Claim Account</CardTitle>
                        </div>
                    </CardHeader>
                    <CardContent>
                        <p className="text-muted-foreground">
                            {error || 'This claim link is invalid or has expired.'}
                        </p>
                        <p className="text-sm text-muted-foreground mt-4">
                            If you believe this is an error, please contact the person who invited you to request a new claim link.
                        </p>
                    </CardContent>
                    <CardFooter>
                        <Button variant="outline" onClick={() => navigate('/')}>
                            Return to Home
                        </Button>
                    </CardFooter>
                </Card>
            </div>
        )
    }

    // Success state
    if (status === 'success') {
        return (
            <div className="min-h-screen flex items-center justify-center bg-background p-4">
                <Card className="w-full max-w-md">
                    <CardHeader>
                        <div className="flex items-center gap-3">
                            <CheckCircle className="h-8 w-8 text-emerald-500" />
                            <CardTitle className="text-emerald-700">Account Claimed!</CardTitle>
                        </div>
                    </CardHeader>
                    <CardContent>
                        <p className="text-muted-foreground">
                            Welcome to The Academy Watch! Your writer account is now active.
                        </p>
                        <p className="text-sm text-muted-foreground mt-4">
                            Redirecting you to your writer dashboard...
                        </p>
                    </CardContent>
                </Card>
            </div>
        )
    }

    // Valid - ready to claim
    return (
        <div className="min-h-screen flex items-center justify-center bg-background p-4">
            <Card className="w-full max-w-md">
                <CardHeader>
                    <div className="flex items-center gap-3">
                        <div className="h-12 w-12 rounded-full bg-primary/10 flex items-center justify-center">
                            <User className="h-6 w-6 text-primary" />
                        </div>
                        <div>
                            <CardTitle>Claim Your Account</CardTitle>
                            <CardDescription>The Academy Watch Writer Account</CardDescription>
                        </div>
                    </div>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="p-4 bg-secondary rounded-lg space-y-2">
                        <div className="flex justify-between text-sm">
                            <span className="text-muted-foreground">Name:</span>
                            <span className="font-medium">{accountInfo?.display_name}</span>
                        </div>
                        <div className="flex justify-between text-sm">
                            <span className="text-muted-foreground">Email:</span>
                            <span className="font-medium">{accountInfo?.email}</span>
                        </div>
                        {accountInfo?.attribution_name && (
                            <div className="flex justify-between text-sm">
                                <span className="text-muted-foreground">Publication:</span>
                                <span className="font-medium">{accountInfo.attribution_name}</span>
                            </div>
                        )}
                    </div>

                    <p className="text-sm text-muted-foreground">
                        Click below to claim this account and start writing directly on The Academy Watch.
                        You'll be able to create and manage your own content.
                    </p>
                </CardContent>
                <CardFooter className="flex gap-3">
                    <Button variant="outline" onClick={() => navigate('/')}>
                        Cancel
                    </Button>
                    <Button
                        className="flex-1"
                        onClick={handleClaim}
                        disabled={status === 'claiming'}
                    >
                        {status === 'claiming' ? (
                            <>
                                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                Claiming...
                            </>
                        ) : (
                            'Claim Account'
                        )}
                    </Button>
                </CardFooter>
            </Card>
        </div>
    )
}

export default ClaimAccount
