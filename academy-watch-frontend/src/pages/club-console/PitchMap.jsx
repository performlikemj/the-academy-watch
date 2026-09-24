import { useState } from 'react';
import { LockKeyhole, Users, Plus, ArrowUpRight } from 'lucide-react';
import { initials, ageDescription } from './presentation';
import { PlayerAvatar } from './PlayerAvatar';
export function PitchMap({
  program,
  staff,
  squads,
  focus,
  members,
  selected,
  onSelect,
  onOpenPlayer,
  onFocus,
  onOpenSquad,
  onStaff,
  onTemplate,
  busy,
  loading
}) {
  const unled = squads.filter(s => !s.lead_staff_id);
  const staffDepth = (person, seen = new Set()) => {
    if (!person || seen.has(person.id)) return 0;
    return 1 + staffDepth(staff.find(s => s.id === person.reports_to_staff_id), new Set([...seen, person.id]));
  };
  const levels = Math.max(1, ...staff.map(person => staffDepth(person)));
  const unledBranch = level => level > 1
    ? <li className="ch-vacant-level"><span className="ch-vacant-connector" aria-hidden="true" /><ul>{unledBranch(level - 1)}</ul></li>
    : <li><div className="ch-node ch-no-lead"><Users size={18} /><strong>No lead yet</strong></div><ul>{unled.map(squadNode)}</ul></li>;
  const squadNode = s => <li key={`s${s.id}`}>
    <button className={`ch-node squad ${focus === s.id ? 'chosen' : ''}`} onClick={() => onFocus(s.id)} aria-label={`Focus ${s.name}, ${s.member_count} players`}>
      <span className="ch-node-icon">
        <Users size={18} />
      </span>
      <strong>{s.name}</strong>
      <small>
        {s.member_count}{' players'}</small>
    </button>
    {focus === s.id && <div className="ch-chips">
      {loading ? <span>Loading…</span> : members.slice(0, 4).map(m => <button key={m.id} aria-pressed={selected?.id === m.id} onClick={() => onSelect(m)}>
        <PlayerAvatar member={m} />
        {m.shirt_number ? `#${m.shirt_number} ` : ''}
        {m.display_name}
      </button>)}
      <button className="ch-open-squad" onClick={() => onOpenSquad(s.id)}>
        {members.length > 4 ? `+${members.length - 4} more · ` : ''}{'Open squad '}<ArrowUpRight size={14} />
      </button>
    </div>}
  </li>;
  const staffNode = (person, ancestors = new Set()) => {
    if (ancestors.has(person.id)) return null;
    const visited = new Set([...ancestors, person.id]);
    const children = staff.filter(s => s.reports_to_staff_id === person.id);
    const led = squads.filter(s => s.lead_staff_id === person.id);
    return <li key={`p${person.id}`}>
    <button className="ch-node staff" onClick={onStaff}>
      <span className="ch-avatar">{initials(person.display_name)}</span>
      <span>
        <small>{person.title}</small>
        <strong>{person.display_name}</strong>
      </span>
    </button>
    {(children.length > 0 || led.length > 0) && <ul>
      {children.map(s => staffNode(s, visited))}
      {led.map(squadNode)}
    </ul>}
  </li>;
  };
  return <>
    <div className="ch-pitch" aria-label="Club organisation pitch">
      <div className="ch-pitch-label">
        <span className="ch-live-dot" />{' CLUB STRUCTURE '}<span>STAFF → SQUADS → PLAYERS</span>
      </div>
      {!staff.length && !squads.length ? <div className="ch-pitch-empty">
        <NetworkEmpty />
        <h3>Every club starts with its people</h3>
        <p>Build your club map with squads and the staff who lead them.</p>
        <div>
          <button className="ch-btn accent" disabled={busy} onClick={onTemplate}>Use standard squads</button>
          <button className="ch-btn outline" onClick={onStaff}>
            <Plus size={16} />{' Add staff'}</button>
        </div>
      </div> : <div className="ch-tree-scroll" tabIndex={0} aria-label="Scroll club map horizontally">
        <div className="ch-tree">
          <ul>
            <li>
              <button className="ch-node root" onClick={() => onFocus(null)}>
                <span className="ch-avatar">{initials(program.name)}</span>
                <span>
                  <small>WHOLE CLUB</small>
                  <strong>{program.name}</strong>
                </span>
              </button>
              <ul>
                {staff.filter(s => !s.reports_to_staff_id).map(s => staffNode(s))}
                {unled.length > 0 && unledBranch(levels)}
              </ul>
            </li>
          </ul>
        </div>
      </div>}
      <p className="ch-pitch-note">
        <LockKeyhole size={13} />{' Only your verified club managers can see this map.'}</p>
    </div>
    {selected && <div className="ch-dock">
      <PlayerAvatar member={selected} />
      <div className="ch-dock-person">
        <h3>
          {selected.display_name}{' '}
          {selected.shirt_number && <span>
            #
            {selected.shirt_number}
          </span>}
        </h3>
        <p>{[selected.position, squads.find(s => s.id === selected.squad_id)?.name, ageDescription(selected)].filter(Boolean).join(' · ')}</p>
        <small>
          <LockKeyhole size={12} />
          {selected.is_minor ? 'Minor · Identity stays inside the club' : 'Private club roster'}
        </small>
      </div>
      <FilmEvidence film={selected.film} dock />
      <button className="ch-btn accent" onClick={() => onOpenPlayer(selected.id)}>{'Open player page '}<ArrowUpRight size={16} />
      </button>
      <button aria-label="Close player dock" onClick={() => onSelect(null)}>×</button>
    </div>}
  </>;
}
function NetworkEmpty() {
  return <div className="ch-empty-symbol">
    <Users size={34} />
  </div>;
}
export function PlayerCard({
  member,
  squads,
  onSave,
  onOpen
}) {
  const [editing, setEditing] = useState(false);
  const [squadId, setSquadId] = useState(member.squad_id || '');
  const [number, setNumber] = useState(member.shirt_number || '');
  const [saving, setSaving] = useState(false);
  return <article className="ch-player-card">
    <div className="ch-player-top">
      <PlayerAvatar member={member} />
      <div>
        <h4><button onClick={onOpen}>{member.display_name}</button></h4>
        <p>{[member.position, ageDescription(member)].filter(Boolean).join(' · ')}</p>
      </div>
      {member.shirt_number && <strong className="ch-shirt">{member.shirt_number}</strong>}
    </div>
    <small>{member.is_minor ? 'Private · Under 18' : 'Private club roster'}</small>
    <FilmEvidence film={member.film} />
    <button className="ch-card-action" onClick={onOpen}>Open player page <ArrowUpRight size={14} /></button>
    <button className="ch-card-action" onClick={() => setEditing(!editing)}>Move squad / shirt number</button>
    {editing && <form className="ch-player-edit" onSubmit={async e => {
      e.preventDefault();
      setSaving(true);
      const ok = await onSave({
        squad_id: squadId ? Number(squadId) : null,
        shirt_number: number ? Number(number) : null
      });
      setSaving(false);
      if (ok) setEditing(false);
    }}>
      <label>
        Squad
        <select aria-label="Squad" value={squadId} onChange={e => setSquadId(e.target.value)}>
          <option value="">Unassigned</option>
          {squads.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
      </label>
      <label>
        Shirt number
        <input type="number" min="1" max="99" value={number} onChange={e => setNumber(e.target.value)} />
      </label>
      <button className="ch-btn" disabled={saving}>Save player</button>
    </form>}
  </article>;
}
function FilmEvidence({
  film,
  dock = false
}) {
  if (!film) return null;
  return <div className={dock ? 'ch-film-evidence dock' : 'ch-film-evidence'}>
    {film.on_camera_minutes != null && <span>
      <strong>{Math.round(film.on_camera_minutes * 10) / 10}</strong>{' min on camera'}</span>}
    {film.report_count > 0 && <span className="ch-report-chip">
      {film.report_count}{' '}
      {film.report_count === 1 ? 'report' : 'reports'}{' ready'}</span>}
    {dock && film.last_report_at && <span>{'Last report · '}{new Date(film.last_report_at).toLocaleDateString()}
    </span>}
  </div>;
}
