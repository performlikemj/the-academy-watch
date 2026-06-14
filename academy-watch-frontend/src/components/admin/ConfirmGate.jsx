import { useState } from 'react'
import { AlertTriangle } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

/**
 * ConfirmGate — shared confirmation dialog for destructive / money / quota
 * admin actions. Public contract (other admin pages import this):
 *
 *   <ConfirmGate
 *     open onOpenChange
 *     title="Run Full Rebuild"
 *     description="This DELETES all tracked players…"
 *     confirmWord="REBUILD"     // user must type this exactly (optional)
 *     confirmLabel="Run it"
 *     destructive               // red styling
 *     onConfirm={() => …}
 *   />
 */
export function ConfirmGate({
    open,
    onOpenChange,
    title,
    description,
    confirmWord,
    confirmLabel = 'Confirm',
    destructive = false,
    onConfirm,
}) {
    const [typed, setTyped] = useState('')

    const needsWord = Boolean(confirmWord)
    const wordMatches = !needsWord || typed === confirmWord

    // Reset the typed word whenever the dialog closes so a previously-typed
    // confirmation never carries over to the next open.
    const handleOpenChange = (next) => {
        if (!next) setTyped('')
        onOpenChange?.(next)
    }

    const handleConfirm = () => {
        if (!wordMatches) return
        try {
            onConfirm?.()
        } finally {
            handleOpenChange(false)
        }
    }

    return (
        <Dialog open={open} onOpenChange={handleOpenChange}>
            <DialogContent data-testid="confirm-gate" className="sm:max-w-md">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        {destructive && <AlertTriangle className="h-5 w-5 text-destructive" />}
                        {title}
                    </DialogTitle>
                    {description && (
                        <DialogDescription className="whitespace-pre-line">
                            {description}
                        </DialogDescription>
                    )}
                </DialogHeader>

                {needsWord && (
                    <div className="space-y-2">
                        <Label htmlFor="confirm-gate-input" className="text-sm">
                            Type <code className="font-mono font-semibold">{confirmWord}</code> to confirm
                        </Label>
                        <Input
                            id="confirm-gate-input"
                            data-testid="confirm-gate-input"
                            value={typed}
                            onChange={(e) => setTyped(e.target.value)}
                            placeholder={confirmWord}
                            autoComplete="off"
                            autoFocus
                            onKeyDown={(e) => {
                                if (e.key === 'Enter' && wordMatches) {
                                    e.preventDefault()
                                    handleConfirm()
                                }
                            }}
                        />
                    </div>
                )}

                <DialogFooter className="gap-2">
                    <Button
                        type="button"
                        variant="outline"
                        data-testid="confirm-gate-cancel"
                        onClick={() => onOpenChange?.(false)}
                    >
                        Cancel
                    </Button>
                    <Button
                        type="button"
                        variant={destructive ? 'destructive' : 'default'}
                        data-testid="confirm-gate-confirm"
                        disabled={!wordMatches}
                        onClick={handleConfirm}
                    >
                        {confirmLabel}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}

export default ConfirmGate
