import { useState } from 'react'
import { APIService } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

export function AccountAccess({ token }) {
    const [confirmation, setConfirmation] = useState('')
    const [message, setMessage] = useState('')
    const [busy, setBusy] = useState(false)
    async function act(kind) {
        setBusy(true)
        try {
            const result = await APIService.request(kind === 'portal' ? '/billing/portal' : `/account/${kind}`, { method: kind === 'export' ? 'GET' : 'POST', ...(kind === 'delete' ? { body: JSON.stringify({ confirm: confirmation }) } : {}) }, { accountAccess: token })
            if (kind === 'portal') globalThis.location.assign(result.portal_url)
            else if (kind === 'export') {
                const url = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' }))
                const link = document.createElement('a'); link.href = url; link.download = 'academy-watch-account.json'; link.click(); URL.revokeObjectURL(url)
                setMessage('Your account export has been downloaded.')
            } else setMessage('Your account has been deleted.')
        } catch (error) { setMessage(error.message || 'Please try again.') }
        finally { setBusy(false) }
    }
    return <section aria-label="Account access" className="space-y-3"><p className="text-sm">You can still cancel your subscription, export your data or delete your account. This verified access expires in 15 minutes.</p><Button disabled={busy} onClick={() => act('portal')}>Manage or cancel subscription</Button><Button disabled={busy} onClick={() => act('export')}>Export my data</Button><label className="block text-sm">Type DELETE to permanently delete your account<Input value={confirmation} onChange={event => setConfirmation(event.target.value)} /></label><Button variant="destructive" disabled={busy || confirmation !== 'DELETE'} onClick={() => act('delete')}>Delete my account</Button>{message && <p role="status">{message}</p>}</section>
}
