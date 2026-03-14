import { QuickTakeForm } from '@/components/QuickTakeForm'
import { Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'

export function SubmitTake() {
    return (
        <div className="min-h-screen bg-background">
            <div className="container max-w-lg mx-auto py-8 px-4">
                <Link to="/">
                    <Button variant="ghost" className="mb-6">
                        <ArrowLeft className="h-4 w-4 mr-2" />
                        Back to Home
                    </Button>
                </Link>

                <div className="mb-8 text-center">
                    <h1 className="text-3xl font-bold tracking-tight mb-2">The Academy Watch</h1>
                    <p className="text-muted-foreground">
                        Share your thoughts on academy prospects
                    </p>
                </div>

                <QuickTakeForm />

                <div className="mt-8 text-center text-sm text-muted-foreground">
                    <p>
                        Want to see your take in our newsletter?
                        Submit your opinion and our editors will review it.
                    </p>
                </div>
            </div>
        </div>
    )
}
