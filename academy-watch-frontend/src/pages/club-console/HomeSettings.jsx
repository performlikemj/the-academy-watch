import { useState } from 'react';
import { APIService } from '@/lib/api';
import { initials } from './presentation';
const primarySwatches = ['#0F3D2E', '#7A1426', '#0B2A5B', '#1A1A1A', '#B3261E', '#4B2A7B'];
const accentSwatches = ['#E3B23C', '#F2F2F2', '#7FC8F8', '#F28C28', '#9BE564', '#D4AF7A'];
export function HomeSettings({
  view,
  program,
  squads,
  staff,
  mutate,
  refresh,
  onAccessDenied
}) {
  if (view === 'branding') return <Branding program={program} refresh={refresh} onAccessDenied={onAccessDenied} />;
  const isStaff = view === 'staff';
  const rows = isStaff ? staff : squads;
  return <section>
    <div className="ch-heading">
      <div>
        <h2>{isStaff ? 'Staff & roles' : 'Squads & age groups'}</h2>
        <p>{isStaff ? 'The people who shape your club. Roles do not grant login access.' : 'Build the pathway that fits your club.'}</p>
      </div>
    </div>
    <div className="ch-settings-list">
      {rows.map((row, index) => <EntityEditor key={`${row.id}:${row.updated_at}`} row={row} isStaff={isStaff} staff={staff} squads={squads} mutate={mutate} onUp={!isStaff && index > 0 ? () => {
        const ids = squads.map(s => s.id);
        [ids[index - 1], ids[index]] = [ids[index], ids[index - 1]];
        return mutate('squads/reorder', 'POST', {
          ids
        });
      } : null} />)}
      <EntityEditor key={`new-${rows.length}`} isStaff={isStaff} staff={staff} squads={squads} mutate={mutate} />
    </div>
  </section>;
}
function EntityEditor({
  row,
  isStaff,
  staff,
  squads,
  mutate,
  onUp
}) {
  const [form, setForm] = useState(row || (isStaff ? {
    display_name: '',
    title: '',
    reports_to_staff_id: '',
    leads_squad_id: ''
  } : {
    name: '',
    kind: 'age_group',
    age_limit: ''
  }));
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const change = (field, value) => setForm({
    ...form,
    [field]: value
  });
  const path = `${isStaff ? 'staff' : 'squads'}${row ? `/${row.id}` : ''}`;
  const save = async event => {
    event.preventDefault();
    setBusy(true);
    const data = isStaff ? {
      display_name: form.display_name,
      title: form.title,
      reports_to_staff_id: form.reports_to_staff_id ? Number(form.reports_to_staff_id) : null,
      leads_squad_id: form.leads_squad_id ? Number(form.leads_squad_id) : null
    } : {
      name: form.name,
      kind: form.kind,
      age_limit: form.age_limit ? Number(form.age_limit) : null
    };
    await mutate(path, row ? 'PATCH' : 'POST', data);
    setBusy(false);
  };
  return <form className="ch-entity" onSubmit={save}>
    <h3>{row ? row.display_name || row.name : isStaff ? 'Add staff' : 'Add squad'}</h3>
    <div className="ch-form-grid">
      <label>
        {isStaff ? 'Display name' : 'Squad name'}
        <input required maxLength={isStaff ? 120 : 80} value={form[isStaff ? 'display_name' : 'name']} onChange={e => change(isStaff ? 'display_name' : 'name', e.target.value)} />
      </label>
      {isStaff ? <>
        <label>
          Job title
          <input required maxLength={80} value={form.title} onChange={e => change('title', e.target.value)} />
        </label>
        <label>
          Reports to
          <select value={form.reports_to_staff_id || ''} onChange={e => change('reports_to_staff_id', e.target.value)}>
            <option value="">Top of club</option>
            {staff.filter(s => s.id !== row?.id).map(s => <option key={s.id} value={s.id}>{s.display_name}</option>)}
          </select>
        </label>
        <label>
          Leads squad
          <select value={form.leads_squad_id || ''} onChange={e => change('leads_squad_id', e.target.value)}>
            <option value="">No squad</option>
            {squads.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </label>
      </> : <>
        <label>
          Kind
          <select value={form.kind} onChange={e => change('kind', e.target.value)}>{[['first_team', 'First team'], ['reserves', 'Reserves'], ['age_group', 'Age group'], ['other', 'Other']].map(([key, text]) => <option key={key} value={key}>{text}</option>)}</select>
        </label>
        <label>
          Age limit
          <input type="number" min="1" max="99" value={form.age_limit || ''} onChange={e => change('age_limit', e.target.value)} />
        </label>
      </>}
    </div>
    <div className="ch-actions">
      <button className="ch-btn" disabled={busy}>{row ? 'Save changes' : isStaff ? 'Add staff' : 'Add squad'}</button>
      {onUp && <button type="button" className="ch-btn" disabled={busy} onClick={onUp}>Move up</button>}
      {row && <button className="ch-btn danger" type="button" onClick={() => setConfirm(true)}>Remove</button>}
    </div>
    {confirm && <div className="ch-confirm" role="alert">
      <p>{'Remove '}{row.display_name || row.name}{'? '}{isStaff ? 'Direct reports will move to the top of the club.' : 'Players will become unassigned.'}
      </p>
      <button type="button" disabled={busy} onClick={async () => {
        setBusy(true);
        await mutate(path, 'DELETE', {});
        setBusy(false);
      }}>Confirm removal</button>
      <button type="button" onClick={() => setConfirm(false)}>Cancel</button>
    </div>}
  </form>;
}
function Branding({
  program,
  refresh,
  onAccessDenied
}) {
  const [colors, setColors] = useState(program.brand);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(null);
  const change = (key, value) => {
    setColors({
      ...colors,
      [key]: value
    });
    setError('');
    setNotice('');
  };
  const fail = err => {
    if (err.status === 403) onAccessDenied();else setError(err.body?.error || err.message || 'Could not save branding.');
  };
  async function save() {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await APIService.request(`/club/${program.id}/branding`, {
        method: 'PATCH',
        body: JSON.stringify({
          primary_color: colors.primary_color,
          accent_color: colors.accent_color
        })
      });
      await refresh();
      setNotice('Branding saved.');
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  }
  async function upload(file) {
    if (!file) return;
    setBusy(true);
    setError('');
    setProgress(0);
    try {
      const grant = await APIService.request(`/club/${program.id}/branding/banner`, {
        method: 'POST',
        body: JSON.stringify({
          content_type: file.type
        })
      });
      await APIService.uploadPhotoToUrl(grant.upload, file, setProgress);
      const result = await APIService.request(`/club/${program.id}/branding/banner/complete`, {
        method: 'POST',
        body: JSON.stringify({
          upload_token: grant.upload_token
        })
      });
      setColors(c => ({
        ...c,
        banner_url: result.brand.banner_url
      }));
      await refresh();
      setNotice('Banner uploaded.');
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
      setProgress(null);
    }
  }
  return <section>
    <div className="ch-heading">
      <div>
        <p className="ch-eyebrow">Settings / Club identity</p>
        <h2>Make it your club</h2>
        <p>Your colours. Your crest. Your home.</p>
      </div>
    </div>
    <div className="ch-brand-grid">
      <div className="ch-brand-controls">
        {[['primary_color', 'Primary colour', primarySwatches], ['accent_color', 'Accent colour', accentSwatches]].map(([key, title, swatches]) => <div className="ch-brand-field" key={key}>
          <h3>{title}</h3>
          <p>{key === 'primary_color' ? 'Your club’s main colour. Used on the rail and banner.' : 'For highlights, selected players and key actions.'}</p>
          <div className="ch-swatches">{swatches.map(hex => <button key={hex} aria-label={`${title} ${hex}`} aria-pressed={colors[key] === hex} style={{
              background: hex
            }} onClick={() => change(key, hex)} />)}</div>
          <label>
            Hex colour
            <input aria-label={`${title} hex`} value={colors[key]} maxLength={7} onChange={e => change(key, e.target.value)} />
          </label>
        </div>)}
        <div className="ch-brand-field">
          <h3>Club banner</h3>
          <p>A view of your ground, your badge or your club colours. JPEG, PNG or WebP, up to 8 MB.</p>
          <label className="ch-upload">
            Upload banner
            <input aria-label="Upload banner" type="file" accept="image/jpeg,image/png,image/webp" disabled={busy} onChange={e => upload(e.target.files?.[0])} />
          </label>
          {progress !== null && <label>{'Uploading '}{progress}
            %
            <progress value={progress} max="100" />
          </label>}
        </div>
      </div>
      <div>
        <h3 className="ch-preview-label">Live preview</h3>
        <div className="ch-brand-preview" style={{
          '--preview-primary': /^#[0-9a-f]{6}$/i.test(colors.primary_color) ? colors.primary_color : '#0F3D2E',
          '--preview-accent': /^#[0-9a-f]{6}$/i.test(colors.accent_color) ? colors.accent_color : '#E3B23C'
        }}>
          <div className="ch-preview-banner">
            <span>{initials(program.name)}</span>
            <div>
              <h2>{program.name}</h2>
              <p>Verified club · Your club home</p>
            </div>
          </div>
          <div className="ch-preview-body">
            <div className="ch-preview-node">
              <span>{initials(program.name)}</span>
              <div>
                <strong>Your club</strong>
                <p>People, squads and possibility</p>
              </div>
            </div>
            <div className="ch-actions">
              <span className="preview-accent">Open squad</span>
              <span className="preview-primary">Club map</span>
            </div>
          </div>
        </div>
        <p className="ch-preview-help">Colours must keep text readable with a contrast ratio of at least 4.5:1.</p>
        {error && <p className="ch-error" role="alert">{error}</p>}
        {notice && <p role="status">{notice}</p>}
        <div className="ch-actions">
          <button className="ch-btn" disabled={busy} onClick={() => {
            setColors(program.brand);
            setError('');
            setNotice('');
          }}>Discard</button>
          <button className="ch-btn dark" disabled={busy} onClick={save}>{busy ? 'Saving…' : 'Save branding'}</button>
        </div>
      </div>
    </div>
  </section>;
}
