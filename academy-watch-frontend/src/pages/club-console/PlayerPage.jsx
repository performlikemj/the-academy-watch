import { useCallback, useEffect, useState } from 'react';
import { Film, LockKeyhole, Upload, ArrowUpRight } from 'lucide-react';
import { APIService } from '@/lib/api';
import { ClubPlayerReels, MatchReport } from '../MyClubConsole';
import { DevelopmentProgress } from '@/components/showcase/DevelopmentAction';
import { PlayerAvatar } from './PlayerAvatar';
import { ageDescription } from './presentation';

const tabs = ['Overview', 'Film', 'Development', 'Scout interest', 'Notes'];
const date = value => value ? new Date(value).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : '';
const empty = text => <p className="ch-player-empty">{text}</p>;
function Section({ title, detail, children }) {
  return <section className="ch-profile-section"><div className="ch-section-heading"><h2>{title}</h2>{detail && <small>{detail}</small>}</div>{children}</section>;
}

export function PlayerPage({ program, memberId, squads, members, onReload, onAccessDenied, onClub, onSquad, onScouts }) {
  const [profile, setProfile] = useState(null);
  const [tab, setTab] = useState('Overview');
  const [error, setError] = useState('');
  const [editor, setEditor] = useState(null);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(null);
  const [preview, setPreview] = useState(null);
  const [file, setFile] = useState(null);
  const [filmMatch, setFilmMatch] = useState(null);
  const endpoint = `/club/${program.id}/roster/${memberId}`;
  const fail = useCallback(err => { if (err.status === 403) onAccessDenied(); else setError(err.body?.error || err.message); }, [onAccessDenied]);
  const load = useCallback(async () => {
    try { setProfile(await APIService.request(`${endpoint}/profile`)); } catch (err) { fail(err); }
  }, [endpoint, fail]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!file) return;
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  async function save(path, method, data) {
    setBusy(true); setError('');
    try {
      await APIService.request(`${endpoint}${path}`, { method, body: JSON.stringify(data) });
      await load(); await onReload(); setEditor(null); return true;
    } catch (err) { fail(err); return false; } finally { setBusy(false); }
  }
  async function upload() {
    setBusy(true); setError(''); setProgress(0);
    try {
      const grant = await APIService.request(`${endpoint}/photo`, { method: 'POST', body: JSON.stringify({ content_type: file.type }) });
      await APIService.uploadPhotoToUrl(grant.upload, file, setProgress);
      await APIService.request(`${endpoint}/photo/complete`, { method: 'POST', body: JSON.stringify({ upload_token: grant.upload_token }) });
      setFile(null); setPreview(null); setEditor(null); await load(); await onReload();
    } catch (err) { fail(err); } finally { setBusy(false); setProgress(null); }
  }
  if (!profile) return <div className="ch-content">{error ? <p role="alert">{error}</p> : <p role="status">Loading player…</p>}<button className="ch-btn" onClick={onClub}>Back to club</button></div>;
  const identity = profile.identity;
  const film = profile.film || [];
  const development = profile.development || [];
  const stats = profile.results?.season;
  const openFilm = match => { setFilmMatch(match); setTab('Film'); };
  const filmCard = row => <div className="ch-film-row" key={row.match.id}>
    <div className="ch-film-tile"><Film size={30} /><span>{row.minutes_visible != null ? `${Math.round(row.minutes_visible * 10) / 10} min on camera` : 'Club match footage'}</span></div>
    <div><h3>vs {row.match.opponent_name || 'Opponent not recorded'}</h3><p>{date(row.match.match_date)} · {row.match.status}</p>
      <div className="ch-player-actions">{row.reel_available && <button className="ch-btn" onClick={() => openFilm(row.match)}>Watch reel <ArrowUpRight size={15} /></button>}
        {row.report_url && <button className="ch-btn" onClick={() => openFilm(row.match)}>Open match report</button>}</div>
      {!row.reel_available && !row.report_url && empty('No player reel or finalized report yet.')}</div>
  </div>;
  const scoutCard = <Section title="Scout interest">{profile.scout_interest?.locked
    ? <div className="ch-scout-locked"><LockKeyhole size={24} /><strong>Scout interest is locked</strong><p>This player is under 18. Their club page and photo stay private. Scouts cannot contact them.</p></div>
    : profile.scout_interest?.requests?.length ? <>{profile.scout_interest.requests.map(row => <div key={row.id} className="ch-feedback-row"><strong>Scout introduction</strong><p>{row.status} · {date(row.created_at)}</p></div>)}<button className="ch-btn" onClick={onScouts}>Manage introductions</button></>
      : empty('No scout introductions visible to your club.')}</Section>;
  return <div className="ch-player-page">
    <header className="ch-player-hero">
      <PlayerAvatar member={identity} className="ch-player-portrait" />
      <div className="ch-player-identity">
        <div className="ch-breadcrumb"><button onClick={onClub}>{program.name}</button><span>›</span><button onClick={() => onSquad(identity.squad_id || 'none')}>{identity.squad?.name || 'Unassigned'}</button><span>›</span><span>Player</span></div>
        <h1>{identity.display_name}{identity.shirt_number && <span>#{identity.shirt_number}</span>}</h1>
        <p>{[identity.position, identity.squad?.name, ageDescription(identity)].filter(Boolean).join(' · ')}</p>
        <div className="ch-player-chips">{identity.is_minor && <span>Minor — club-private</span>}<span>{identity.claim_status === 'claimed' ? 'Claimed by player' : 'Not yet claimed'}</span><span>Private club page</span></div>
      </div>
      <div className="ch-player-actions"><button className="ch-btn outline" disabled={busy} onClick={() => setEditor('photo')}><Upload size={16} />{identity.has_club_photo ? 'Manage photo' : 'Upload photo'}</button><button className="ch-btn outline" disabled={busy} onClick={() => setEditor('squad')}>Move squad</button><button className="ch-btn accent" disabled={busy} onClick={() => setEditor('brief')}>Edit brief</button></div>
    </header>
    <div className="ch-player-tabs" role="tablist" aria-label="Player sections">{tabs.map(t => <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}>{t}</button>)}</div>
    {error && <p className="ch-error" role="alert">{error}</p>}
    {editor && <section className="ch-player-editor ch-profile-section" aria-label={`Edit ${editor}`}>
      <div className="ch-section-heading"><h2>{editor === 'photo' ? 'Private club photo' : editor === 'brief' ? "Coach’s brief" : 'Move squad'}</h2><button disabled={busy} onClick={() => { setEditor(null); setFile(null); setPreview(null); }}>Close</button></div>
      {editor === 'photo' ? <><p>Only verified managers of this club can see the uploaded photo. An adult player’s approved photo takes priority.</p><input aria-label="Choose player photo" type="file" accept="image/jpeg,image/png,image/webp" disabled={busy} onChange={e => setFile(e.target.files?.[0] || null)} />
        {file && preview && <img className="ch-photo-preview" src={preview} alt="New club photo preview" />}{progress != null && <><progress max="100" value={progress} /><p role="status">{progress === 100 ? 'Processing photo…' : `Uploading ${progress}%`}</p></>}
        <div className="ch-player-actions"><button className="ch-btn accent" disabled={!file || busy} onClick={upload}>{identity.has_club_photo ? 'Replace photo' : 'Save photo'}</button>{identity.has_club_photo && <button className="ch-btn" disabled={busy} onClick={() => save('/photo', 'DELETE')}>Remove club photo</button>}</div></>
        : <form onSubmit={e => { e.preventDefault(); const data = new FormData(e.currentTarget); if (editor === 'brief') save('/brief', 'PUT', { body: data.get('body') }); else save('', 'PATCH', { squad_id: data.get('squad') ? Number(data.get('squad')) : null, shirt_number: data.get('shirt') ? Number(data.get('shirt')) : null }); }}>
          {editor === 'brief' ? <><p>Up to 8 short instructions. Keep player names out of the brief.</p><textarea aria-label="Coach brief" name="body" rows="6" maxLength="2000" defaultValue={identity.brief?.body || ''} /></>
            : <div className="ch-form-grid"><label>Squad<select name="squad" defaultValue={identity.squad_id || ''}><option value="">Unassigned</option>{squads.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label><label>Shirt number<input name="shirt" type="number" min="1" max="99" defaultValue={identity.shirt_number || ''} /></label></div>}
          <button className="ch-btn accent" disabled={busy}>Save {editor === 'brief' ? 'brief' : 'assignment'}</button></form>}
    </section>}
    <div className="ch-player-columns"><div className="ch-player-primary" role="tabpanel" aria-label={tab}>
      {tab === 'Overview' && <><Section title="This season" detail="From results your club entered">{stats ? <div className="ch-season-stats">{[['Apps', 'apps'], ['Minutes', 'minutes'], ['Goals', 'goals'], ['Assists', 'assists']].map(([label, key]) => <div key={key}><small>{label}</small><strong>{stats[key].toLocaleString()}</strong></div>)}</div> : empty('No results entered for this player this season.')}</Section>
        <Section title="Film Room" detail="Private club footage">{film.length ? filmCard(film[0]) : empty('Add this player to a match roster to bring their footage here.')}</Section>
        <Section title="Coach’s brief" detail="Private to club">{profile.coach_brief?.lines?.length ? <ul className="ch-brief-lines">{profile.coach_brief.lines.map((line, i) => <li key={i}>{line}</li>)}</ul> : empty('Add a short brief so your coaches know what to look for.')}</Section></>}
      {tab === 'Film' && <><Section title="Film Room">{film.length ? film.map(filmCard) : empty('No matches include this player yet.')}</Section>{filmMatch && <Section title={`vs ${filmMatch.opponent_name || 'Opponent not recorded'}`}><ClubPlayerReels programId={program.id} rosterEntryId={film.find(row => row.match.id === filmMatch.id)?.roster_entry_id} match={filmMatch} rosterMembers={members} onAccessDenied={onAccessDenied} />{filmMatch.status === 'finalized' && <MatchReport programId={program.id} rosterEntryId={film.find(row => row.match.id === filmMatch.id)?.roster_entry_id} match={filmMatch} onAccessDenied={onAccessDenied} />}</Section>}</>}
      {tab === 'Development' && <Section title="Development">{development.length ? development.map(row => <article className="ch-feedback-row" key={row.id}><h3>{row.title}</h3><p>{row.body}</p><DevelopmentProgress feedback={row} manager programId={program.id} onUpdated={load} onAccessLost={load} /></article>) : empty('No shared coaching feedback yet. Accepted player relationships can receive feedback from Roster & briefs.')}</Section>}
      {tab === 'Scout interest' && scoutCard}
      {tab === 'Notes' && <Section title="Private notes" detail="Only your club managers"><form onSubmit={e => { e.preventDefault(); save('', 'PATCH', { note: new FormData(e.currentTarget).get('note') }); }}><textarea aria-label="Private roster note" name="note" rows="7" maxLength="500" defaultValue={profile.note || ''} placeholder="Add context for your coaching team…" /><button className="ch-btn" disabled={busy}>Save note</button></form></Section>}
    </div><aside className="ch-player-secondary">{tab === 'Overview' && scoutCard}<Section title={`Pathway at ${program.name}`}>{profile.pathway?.length ? <ol className="ch-pathway">{profile.pathway.map(row => <li key={row.id} className={!row.ended_at ? 'current' : ''}><strong>{row.squad_name}</strong><small>{date(row.started_at)} – {row.ended_at ? date(row.ended_at) : 'now'}</small></li>)}</ol> : empty('Squad assignments will appear here when this player joins a squad.')}</Section>
      <Section title="Development actions">{development.filter(row => row.development_action).length ? development.filter(row => row.development_action).map(row => <div className="ch-feedback-row" key={row.id}><strong>{row.development_action.focus}</strong><p>{row.development_action.practice}</p><small>{(row.development_progress?.status || 'Waiting on player').replaceAll('_', ' ')}</small></div>) : empty('No active development actions yet.')}</Section></aside></div>
  </div>;
}
