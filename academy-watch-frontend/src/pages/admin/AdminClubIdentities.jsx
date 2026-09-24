import { useCallback, useEffect, useState } from 'react';
import { APIService } from '@/lib/api';

export function AdminClubIdentities() {
  const [program, setProgram] = useState('');
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [target, setTarget] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try {
      setData(await APIService.request(`/admin/club-identities?limit=100&offset=${offset}${program ? `&program_id=${encodeURIComponent(program)}` : ''}`, {}, { admin: true }));
      setError('');
    } catch (err) { setError(err.message); }
  }, [program, offset]);
  useEffect(() => { load(); }, [load]);
  async function suppress(event) {
    event.preventDefault(); setBusy(true); setError('');
    const form = new FormData(event.currentTarget);
    try {
      // Use the existing intake and suppression lifecycle, including its audit trail.
      await APIService.request(`/local-players/${target.id}/takedown-request`, { method: 'POST', body: JSON.stringify({ requester_role: 'club', contact_email: form.get('email'), statement: form.get('notes') }) });
      let found;
      for (let page = 0; ; page += 200) {
        const queue = await APIService.request(`/admin/suppressions?status=requested&limit=200&offset=${page}`, {}, { admin: true });
        found = queue.suppressions.find(row => row.local_player_id === target.id);
        if (found || page + queue.suppressions.length >= queue.total) break;
      }
      if (!found) throw new Error('No pending takedown found. Refresh the safeguarding view.');
      await APIService.request(`/admin/suppressions/${found.id}/activate`, { method: 'POST', body: JSON.stringify({ notes: form.get('notes') }) }, { admin: true });
      setTarget(null); await load();
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  }
  return <div className="space-y-6 p-6">
    <div><h1 className="text-2xl font-bold">Club identities</h1><p className="text-sm text-muted-foreground">Private club-created players · safeguarding review</p></div>
    <label className="flex items-center gap-3">Filter by program ID<input type="number" min="1" value={program} onChange={e => { setProgram(e.target.value); setOffset(0); }} className="rounded border p-2" placeholder="All programs" /></label>
    {error && <p role="alert" className="text-red-700">{error}</p>}
    {target && <form onSubmit={suppress} className="space-y-3 rounded-xl border p-5"><h2 className="font-bold">Suppress {target.display_name}</h2><p className="text-sm">This activates the existing player takedown process and removes access to this identity.</p><label className="block">Review contact email<input className="block w-full rounded border p-2" name="email" type="email" required /></label><label className="block">Safeguarding decision<textarea name="notes" required maxLength="2000" className="block w-full rounded border p-2" /></label><button disabled={busy} className="rounded bg-red-800 px-4 py-2 text-white">Confirm suppression</button><button type="button" disabled={busy} className="ml-3" onClick={() => setTarget(null)}>Cancel</button></form>}
    <div className="overflow-x-auto rounded-xl border bg-card"><table className="w-full text-left text-sm"><thead><tr className="border-b bg-muted">{['Player', 'Origin program', 'Created by / at', 'Age', 'Roster memberships', 'Safeguarding'].map(h => <th key={h} className="p-4">{h}</th>)}</tr></thead><tbody>{data?.players.map(row => <tr key={row.id} className="border-b"><td className="p-4 font-semibold">{row.display_name}<span className="block text-xs font-normal">Local #{row.id}</span></td><td className="p-4">{row.program_name || 'No origin recorded'} {row.origin_program_id && `(#${row.origin_program_id})`}</td><td className="p-4">{row.created_by ? `User #${row.created_by}` : 'Former user'}<span className="block text-xs">{row.created_at && new Date(row.created_at).toLocaleDateString()}</span></td><td className="p-4">{row.is_minor ? 'Minor / age unconfirmed' : 'Adult'}</td><td className="p-4">{row.memberships.map(m => <div key={m.member_id}>{m.program_name} · Member #{m.member_id}</div>)}</td><td className="p-4">{row.suppressed ? 'Suppressed' : <button className="font-semibold text-red-800 underline" onClick={() => setTarget(row)}>Suppress identity</button>}</td></tr>)}</tbody></table>{data && !data.players.length && <p className="p-6">No club identities match this filter.</p>}</div>
    {data && <div className="flex items-center gap-4"><button disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 100))}>Previous</button><span>{data.total} identities</span><button disabled={offset + data.players.length >= data.total} onClick={() => setOffset(offset + 100)}>Next</button></div>}
  </div>;
}
