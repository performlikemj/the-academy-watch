import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { LEVEL_LABELS, LEVELS, PROGRAMME_LABELS, PROGRAMMES, parseCoordinatePair } from '@/lib/club-directory'

/**
 * "Find us" fields of the club profile form (Clubs near you, dark behind CLUB_DIRECTORY_ENABLED).
 * Controlled: `value` is the form from lib/club-directory `directoryForm`. Saved with the rest of the
 * profile, so nothing here is public until the revision is approved.
 */
export function DirectoryFields({ value, onChange, errors = {} }) {
  const edit = (field, next) => onChange({ ...value, [field]: next })
  const editLatitude = (text) => {
    // Maps apps copy "51.5010, -0.1416" as one string: split it across both boxes.
    const pair = parseCoordinatePair(text)
    if (pair && /[,\s]/.test(text.trim())) onChange({ ...value, latitude: String(pair.latitude), longitude: String(pair.longitude) })
    else edit('latitude', text)
  }
  const toggleProgramme = (code) => edit(
    'gender_programs',
    value.gender_programs.includes(code) ? value.gender_programs.filter((item) => item !== code) : [...value.gender_programs, code],
  )
  const error = (field) => (errors[field] ? <p className="text-xs text-destructive">{errors[field]}</p> : null)

  return (
    <fieldset className="space-y-4 rounded-[10px] border border-border p-4 sm:p-5" data-testid="directory-fields">
      <legend className="eyebrow px-2">Clubs near you</legend>
      <p className="text-sm text-muted-foreground">
        Where people can find you and who you run football for. Shown in the public club search once approved.
        Leave anything blank that you’d rather not list.
      </p>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="venue_name">Ground or venue</Label>
          <Input id="venue_name" value={value.venue_name} onChange={(event) => edit('venue_name', event.target.value)} maxLength={120} placeholder="Name of your home ground" />
          {error('venue_name')}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="postcode">Postcode or ZIP</Label>
          <Input id="postcode" value={value.postcode} onChange={(event) => edit('postcode', event.target.value)} maxLength={12} autoComplete="off" />
          {error('postcode')}
        </div>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="latitude">Latitude (optional)</Label>
          <Input id="latitude" inputMode="decimal" value={value.latitude} onChange={(event) => editLatitude(event.target.value)} placeholder="e.g. 51.50101" autoComplete="off" />
          {error('latitude')}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="longitude">Longitude (optional)</Label>
          <Input id="longitude" inputMode="decimal" value={value.longitude} onChange={(event) => edit('longitude', event.target.value)} placeholder="e.g. -0.14159" autoComplete="off" />
          {error('longitude')}
        </div>
      </div>
      <p className="text-xs text-muted-foreground">
        The pin lets people sort clubs by distance. In a maps app, press and hold on your ground, copy the two numbers and paste them into Latitude.
        Without a pin your club is still listed, with “distance unavailable”.
      </p>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="club_level">Level</Label>
          <select
            id="club_level"
            value={value.club_level}
            onChange={(event) => edit('club_level', event.target.value)}
            className="h-11 w-full rounded-md border border-input bg-background px-3 text-sm"
          >
            <option value="">Not listed</option>
            {LEVELS.map((code) => <option key={code} value={code}>{LEVEL_LABELS[code]}</option>)}
          </select>
          {error('club_level')}
        </div>
        <div className="space-y-1.5">
          <span id="gender-programs-label" className="text-sm font-medium leading-none">Football for</span>
          <div className="flex flex-wrap gap-x-5 gap-y-2 pt-1.5" role="group" aria-labelledby="gender-programs-label">
            {PROGRAMMES.map((code) => (
              <label key={code} className="text-sm" style={{ display: 'inline-flex', flexDirection: 'row', alignItems: 'center', gap: 8, minHeight: 44 }}>
                <input type="checkbox" className="h-4 w-4 accent-[var(--color-ink)]" checked={value.gender_programs.includes(code)} onChange={() => toggleProgramme(code)} />
                {PROGRAMME_LABELS[code]}
              </label>
            ))}
          </div>
          {error('gender_programs')}
        </div>
      </div>
    </fieldset>
  )
}
