import { canonicalTimezone, fromLocalInput, localInput } from '@/lib/opportunity-time'
import { OpportunityBoundary } from '@/pages/opportunities/OpportunityBoundary'
import { useCallback, useEffect, useRef, useState } from 'react'
import { ComingSoon } from '@/components/interest/ComingSoon'
import { APIService } from '@/lib/api'
import { errorMessage, useOpportunities, when, write } from '@/pages/opportunities/useOpportunities'
import '@/pages/opportunities/opportunities.css'

const STAGES = [['new', 'New'], ['shortlisted', 'Shortlisted'], ['invited', 'Invited'], ['attended', 'Attended'], ['offer', 'Offer']]
const TITLE = { shortlisted: 'Shortlist', invited: 'Invite to trial', attended: 'Record attendance', offer: 'Make offer', rejected: 'Not selected', signed: 'Record signed' }
const LOCKED = new Set(['title', 'description', 'instructions', 'capacity', 'type', 'squad_id', 'birth_year_min', 'birth_year_max', 'gender_program', 'position_requirements', 'starts_at', 'ends_at', 'timezone', 'venue', 'address', 'closes_at'])
const FIELDS = [['title', 'Title', 'text', true], ['description', 'About this opportunity', 'textarea', true], ['instructions', 'What to bring', 'textarea'], ['position_requirements', 'Positions / eligibility', 'text'], ['venue', 'Venue', 'text', true], ['address', 'Address', 'text'], ['timezone', 'Time zone (for example Europe/London)', 'text', true], ['birth_year_min', 'Earliest birth year', 'number'], ['birth_year_max', 'Latest birth year', 'number'], ['capacity', 'Trial capacity (optional)', 'number'], ['starts_at', 'Starts (your local time)', 'datetime-local'], ['ends_at', 'Ends (your local time)', 'datetime-local'], ['closes_at', 'Applications close (your local time)', 'datetime-local', true]]

