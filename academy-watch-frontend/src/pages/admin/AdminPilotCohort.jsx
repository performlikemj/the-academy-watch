import { useRef, useState } from 'react'
import { APIService } from '@/lib/api'
import { track } from '@/lib/track'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

const FAILURE = 'The report could not be generated. Your register has not been saved.'
const label = value => value.replaceAll('_', ' ')

function download(value, filename) {
    const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }))
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export default function AdminPilotCohort() {
    const [register, setRegister] = useState(null)
    const [report, setReport] = useState(null)
    const [error, setError] = useState('')
    const [loading, setLoading] = useState(false)
    const uploadVersion = useRef(0)

    async function upload(event) {
        const version = ++uploadVersion.current
        const file = event.target.files?.[0]
        setRegister(null)
        setReport(null)
        setError('')
        if (!file) return
        if (file.size > 256 * 1024) {
            setError('Choose a JSON register smaller than 256 KiB.')
            return
        }
        try {
            const parsed = JSON.parse(await file.text())
            if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object' || parsed.schema_version !== 1 || !Array.isArray(parsed.participants)) {
                throw new Error('invalid_register')
            }
            if (version === uploadVersion.current) setRegister(parsed)
        } catch {
            if (version === uploadVersion.current) setError('Choose a valid schema version 1 JSON register.')
        }
    }

    async function generate() {
        setLoading(true)
        setError('')
        setReport(null)
        track('pilot_ui', { package: 'P1', action: 'report_requested', outcome: 'requested' })
        try {
            const data = await APIService.request('/admin/pilot-cohort/report', {
                method: 'POST', body: JSON.stringify(register), cache: 'no-store',
            }, { admin: true })
            setReport(data)
            track('pilot_ui', { package: 'P1', action: 'report_completed', outcome: 'success' })
        } catch (err) {
            const denied = err.status === 401 || err.status === 403
            const invalid = [400, 413, 422].includes(err.status)
            setError(denied ? 'Admin access required.' : invalid
                ? `Check the register, observation references, and UTC window. ${FAILURE}` : FAILURE)
            track('pilot_ui', { package: 'P1', action: 'report_failed', outcome: denied ? 'denied' : invalid ? 'invalid' : 'error' })
        } finally {
            setLoading(false)
        }
    }

    return (
        <Card className="min-w-0 border-t-4 border-t-primary" aria-labelledby="pilot-title">
            <CardHeader>
                <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">Pilot / declared cohort</p>
                <CardTitle id="pilot-title" className="text-2xl">People, actions, and continuation</CardTitle>
                <CardDescription>Upload the register declared before the pilot.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
                <div className="space-y-3">
                    <label htmlFor="pilot-register" className="block text-sm font-medium">Declared register (JSON, up to 256 KiB)</label>
                    <input id="pilot-register" type="file" accept=".json,application/json" onChange={upload} disabled={loading}
                        className="block w-full min-w-0 rounded border p-3 text-sm file:mr-3 file:rounded file:border-0 file:bg-muted file:px-3 file:py-2" />
                    <div className="flex flex-wrap gap-2">
                        <Button disabled={!register || loading} onClick={generate}>Generate report</Button>
                        <Button variant="outline" disabled={!register || loading} onClick={() => download(register, 'pilot-register.json')}>Download register</Button>
                        {report ? <Button variant="outline" onClick={() => download(report, 'pilot-report.json')}>Download report</Button> : null}
                    </div>
                </div>
                <div aria-live="polite" aria-atomic="true">
                    {loading ? <p role="status">Checking registered actions…</p> : null}
                    {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
                </div>
                {report ? (
                    <div className="space-y-6">
                        {!report.capabilities.relationships || !report.capabilities.feedback ? (
                            <p className="rounded border border-amber-500/40 bg-amber-500/10 p-3 text-sm">Relationship/feedback evidence is not available yet. Missing capabilities are evidence gaps, not zero adoption.</p>
                        ) : null}
                        {!report.capabilities.stable_results ? <p className="text-sm text-muted-foreground">Stable result evidence is not available yet.</p> : null}
                        <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
                            {[
                                ['Qualifying people', report.summary.qualifying_people],
                                ['Later-week use', report.summary.repeat_people],
                                ['Cross-person outcomes', report.cross_person_outcomes.length],
                                ['Paid continuation', label(report.continuation.decision)],
                            ].map(([title, value]) => <div key={title} className="border-l-2 border-primary pl-4">
                                <dt className="text-sm text-muted-foreground">{title}</dt>
                                <dd className="mt-1 break-words text-2xl font-semibold tabular-nums">{value}</dd>
                            </div>)}
                        </dl>
                        <p className="text-sm">Later-week target: {report.summary.repeat_target_met ? 'met' : 'not met'} ({report.summary.repeat_staff} staff, {report.summary.repeat_players} players). At least seven days after the first qualifying action.</p>
                        <p className="text-sm">{Object.entries(report.summary.by_role).map(([role, count]) => `${label(role)}: ${count}`).join(' · ')}</p>
                        <div className="rounded bg-muted/40 p-3 text-xs">
                            <p>Register SHA-256</p><p className="mt-1 break-all font-mono">{report.register_sha256}</p>
                            <p className="mt-2">Generated {report.generated_at}</p>
                        </div>
                        <ul className="divide-y rounded border">
                            {report.participants.map(person => <li key={person.person_key} className="min-w-0 space-y-2 p-4 text-sm">
                                <p className="break-all font-semibold">{person.person_key} · {person.primary_role} · {person.qualified ? 'Qualified' : 'Not qualified'}</p>
                                <p>Currently eligible: {person.eligible_now ? 'yes' : 'no'}</p>
                                {person.action_dates.length ? <p>Action dates: {person.action_dates.join(', ')}</p> : null}
                                {person.repeat_dates.length ? <p>Later-week dates: {person.repeat_dates.join(', ')}</p> : null}
                                {person.missing.length ? <p>Missing: {person.missing.map(label).join(', ')}</p> : null}
                                <ul className="space-y-1 text-muted-foreground">
                                    {person.evidence.map((item, i) => <li key={i} className="break-words">
                                        {label(item.kind)} · {item.record_type} #{item.record_id} · {item.occurred_at}
                                        {item.basis === 'operator_correlated' ? ' · Observed outside the app' : ' · Database evidence'}
                                    </li>)}
                                </ul>
                            </li>)}
                        </ul>
                        {report.cross_person_outcomes.length ? <ul className="space-y-2 text-sm">
                            {report.cross_person_outcomes.map((item, i) => <li key={i} className="break-words">{label(item.stage || item.kind)} · {item.record_type} #{item.record_id} · {item.occurred_at}</li>)}
                        </ul> : null}
                        <p className="text-sm">Continuation: Observed outside the app. This is an operator declaration, not payment verification.</p>
                    </div>
                ) : null}
                <div className="space-y-2 border-t pt-4 text-sm text-muted-foreground">
                    <p>Pre-declaration and person/account reconciliation are operator-verified, not database-enforced. Freeze the register and record its SHA-256 and declaration time before counting. Revoked or deleted prerequisites can reduce later counts.</p>
                    <p><code>track.js</code> sends no Authorization header, and <code>profile_view</code> removes identity even if supplied. Named return use cannot be reconstructed from these events.</p>
                    <p className="font-medium text-foreground">This report contains account references. Store it privately.</p>
                    <p>Registers and reports stay in browser memory until you download them. They are not saved by the application.</p>
                </div>
            </CardContent>
        </Card>
    )
}
