import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { APIService } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useAuth, useAuthUI } from '@/context/AuthContext'
import { usePublicationFlag } from '@/hooks/usePublicationFlag'

function status(row) {
  if (row.club_revoked) return 'Club association revoked · private'
  if (row.withdrawn) return 'Consent withdrawn · private'
  if (row.public) return 'Public with your consent'
  if (row.moderation_status === 'rejected') return 'Not approved · private'
  if (!row.claimed) return 'Waiting for the player · private'
  if (!row.consented) return 'Waiting for public consent · private'
  return 'Waiting for moderation · private'
}

export function PlayerPublications({ mode = 'player' }) {
  const { programId } = useParams()
  const { token: authToken } = useAuth()
  const { openLoginModal } = useAuthUI()
  const enabled = usePublicationFlag()
  const [rows, setRows] = useState([])
  const [players, setPlayers] = useState([])
  const [selected, setSelected] = useState('')
  const [email, setEmail] = useState('')
  const [shareLink, setShareLink] = useState('')
  const [checked, setChecked] = useState({})
  const [reason, setReason] = useState({})
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  // The capability belongs in the fragment, never in a path, query or analytics event.
  const [token] = useState(() => mode === 'invite' ? new URLSearchParams(window.location.hash.slice(1)).get('token') : null)
  useEffect(() => {
    if (mode === 'invite') window.history.replaceState(null, '', window.location.pathname)
  }, [mode])

  async function load() {
    setLoading(true)
    try {
      if (mode === 'invite') {
        const result = await APIService.request('/me/player-publication-invites/preview', { method: 'POST', body: JSON.stringify({ token }) })
        setRows([result.publication])
      } else {
        const path = mode === 'club' ? `/club/${programId}/player-publications` : mode === 'admin' ? '/admin/player-publications' : '/me/player-publications'
        const result = await APIService.request(path, {}, { admin: mode === 'admin' })
        setRows(result.publications || [])
        if (mode === 'club') {
          const candidates = await APIService.request(`/club/${programId}/publication-candidates`)
          setPlayers(candidates.players || [])
        }
      }
    } catch (err) { setError(err?.body?.error || err.message || 'Profiles could not be loaded.') }
    finally { setLoading(false) }
  }
  useEffect(() => { if (enabled && authToken) load() }, [enabled, authToken, mode, programId]) // eslint-disable-line react-hooks/exhaustive-deps

  async function act(row, action) {
    setBusy(true); setError('')
    try {
      const path = mode === 'invite' ? '/me/player-publication-invites/accept' : mode === 'admin' ? `/admin/player-publications/${row.id}/review` : mode === 'club' ? `/club/${programId}/player-publications/${row.id}/revoke` : `/me/player-publications/${row.id}/${action}`
      const result = await APIService.request(path, { method: 'POST', body: JSON.stringify({ expected_version: row.version, public_profile_consent: checked[row.id] === true, consent_version: row.consent_version, token, self_claim: checked[row.id] === true, action, reason: reason[row.id] }) }, { admin: mode === 'admin' })
      if (mode === 'invite') window.location.assign('/player-publications')
      else setRows(current => mode === 'admin' ? current.filter(r => r.id !== row.id) : current.map(r => r.id === row.id ? result.publication : r))
      setChecked(current => ({ ...current, [row.id]: false }))
    } catch (err) { setError(err?.body?.error || err.message || 'Nothing changed. Try again.') }
    finally { setBusy(false) }
  }
  async function invite(event) {
    event.preventDefault(); setBusy(true); setError(''); setShareLink('')
    try {
      const existing = rows.find(r => r.local_player_id === Number(selected))
      const result = await APIService.request(`/club/${programId}/players/${selected}/publication-invite`, { method: 'POST', body: JSON.stringify({ recipient_email: email, expected_version: existing?.version }) })
      setShareLink(`${window.location.origin}/player-publication-invite#token=${result.token}`)
      await load()
    } catch (err) { setError(err?.body?.error || err.message || 'Invite could not be created.') }
    finally { setBusy(false) }
  }
  if (enabled === null) return <p className="floodlight-container py-12">Loading…</p>
  if (!enabled) return <div className="floodlight-container py-12"><p>Page unavailable.</p><Link to="/">Home</Link></div>
  if (!authToken) return <main className="floodlight-container mx-auto max-w-4xl py-12"><h1 className="display text-5xl">Your private invitation</h1><p className="my-6 text-muted-foreground">Sign in with the email the club invited. Claiming this profile does not make it public.</p><Button onClick={openLoginModal}>Sign in to review</Button></main>
  return <main className="floodlight-container mx-auto max-w-4xl py-12 text-foreground">
    <p className="eyebrow text-gold-text dark:text-gold">{mode === 'club' ? 'Club Home' : mode === 'admin' ? 'Control room' : 'Your choice'}</p>
    <h1 className="display mt-4 text-5xl">{mode === 'club' ? 'Invite an adult player' : mode === 'admin' ? 'Review public profiles' : mode === 'invite' ? 'Your private profile' : 'Your public profile'}</h1>
    <p className="mt-5 max-w-2xl text-muted-foreground">Club profiles stay private until the adult player claims their identity, gives public consent, and a moderator approves. Introductions go to the club first. Either side can take back its permission.</p>
    {error && <p role="alert" className="mt-6 rounded-lg border border-danger p-4 text-danger">{error}<Button variant="ghost" onClick={load}>Refresh</Button></p>}
    {mode === 'club' && <form onSubmit={invite} className="my-8 space-y-4 border-y border-border py-6">
      <label className="block">Adult player<select required className="mt-2 block min-h-11 w-full rounded-lg border border-border bg-background p-3" value={selected} onChange={e => setSelected(e.target.value)}><option value="">Choose a player</option>{players.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
      <label className="block">Player’s email<Input required type="email" value={email} onChange={e => setEmail(e.target.value)} /></label>
      <p className="text-sm text-muted-foreground">Only known adults appear here. Creating an invite confirms their club association. Share the private link with that player; they must sign in with this email. It expires in seven days.</p>
      <Button disabled={busy || !selected}>Create private invite</Button>
      {shareLink && <label className="block text-sm">Private invite link<Input readOnly value={shareLink} onFocus={e => e.target.select()} /></label>}
    </form>}
    {loading ? <p className="mt-8" role="status">Loading profiles…</p> : rows.length === 0 ? <p className="mt-8 border-t border-border py-6 text-muted-foreground">No profiles waiting here.</p> : <div className="mt-8">{rows.map(row => <section key={row.id} className="space-y-4 border-t border-border py-6">
      <h2 className="font-serif text-3xl">{row.player_name || 'Profile unavailable'}</h2><p className="eyebrow text-muted-foreground">{status(row)}</p>
      {mode === 'invite' && <><label className="flex items-start gap-3"><input className="mt-1 size-5" type="checkbox" checked={checked[row.id] || false} onChange={e => setChecked({ ...checked, [row.id]: e.target.checked })} />I am this adult player and I claim this profile. This does not make my profile public.</label><Button disabled={busy || !checked[row.id]} onClick={() => act(row, 'accept')}>Claim my private profile</Button></>}
      {mode === 'player' && !row.club_revoked && !row.public && !row.consented && <><label className="flex items-start gap-3"><input className="mt-1 size-5 shrink-0" type="checkbox" checked={checked[row.id] || false} onChange={e => setChecked({ ...checked, [row.id]: e.target.checked })} />{row.consent_text}</label><Button disabled={busy || !checked[row.id]} onClick={() => act(row, 'consent')}>Give public profile consent</Button></>}
      {mode === 'player' && row.consented && !row.withdrawn && <Button variant="outline" disabled={busy} onClick={() => act(row, 'withdraw')}>Withdraw public consent</Button>}
      {mode === 'club' && !row.club_revoked && <Button variant="outline" disabled={busy} onClick={() => act(row, 'revoke')}>Revoke club association</Button>}
      {mode === 'admin' && <><label className="block">Review reason<Input maxLength={2000} value={reason[row.id] || ''} onChange={e => setReason({ ...reason, [row.id]: e.target.value })} /></label><div className="flex flex-wrap gap-3"><Button disabled={busy || !row.claimed || !row.consented || !reason[row.id]?.trim()} onClick={() => act(row, 'approve')}>Approve profile and self-claim</Button><Button variant="outline" disabled={busy || !reason[row.id]?.trim()} onClick={() => act(row, 'reject')}>Keep private</Button></div></>}
      {row.public && <Link className="inline-block underline" to={`/local-players/${row.local_player_id}`}>View public profile</Link>}
    </section>)}</div>}
  </main>
}