function OpportunityEditor({ programId, squads, item, onClose, onSaved }) {
  const ref = useRef(null)
  const [values, setValues] = useState(() => ({ type: 'trial', status: 'draft', gender_program: 'all', timezone: canonicalTimezone(Intl.DateTimeFormat().resolvedOptions().timeZone), position_requirements: 'All positions', ...item, ...Object.fromEntries(['starts_at', 'ends_at', 'closes_at'].map(key => [key, localInput(item?.[key], item?.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone)])) }))
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const locked = Boolean(item?.application_count)
  useEffect(() => { ref.current.showModal() }, [])
  async function save(event) {
    event.preventDefault(); setBusy(true); setError('')
    try {
    const data = { status: values.status, type: values.type, gender_program: values.gender_program, squad_id: values.squad_id ? Number(values.squad_id) : null }
    for (const [key, , type] of FIELDS) {
      if (locked && LOCKED.has(key)) continue
      const value = values[key] || ''
      data[key] = type === 'number' ? value ? Number(value) : null : type === 'datetime-local' ? value ? fromLocalInput(value, values.timezone) : null : value
    }
    if (item) data.expected_version = item.version
    if (locked) for (const key of LOCKED) delete data[key]
    await write(`/club/${programId}/opportunities${item ? `/${item.id}` : ''}`, data, item ? 'PATCH' : 'POST'); onSaved(); onClose() }
    catch (err) { setError(errorMessage(err)) }
    finally { setBusy(false) }
  }
  return <dialog ref={ref} onCancel={onClose} aria-labelledby="opportunity-editor-title"><div className="flex items-start justify-between gap-5"><h2 id="opportunity-editor-title" className="opp-section">{item ? 'Edit opportunity' : 'New opportunity'}</h2><button type="button" className="opp-button" onClick={onClose} aria-label="Close editor">Close</button></div>
    <form onSubmit={save} className="mt-6 grid gap-5">
      <label className="opp-field">Opportunity type<select aria-label="Opportunity type" disabled={locked} value={values.type} onChange={e => setValues({ ...values, type: e.target.value })}><option value="trial">Trial</option><option value="open_session">Open session</option><option value="position">Position</option></select></label>
      <label className="opp-field">Squad<select aria-label="Squad" disabled={locked} value={values.squad_id || ''} onChange={e => setValues({ ...values, squad_id: e.target.value })}><option value="">Whole club</option>{squads.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
      <label className="opp-field">Programme<select aria-label="Programme" disabled={locked} value={values.gender_program} onChange={e => setValues({ ...values, gender_program: e.target.value })}>{['all', 'boys', 'girls', 'men', 'women', 'mixed'].map(v => <option key={v} value={v}>{v}</option>)}</select></label>
      {FIELDS.map(([key, label, type, required]) => <label key={key} className="opp-field">{type === 'datetime-local' ? `${label.replace(' (your local time)', '')} (${values.timezone})` : label}{type === 'textarea' ? <textarea disabled={locked && LOCKED.has(key)} maxLength={key === 'description' ? 6000 : 3000} required={required} value={values[key] || ''} onChange={e => setValues({ ...values, [key]: e.target.value })} /> : <input disabled={locked && LOCKED.has(key)} type={type} required={required || (key === 'starts_at' && values.type !== 'position')} min={type === 'number' ? key === 'capacity' ? 1 : 1900 : undefined} maxLength={key === 'title' ? 180 : 300} value={values[key] ?? ''} onChange={e => setValues({ ...values, [key]: e.target.value })} />}</label>)}
      {locked && <p className="text-sm text-muted">Advertised details and capacity are fixed once applications arrive. Trial changes use the applicant invitation.</p>}
      <label className="opp-field">Publication<select aria-label="Publication" value={values.status} onChange={e => setValues({ ...values, status: e.target.value })}>{item?.status !== 'published' && <option value="draft">Draft</option>}<option value="published">Published</option></select></label>
      {error && <p role="alert" className="opp-error">{error}</p>}<button disabled={busy} className="opp-button primary">{busy ? 'Saving…' : 'Save opportunity'}</button>
    </form>
  </dialog>
}

function Candidate({ row, programId, onChanged }) {
  const [open, setOpen] = useState(false)
  const [detail, setDetail] = useState(null)
  const [invite, setInvite] = useState(false)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [trial, setTrial] = useState({ trial_at: localInput(row.trial_at, row.timezone), trial_venue: row.trial_venue || '', trial_instructions: row.trial_instructions || '' })
  const [signed, setSigned] = useState(false)
  async function act(status, extra = {}) {
    setBusy(true); setError('')
    try { await write(`/club/${programId}/applications/${row.id}/transition`, { expected_version: row.version, status, ...extra }); setInvite(false); await onChanged() }
    catch (err) { setError(errorMessage(err)); if ([403, 404, 409].includes(err.status)) await onChanged() }
    finally { setBusy(false) }
  }
  async function addNote(event) {
    event.preventDefault(); setBusy(true); setError('')
    try { await write(`/club/${programId}/applications/${row.id}/notes`, { body: note }); setNote(''); const data = await APIService.request(`/club/${programId}/applications/${row.id}`); setDetail(data.application); await onChanged() }
    catch (err) { setError(errorMessage(err)); if ([403, 404, 409].includes(err.status)) await onChanged() }
    finally { setBusy(false) }
  }
  return <article className="opp-candidate">
    <button className="text-left font-medium underline-offset-4 hover:underline" onClick={async () => {
      setOpen(!open)
      if (!open) { try { const data = await APIService.request(`/club/${programId}/applications/${row.id}`); setDetail(data.application) } catch (err) { setError(errorMessage(err)); await onChanged() } }
    }} aria-expanded={open}>{row.applicant_name}</button><p className="text-xs text-muted">{row.position}{row.current_club ? ` · ${row.current_club}` : ''}</p><p className="opp-label">Adult self-claim</p>
    {row.trial_at && <p className="text-xs text-muted">{when(row.trial_at, row.timezone)} · {row.reservation_state}</p>}
    {row.transitions?.filter(v => v !== 'rejected').map(status => status === 'invited' ? <button key={status} disabled={busy || !row.profile_available} className="opp-button" onClick={() => setInvite(!invite)}>Invite to trial →</button> : status === 'signed' ? <div key={status}><label className="flex gap-2 text-xs"><input type="checkbox" checked={signed} onChange={e => setSigned(e.target.checked)} />Adult enrollment completed separately</label><button className="opp-button mt-3" disabled={busy || !signed || !row.profile_available} onClick={() => act('signed', { enrollment_confirmed: true })}>Record signed</button></div> : <button key={status} className="opp-button" disabled={busy || !row.profile_available || (status === 'attended' && (row.reservation_state !== 'confirmed' || new Date(row.trial_at) > new Date()))} onClick={() => act(status)}>{TITLE[status]} →</button>)}
    {row.status === 'invited' && <button className="opp-button" disabled={busy || !row.profile_available} onClick={() => setInvite(!invite)}>Reschedule trial</button>}
    {invite && <form className="grid gap-4" onSubmit={event => { event.preventDefault(); try { act('invited', { ...trial, trial_at: fromLocalInput(trial.trial_at, row.timezone) }) } catch (err) { setError(errorMessage(err)) } }}>
      <label className="opp-field">Trial ({row.timezone})<input type="datetime-local" required value={trial.trial_at} onChange={e => setTrial({ ...trial, trial_at: e.target.value })} /></label>
      <label className="opp-field">Trial venue<input required maxLength={200} value={trial.trial_venue} onChange={e => setTrial({ ...trial, trial_venue: e.target.value })} /></label>
      <label className="opp-field">Instructions<textarea maxLength={3000} value={trial.trial_instructions} onChange={e => setTrial({ ...trial, trial_instructions: e.target.value })} /></label>
      <button disabled={busy} className="opp-button primary">Send trial invitation</button>
    </form>}
    {open && <div className="grid gap-4 border-t border-hairline pt-4">
      {row.transitions?.includes('rejected') && <button disabled={busy} className="opp-button" onClick={() => act('rejected')}>Not selected</button>}
      <p className="opp-label">Club-private notes</p>{detail?.notes?.map(n => <p key={n.id} className="whitespace-pre-wrap text-sm">{n.body}</p>)}
      <form className="grid gap-3" onSubmit={addNote}><label className="opp-field">Private note<textarea required maxLength={3000} value={note} onChange={e => setNote(e.target.value)} /></label><button disabled={busy} className="opp-button">Add note</button></form>
      <p className="opp-label">History</p>{detail?.events?.map(e => <p className="text-xs text-muted" key={e.version}>{when(e.created_at, row.timezone)} · {e.reason_code.replaceAll('_', ' ')}</p>)}
    </div>}
    {error && <p className="opp-error" role="alert">{error}</p>}
  </article>
}

function RecruitingContent({ program, squads = [] }) {
  const flags = useOpportunities()
  const [opportunities, setOpportunities] = useState([])
  const [selected, setSelected] = useState(null)
  const [applications, setApplications] = useState([])
  const [appPage, setAppPage] = useState(1)
  const [appMore, setAppMore] = useState(false)
  const [opportunityPage, setOpportunityPage] = useState(1)
  const [opportunityMore, setOpportunityMore] = useState(false)
  const [editor, setEditor] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const load = useCallback(async () => {
    try { const data = await APIService.request(`/club/${program.id}/opportunities?page=${opportunityPage}`); setOpportunities(data.opportunities); setOpportunityMore(data.has_more); setSelected(current => data.opportunities.some(r => r.id === current) ? current : data.opportunities[0]?.id || null) }
    catch (err) { setError(errorMessage(err)) }
  }, [program.id, opportunityPage])
  const loadApplications = useCallback(async () => {
    if (!selected || !flags.applications) { setApplications([]); return }
    try { const data = await APIService.request(`/club/${program.id}/opportunities/${selected}/applications?page=${appPage}`); setApplications(data.applications); setAppMore(data.has_more) }
    catch (err) { setError(errorMessage(err)) }
  }, [program.id, selected, flags.applications, appPage])
  useEffect(() => { if (flags.opportunities) load() }, [flags.opportunities, load])
  useEffect(() => { setApplications([]); loadApplications() }, [loadApplications])
  const current = opportunities.find(item => item.id === selected)
  async function close(status) {
    setBusy(true); setError('')
    try { await write(`/club/${program.id}/opportunities/${current.id}/close`, { expected_version: current.version, status }); await load(); await loadApplications() }
    catch (err) { setError(errorMessage(err)) }
    finally { setBusy(false) }
  }
  if (flags.error) return <p role="alert" className="p2-opportunities py-8">{flags.error}</p>
  if (!flags.loaded) return <p role="status" className="p2-opportunities py-8">Loading opportunities…</p>
  if (!flags.opportunities) return <ComingSoon feature="recruiting" role="club" image="/media/club-match.webp" title="The next player. The right place." lede="Trials and applications will have a home here. Join the list to hear when recruiting opens." bullets={['Share the opportunities your club is ready to offer.', 'Keep applications and next steps together.', 'Build a clearer path into your squads.']} />
  return <section className="p2-opportunities" aria-label="Recruiting">
    <header className="flex flex-wrap items-end justify-between gap-6"><div><p className="opp-label">Recruiting</p><h1 className="opp-heading mt-3">{current?.title || 'Your next player.'}</h1>{current && <p className="mt-4 text-sm text-muted">{when(current.starts_at, current.timezone)} · {current.venue} · {current.status}</p>}</div><button className="opp-button primary" onClick={() => setEditor({ item: null })}>+ New opportunity</button></header>
    {error && <p className="opp-error" role="alert">{error}</p>}
    <div className="my-8 flex flex-wrap gap-5 border-b border-hairline pb-5" aria-label="Opportunities">{opportunities.map(item => <button className="text-left text-sm" aria-pressed={selected === item.id} key={item.id} onClick={() => { setSelected(item.id); setAppPage(1) }}>{item.title} <span className="opp-label">{item.application_count} · {item.status}</span></button>)}</div>
    <div className="mb-5 flex gap-3">{opportunityPage > 1 && <button className="opp-button" onClick={() => setOpportunityPage(opportunityPage - 1)}>Previous opportunities</button>}{opportunityMore && <button className="opp-button" onClick={() => setOpportunityPage(opportunityPage + 1)}>Next opportunities</button>}</div>
    {current && <div className="mb-8 flex flex-wrap gap-3">{!['closed', 'cancelled'].includes(current.status) && <><button className="opp-button" onClick={() => setEditor({ item: current })}>Edit opportunity</button><button disabled={busy} className="opp-button" onClick={() => close('closed')}>Close applications</button><button disabled={busy} className="opp-button" onClick={() => close('cancelled')}>Cancel opportunity</button></>}{current.capacity != null && <p className="self-center text-sm text-muted">{current.places_left} of {current.capacity} trial places available</p>}</div>}
    {!opportunities.length && <p className="py-8 text-muted">Create a draft opportunity, then publish when your club is ready.</p>}
    {current && flags.applications && <><div className="opp-board">{STAGES.map(([key, title]) => { const rows = applications.filter(a => a.status === key); return <section key={key}><div className="flex items-baseline justify-between gap-3 border-b border-ink pb-3"><h2 className="font-serif text-[26px]">{title}</h2><span className="opp-label">{rows.length}</span></div>{rows.length ? rows.map(row => <Candidate key={`${row.id}:${row.version}`} row={row} programId={program.id} onChanged={loadApplications} />) : <p className="py-6 text-xs text-muted">No applicants here yet.</p>}</section> })}</div><details className="mt-10 border-t border-hairline pt-5"><summary className="cursor-pointer text-sm">Decisions &amp; withdrawals ({applications.filter(a => ['signed', 'rejected', 'withdrawn'].includes(a.status)).length})</summary><div className="mt-5 grid gap-5 sm:grid-cols-2">{applications.filter(a => ['signed', 'rejected', 'withdrawn'].includes(a.status)).map(row => <div key={row.id}><p className="opp-label">{row.status_label}</p><Candidate row={row} programId={program.id} onChanged={loadApplications} /></div>)}</div></details></>}
    {current?.temporarily_unavailable_reservations > 0 && <p className="mb-6 text-sm text-muted">{current.temporarily_unavailable_reservations} {current.temporarily_unavailable_reservations === 1 ? 'place reserved — applicant temporarily unavailable' : 'places reserved — applicants temporarily unavailable'}</p>}
    {current && !flags.applications && <p className="py-8 text-muted">Adult applications are coming soon.</p>}
    <p className="mt-10 border-t border-hairline pt-5 text-sm leading-relaxed text-muted">Adults apply with approved self-claims. Applicant details stay inside Club Home and are retained for up to 180 days. Reserved places remain reserved while an applicant is temporarily unavailable. Parent and guardian applications are coming soon. Signing is recorded after a separate adult enrollment; it creates no public profile or consent.</p>
    <div className="mt-5 flex gap-3">{appPage > 1 && <button className="opp-button" onClick={() => setAppPage(appPage - 1)}>Previous applications</button>}{appMore && <button className="opp-button" onClick={() => setAppPage(appPage + 1)}>Next applications</button>}</div>
    {editor && <OpportunityEditor key={editor.item?.id || 'new'} item={editor.item} programId={program.id} squads={squads} onClose={() => setEditor(null)} onSaved={load} />}
  </section>
}

export function Recruiting(props) { return <OpportunityBoundary><RecruitingContent {...props} /></OpportunityBoundary> }
