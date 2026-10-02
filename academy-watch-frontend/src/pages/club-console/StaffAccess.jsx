import { useCallback, useEffect, useState } from 'react';
import { APIService } from '@/lib/api';
import { INVITE_ROLES, ROLE_LABELS, SCOPED_ROLES, can, scopeBody, scopeFromEntry, scopeValid, squadScopeLabel, toggleScopeSquad } from '@/lib/staff-access';
import { initials } from './presentation';
import { formatDisplayDate } from '@/lib/display-date';
import './staff-access.css';

const shortDate = value => formatDisplayDate(value, { fallback: '' });
const article = role => (/^[aeiou]/i.test(role) ? 'an ' : 'a ') + role.toLowerCase();
const ACTIVITY = {
  invite_sent: 'Invite sent',
  invite_revoked: 'Invite withdrawn',
  invite_accepted: 'Invite accepted',
  grant_changed: 'Access changed',
  grant_revoked: 'Access removed',
  owner_assigned: 'Owner confirmed',
  owner_removed: 'Owner removed',
};

// "All squads" or any subset of the club's squads (one or more). The whole selection round-trips.
function SquadScope({ id, role, scope, squads, onChange }) {
  const scoped = SCOPED_ROLES.has(role);
  const all = !scoped || scope.all;
  const listed = new Set(squads.map(s => s.id));
  const options = [...squads, ...scope.ids.filter(squadId => !listed.has(squadId)).map(squadId => ({ id: squadId, name: 'Squad no longer listed' }))];
  const missing = !all && scope.ids.length === 0;
  const hint = !scoped ? 'Club managers always see every squad.'
    : all ? 'Includes squads you add later.'
      : options.length === 0 ? 'This club has no squads yet. Choose All squads.'
        : missing ? 'Choose at least one squad.'
          : `${scope.ids.length} of ${options.length} ${options.length === 1 ? 'squad' : 'squads'} selected.`;
  return <fieldset id={id} className="sa-scope" aria-describedby={`${id}-hint`}>
    <legend>Squads</legend>
    <div className="sa-chips">
      <label className="sa-chip"><input type="checkbox" checked={all} disabled={!scoped} onChange={e => onChange({ ...scope, all: e.target.checked })} /><span>All squads</span></label>
      {!all && options.map(s => <label className="sa-chip" key={s.id}><input type="checkbox" checked={scope.ids.includes(s.id)} onChange={() => onChange(toggleScopeSquad(scope, s.id))} /><span>{s.name}</span></label>)}
    </div>
    <p id={`${id}-hint`} className={`sa-scope-hint${missing ? ' warn' : ''}`}>{hint}</p>
  </fieldset>;
}

