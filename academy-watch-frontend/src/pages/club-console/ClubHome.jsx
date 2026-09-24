import { useCallback, useEffect, useState } from 'react';
import { Network, Users, Film, Send, Settings, ShieldCheck, Plus, LockKeyhole, Search } from 'lucide-react';
import { APIService } from '@/lib/api';
import { AddRosterMemberDialog } from '../MyClubConsole';
import { HomeSettings } from './HomeSettings';
import { PitchMap, PlayerCard } from './PitchMap';
import { initials, positionGroup } from './presentation';
import './club-home.css';
export function ClubHome({
  program,
  members,
  onReload,
  onAccessDenied,
  programOptions,
  onProgramChange,
  panels,
  statusContent,
  moderationCount
}) {
  const [map, setMap] = useState(null);
  const [navigationOpen, setNavigationOpen] = useState(false);
  const [view, setView] = useState('map');
  const [focus, setFocus] = useState(null);
  const [selected, setSelected] = useState(null);
  const [squadMembers, setSquadMembers] = useState([]);
  const [query, setQuery] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const programId = program.id;
  const squads = map?.squads || [];
  const staff = map?.staff || [];
  const club = map?.program || program;
  const brand = club.brand || {
    primary_color: '#0F3D2E',
    accent_color: '#E3B23C'
  };
  const squad = squads.find(s => s.id === focus);
  const lead = staff.find(s => s.id === squad?.lead_staff_id);
  const fail = useCallback(err => {
    if (err.status === 403) onAccessDenied();else setError(err.body?.error || err.message || 'Could not save this change.');
  }, [onAccessDenied]);
  const refresh = useCallback(async () => {
    try {
      setMap(await APIService.request(`/club/${programId}/map`));
    } catch (err) {
      fail(err);
    }
  }, [programId, fail]);
  useEffect(() => {
    refresh();
  }, [refresh, members]);
  useEffect(() => {
    let cancelled = false;
    setSquadMembers([]);
    setSelected(null);
    if (focus === null) return;
    setLoading(true);
    APIService.getClubRoster(programId, focus).then(data => {
      if (!cancelled) setSquadMembers(data.members || []);
    }).catch(err => {
      if (!cancelled) fail(err);
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [programId, focus, members, fail]);
  async function mutate(path, method, data) {
    setError('');
    setBusy(true);
    try {
      await APIService.request(`/club/${programId}/${path}`, {
        method,
        body: JSON.stringify(data)
      });
      await refresh();
      await onReload();
      return true;
    } catch (err) {
      fail(err);
      return false;
    } finally {
      setBusy(false);
    }
  }
  function navigate(next) {
    setView(next);
    setError('');
    setNavigationOpen(false);
  }
  const openSquad = id => {
    setFocus(id);
    navigate('squad');
  };
  const matchesQuery = value => (value || '').toLowerCase().includes(query.toLowerCase());
  const visibleSquads = squads.filter(s => matchesQuery(s.name) || members.some(m => m.squad_id === s.id && matchesQuery(m.display_name)));
  const settingsViews = ['branding', 'squads', 'staff', 'profile', 'affiliations', 'roster'];
  const rail = [['Club', Network, 'map'], ['Squads', Users, 'squad'], ['Matches', Film, 'matches'], ['Scouts', Send, 'introductions'], ['Settings', Settings, 'branding']];
  const activeRail = settingsViews.includes(view) ? 'branding' : view;
  const effectiveMembers = squadMembers.filter(m => m.available && matchesQuery(m.display_name));
  return <div className="club-home" style={{
    '--club-primary': brand.primary_color,
    '--club-accent': brand.accent_color
  }}>
    <nav className="ch-rail" aria-label="Club console">
      <div className="ch-mark">{club.crest_url ? <img src={club.crest_url} alt="" /> : initials(club.name)}</div>
      {rail.map(([label, Icon, target]) => <button key={label} aria-current={activeRail === target ? 'page' : undefined} onClick={() => {
        if (target === 'squad' && focus === null) setFocus(squads[0]?.id || 'none');
        navigate(target);
      }}>
        <Icon size={22} />
        <span>{label}</span>
      </button>)}
    </nav>
    <aside className={`ch-sidebar ${navigationOpen ? 'is-open' : ''}`} id="club-navigation">
      <div className="ch-club-id">
        <div className="ch-mark">{initials(club.name)}</div>
        <div>
          <strong>{club.name}</strong>
          <small>{'Verified club · '}{members.length}{' players'}</small>
        </div>
      </div>
      {programOptions.length > 1 && <select aria-label="Switch club program" value={programId} onChange={e => onProgramChange(Number(e.target.value))}>{programOptions.map(p => <option key={p.program.id} value={p.program.id}>{p.program.name}</option>)}</select>}
      <label className="ch-search">
        <Search size={16} />
        <input aria-label="Search squads and players" placeholder="Find a squad or player…" value={query} onChange={e => setQuery(e.target.value)} />
      </label>
      <div className="ch-eyebrow">Club</div>
      <button className={view === 'map' ? 'active' : ''} onClick={() => navigate('map')}>
        <Network size={17} />{' Club map'}</button>
      <button onClick={() => navigate('staff')}>
        <Users size={17} />{' Staff'}</button>
      <div className="ch-eyebrow">Squads</div>
      {visibleSquads.map(s => <button key={s.id} className={view === 'squad' && focus === s.id ? 'active' : ''} onClick={() => openSquad(s.id)}>
        <span>
          <strong>{s.name}</strong>
          <small>{staff.find(person => person.id === s.lead_staff_id)?.display_name || 'No lead coach'}</small>
        </span>
        <span className="ch-count">{s.member_count}</span>
      </button>)}
      <button onClick={() => openSquad('none')}>{'Unassigned '}<span className="ch-count">{map?.unassigned_count || 0}</span>
      </button>
      <button onClick={() => navigate('squads')}>
        <Plus size={17} />{' Add squad'}</button>
      {query && members.filter(m => m.available && matchesQuery(m.display_name)).slice(0, 12).map(m => <button key={m.id} onClick={() => {
        setFocus(m.squad_id || 'none');
        setView('squad');
        setQuery('');
      }}>
        {m.shirt_number ? `#${m.shirt_number} ` : ''}
        {m.display_name}
      </button>)}
      <div className="ch-sidebar-foot">
        <LockKeyhole size={15} />{' Private club workspace'}</div>
    </aside>
    <main className="ch-main">
      <button className="ch-mobile-navigation" aria-expanded={navigationOpen} aria-controls="club-navigation" onClick={() => setNavigationOpen(!navigationOpen)}>Squads & club navigation</button>
      <header className="ch-banner" style={brand.banner_url ? {
        backgroundImage: `linear-gradient(#00000033, #00000033), linear-gradient(color-mix(in srgb, var(--club-primary) 88%, transparent), color-mix(in srgb, var(--club-primary) 88%, transparent)), url("${brand.banner_url}")`
      } : undefined}>
        <div className="ch-crest">{club.crest_url ? <img src={club.crest_url} alt={`${club.name} crest`} /> : initials(club.name)}</div>
        <div>
          <div className="ch-verified">
            <ShieldCheck size={15} />{' YOUR CLUB HOME'}</div>
          <h1>{club.name}</h1>
          <p>
            {squads.length}{' squads · '}{members.length}{' players · One club'}</p>
        </div>
        <button className="ch-banner-edit" onClick={() => navigate('branding')}>Edit branding</button>
      </header>
      {statusContent}
      <div className="ch-content">
        {error && <p className="ch-error" role="alert">{error}</p>}
        {view === 'map' && <>
          <div className="ch-heading">
            <div>
              <h2>Club map</h2>
              <p>Your people. Your pathway. Your club.</p>
            </div>
            <button className="ch-btn" onClick={() => navigate('staff')}>Manage staff</button>
          </div>
          <div className="ch-pills">
            <button aria-pressed={focus === null} onClick={() => setFocus(null)}>Whole club</button>
            {squads.map(s => <button key={s.id} aria-pressed={focus === s.id} onClick={() => setFocus(s.id)}>{s.name}</button>)}
          </div>
          <PitchMap program={club} squads={squads} staff={staff} focus={focus} members={effectiveMembers} selected={selected} onSelect={setSelected} onFocus={setFocus} onOpenSquad={openSquad} onStaff={() => navigate('staff')} onTemplate={() => mutate('squads/template', 'POST', {})} busy={busy} loading={loading} />
        </>}
        {view === 'squad' && <>
          <div className="ch-squad-header">
            <p>
              <button onClick={() => navigate('map')}>Club map</button>{' / '}{squad?.name || 'Unassigned'}
            </p>
            <div className="ch-heading">
              <div>
                <h2>{squad?.name || 'Unassigned'}</h2>
                <p>
                  {squadMembers.length}{' players'}{lead ? ` · ${lead.display_name}, ${lead.title}` : ''}
                </p>
              </div>
              <button className="ch-btn accent" onClick={() => setAddOpen(true)}>
                <Plus size={16} />{' Add player'}</button>
            </div>
          </div>
          <div className="ch-tabs">
            <button aria-current="page">Players</button>
            <button onClick={() => navigate('matches')}>Matches</button>
            <button onClick={() => navigate('roster')}>Briefs & player management</button>
          </div>
          {effectiveMembers.length > 0 && effectiveMembers.every(m => m.is_minor) && <p className="ch-privacy">
            <LockKeyhole size={17} />
            Everyone in this squad is under 18. Their identities stay inside the club and scouts can’t contact them.
          </p>}
          {loading ? <p role="status">Loading players…</p> : effectiveMembers.length === 0 ? <div className="ch-empty">
            <h3>A place for your next team</h3>
            <p>Add a player or move someone here from another squad.</p>
            <button className="ch-btn accent" onClick={() => setAddOpen(true)}>Add player</button>
          </div> : ['Goalkeepers', 'Defenders', 'Midfielders', 'Forwards', 'Other'].map(group => {
            const players = effectiveMembers.filter(m => positionGroup(m.position) === group);
            return players.length > 0 && <section className="ch-position" key={group}>
            <h3>
              {group}{' · '}{players.length}
            </h3>
            <div className="ch-player-grid">{players.map(m => <PlayerCard key={m.id} member={m} squads={squads} onSave={data => mutate(`roster/${m.id}`, 'PATCH', data)} />)}</div>
          </section>;
          })}
        </>}
        {settingsViews.includes(view) && <div className="ch-settings-nav">{[['branding', 'Branding'], ['squads', 'Squads & age groups'], ['staff', 'Staff & roles'], ['roster', 'Roster & briefs'], ['profile', 'Club profile'], ['affiliations', `Affiliations${moderationCount ? ` (${moderationCount})` : ''}`]].map(([key, label]) => <button aria-current={view === key ? 'page' : undefined} key={key} onClick={() => navigate(key)}>{label}</button>)}</div>}
        {['branding', 'squads', 'staff'].includes(view) && <HomeSettings key={`${view}:${programId}`} view={view} program={club} squads={squads} staff={staff} mutate={mutate} refresh={refresh} onAccessDenied={onAccessDenied} />}
        {panels[view]}
      </div>
    </main>
    {addOpen && <AddRosterMemberDialog open onOpenChange={setAddOpen} programId={programId} squads={squads} defaultSquad={focus === 'none' ? null : focus} onAdded={onReload} onAccessDenied={onAccessDenied} />}
  </div>;
}