export function StaffAccess({ programId, squads, access, onAccessDenied }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [noticeWarn, setNoticeWarn] = useState(false);
  const [busy, setBusy] = useState(false);
  const [picked, setPicked] = useState(null);
  const [form, setForm] = useState({ email: '', role: 'coach', scope: { all: true, ids: [] } });
  const [edit, setEdit] = useState(null);
  const manage = can(access, 'access.manage');

  const fail = useCallback(err => {
    if (err?.status === 403) onAccessDenied();
    else setError(err?.body?.error ? friendly(err.body.error) : 'That didn’t work. Try again.');
  }, [onAccessDenied]);
  const load = useCallback(async () => {
    try {
      setData(await APIService.request(`/club/${programId}/access`));
    } catch (err) { fail(err); }
  }, [programId, fail]);
  useEffect(() => {
    const timer = setTimeout(load, 0);
    return () => clearTimeout(timer);
  }, [load]);

  async function call(path, method, body, done) {
    setBusy(true); setError(''); setNotice(''); setNoticeWarn(false);
    try {
      const out = await APIService.request(`/club/${programId}/${path}`, { method, body: body ? JSON.stringify(body) : undefined });
      await load();
      if (done) done(out);
      return true;
    } catch (err) { fail(err); return false; } finally { setBusy(false); }
  }

  if (!data) return <section className="sa-root">{error ? <p className="ch-error" role="alert">{error}</p> : <p role="status">Loading staff and access…</p>}</section>;

  const people = [
    ...data.people.map(p => ({ key: `u${p.user_account_id}`, kind: 'person', ...p })),
    ...data.invites.map(i => ({ key: `i${i.id}`, kind: 'invite', ...i })),
  ];
  const selected = people.find(p => p.key === picked) || people.find(p => p.kind === 'person' && p.role !== 'owner' && p.role !== 'manager') || people[0];
  const matrixRole = selected?.kind === 'invite' ? null : selected?.role;
  // The marks are this person's own resolved permissions from the server, not a per-role table.
  const marks = selected?.kind === 'person' && Array.isArray(selected.permissions) ? selected.permissions : data.matrix.rows.map(() => false);
  const invitedManager = selected?.kind === 'person' && selected.role === 'manager' && !selected.verified;
  const roleName = selected?.kind === 'invite' ? (selected.status === 'expired' ? 'an expired invite' : 'a pending invite') : article(ROLE_LABELS[matrixRole] || 'member');

  // Refuses a scoped role with no squad ticked before anything is sent.
  const scopeReady = (role, scope) => {
    if (scopeValid(role, scope)) return true;
    setNotice(''); setError(friendly('scope_required'));
    return false;
  };
  const pick = row => {
    setPicked(row.key);
    setEdit(row.kind === 'person' && row.editable ? { role: row.role, scope: scopeFromEntry(row) } : null);
  };

  return <section className="sa-root" aria-labelledby="sa-title">
    <header className="sa-head">
      <p className="sa-eyebrow">Staff &amp; access · {countPeople(people.length)}</p>
      <h1 id="sa-title">Who can see <em>what</em></h1>
    </header>

    {manage ? <form className="sa-invite" onSubmit={e => {
      e.preventDefault();
      const email = form.email.trim();
      if (!scopeReady(form.role, form.scope)) return;
      call('staff-invites', 'POST', { email, role: form.role, ...scopeBody(form.role, form.scope) }, out => {
        setForm({ email: '', role: form.role, scope: form.scope });
        setNoticeWarn(out?.email_sent === false);
        setNotice(out?.email_sent === false ? `Invite saved for ${email}, but the email didn’t send. Try again later.` : `Invite sent to ${email}.`);
      });
    }}>
      <label htmlFor="sa-email"><span>Invite by email</span><input id="sa-email" type="email" required autoComplete="off" value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} placeholder="name@club.org" /></label>
      <label htmlFor="sa-role"><span>Role</span><select id="sa-role" value={form.role} onChange={e => setForm({ ...form, role: e.target.value })}>{INVITE_ROLES.map(r => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}</select></label>
      <SquadScope id="sa-scope" role={form.role} scope={form.scope} squads={squads} onChange={scope => { setError(''); setForm({ ...form, scope }); }} />
      <button type="submit" disabled={busy}>Send invite</button>
    </form> : <p className="sa-quiet">Only the club owner can invite staff or change access. The Academy Watch confirms the owner when your club is verified.</p>}
    {notice && <p className={`sa-notice${noticeWarn ? ' warn' : ''}`} role="status">{notice}</p>}
    {error && <p className="ch-error" role="alert">{error}</p>}

    <div className="sa-grid">
      <section aria-label="People with access">
        <div className="sa-row sa-row-head"><span>Person</span><span>Role</span><span>Squads</span></div>
        {people.map(row => <button type="button" key={row.key} className="sa-row" aria-pressed={selected?.key === row.key} onClick={() => pick(row)}>
          <span className="sa-person">
            <span className={`sa-avatar ${row.kind === 'invite' ? 'pending' : ''}`} aria-hidden="true">{row.kind === 'invite' ? '··' : initials(row.display_name || row.email || '?')}</span>
            <span><strong>{row.kind === 'invite' ? row.email : row.display_name || row.email}</strong><small>{row.kind === 'invite' ? `Invite sent ${shortDate(row.created_at)} · ${row.status === 'expired' ? 'expired' : 'expires'} ${shortDate(row.expires_at)}` : row.verified ? 'Verified club official' : row.email}</small></span>
          </span>
          <span className={`sa-role ${row.kind === 'invite' ? 'pending' : ''}`}>{row.kind === 'invite' ? `${row.status === 'expired' ? 'Expired' : 'Pending'} · ${ROLE_LABELS[row.role]}` : ROLE_LABELS[row.role]}</span>
          <span className="sa-squads">{squadScopeLabel(row, squads)}</span>
        </button>)}
        {people.length === 0 && <p className="sa-quiet">No one has access yet.</p>}

        {manage && selected?.kind === 'invite' && <div className="sa-editor">
          <p>Invitation for <strong>{selected.email}</strong> as {ROLE_LABELS[selected.role].toLowerCase()}.</p>
          {selected.status === 'expired' && <button type="button" className="sa-save" disabled={busy} onClick={() => call('staff-invites', 'POST', { email: selected.email, role: selected.role, ...scopeBody(selected.role, scopeFromEntry(selected)) }, out => {
            setPicked(null);
            setNoticeWarn(out?.email_sent === false);
            setNotice(out?.email_sent === false ? `Invite saved for ${selected.email}, but the email didn’t send. Try again later.` : `Invite sent to ${selected.email}. The previous link no longer works.`);
          })}>Send again</button>}
          <button type="button" className="sa-danger" disabled={busy} onClick={() => call(`staff-invites/${selected.id}/revoke`, 'POST', null, () => { setPicked(null); setNotice('Invite withdrawn. The link no longer works.'); })}>Withdraw invite</button>
        </div>}
        {manage && selected?.kind === 'person' && selected.editable && edit && <form className="sa-editor" onSubmit={e => {
          e.preventDefault();
          if (!scopeReady(edit.role, edit.scope)) return;
          call(`access/${selected.grant_id}`, 'PATCH', { role: edit.role, ...scopeBody(edit.role, edit.scope), expected_version: selected.version }, () => setNotice('Access updated. It applies straight away.'));
        }}>
          <p>Change access for <strong>{selected.display_name || selected.email}</strong></p>
          <div className="sa-editor-fields">
            <label htmlFor="sa-edit-role"><span>Role</span><select id="sa-edit-role" value={edit.role} onChange={e => setEdit({ ...edit, role: e.target.value })}>{INVITE_ROLES.map(r => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}</select></label>
            <SquadScope id="sa-edit-scope" role={edit.role} scope={edit.scope} squads={squads} onChange={scope => { setError(''); setEdit({ ...edit, scope }); }} />
          </div>
          <div className="sa-editor-actions">
            <button type="submit" className="sa-save" disabled={busy}>Save access</button>
            <button type="button" className="sa-danger" disabled={busy} onClick={() => call(`access/${selected.grant_id}`, 'DELETE', null, () => { setPicked(null); setNotice('Access removed. It ends straight away, including open match footage.'); })}>Remove access</button>
          </div>
        </form>}
      </section>

      <aside className="sa-aside">
        <section aria-labelledby="sa-matrix">
          <h2 id="sa-matrix">What {roleName} can do</h2>
          {data.matrix.rows.map((label, index) => <div key={label} className={`sa-perm ${marks[index] ? '' : 'off'}`}><span>{label}</span><span className="sa-mark">{marks[index] ? 'Yes' : '—'}</span></div>)}
          {invitedManager && <p className="sa-quiet sa-matrix-note">Invited managers can’t decide on scout requests. That stays with club officials The Academy Watch has verified.</p>}
        </section>
        <section aria-labelledby="sa-activity">
          <h2 id="sa-activity" className="sa-eyebrow-heading">Recent activity</h2>
          {data.activity.length ? data.activity.map((row, index) => <div key={index} className="sa-activity">{row.actor} · {ACTIVITY[row.action] || 'Access updated'}{row.role ? ` (${(ROLE_LABELS[row.role] || row.role).toLowerCase()})` : ''} <span>{shortDate(row.created_at)}</span></div>)
            : <p className="sa-quiet">Invites and access changes will appear here.</p>}
        </section>
      </aside>
    </div>
  </section>;
}

function countPeople(n) {
  return `${n} ${n === 1 ? 'person' : 'people'}`;
}

function friendly(code) {
  return {
    invalid_email: 'Enter a valid email address.',
    already_has_access: 'That person already has access to this club.',
    scope_required: 'Choose a squad, or All squads.',
    squad_not_found: 'That squad no longer exists. Refresh and try again.',
    grant_version_conflict: 'Someone else changed this person’s access. Refresh and try again.',
    cannot_change_own_access: 'You can’t change your own access.',
    owner_admin_only: 'The owner is set by The Academy Watch. Contact us to change it.',
    invite_not_pending: 'That invite has already been used or withdrawn.',
  }[code] || 'That didn’t work. Try again.';
}
