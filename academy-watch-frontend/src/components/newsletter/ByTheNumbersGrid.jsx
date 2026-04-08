/**
 * "By the numbers" — up to 5 stat callouts in a responsive grid.
 *
 * Reads:
 *   - byNumbers.minutes_leaders   [{player, minutes}]
 *   - byNumbers.ga_leaders        [{player, g, a}]
 *   - byNumbers.rating_leaders    [{player, rating}]            (post-PR-A)
 *   - byNumbers.key_passes_leaders [{player, key_passes}]       (post-PR-A)
 *   - byNumbers.clean_sheets_leaders [{player, clean_sheets}]   (post-PR-A)
 *
 * Each section is optional — only callouts whose source list has data are
 * rendered. On small screens the grid collapses to 2 / 1 columns.
 */

function StatCallout({ label, headline, sub }) {
  return (
    <div
      className="rounded-lg p-5 lg:p-6"
      style={{ background: 'var(--tl-section)' }}
    >
      <p className="tl-eyebrow m-0 mb-2">{label}</p>
      <p className="tl-headline text-xl sm:text-2xl text-[var(--tl-text)] m-0 leading-tight truncate">
        {headline}
      </p>
      {sub && (
        <p className="text-[13px] font-semibold m-0 mt-2 text-[var(--tl-primary)]">{sub}</p>
      )}
    </div>
  )
}

export function ByTheNumbersGrid({ byNumbers }) {
  if (!byNumbers || typeof byNumbers !== 'object') return null

  const minutes = Array.isArray(byNumbers.minutes_leaders) ? byNumbers.minutes_leaders : []
  const ga = Array.isArray(byNumbers.ga_leaders) ? byNumbers.ga_leaders : []
  const rating = Array.isArray(byNumbers.rating_leaders) ? byNumbers.rating_leaders : []
  const keyPasses = Array.isArray(byNumbers.key_passes_leaders) ? byNumbers.key_passes_leaders : []
  const cleanSheets = Array.isArray(byNumbers.clean_sheets_leaders) ? byNumbers.clean_sheets_leaders : []

  const tiles = []
  if (minutes[0]) {
    tiles.push({
      label: 'Minutes Leader',
      headline: minutes[0].player,
      sub: `${minutes[0].minutes}'`,
    })
  }
  if (ga[0]) {
    tiles.push({
      label: 'Goal Contributors',
      headline: ga[0].player,
      sub: `${ga[0].g || 0}G ${ga[0].a || 0}A`,
    })
  }
  if (rating[0]) {
    tiles.push({
      label: 'Top Rating',
      headline: rating[0].player,
      sub: `${rating[0].rating}`,
    })
  }
  if (keyPasses[0]) {
    tiles.push({
      label: 'Top Key Passes',
      headline: keyPasses[0].player,
      sub: `${keyPasses[0].key_passes} KP`,
    })
  }
  if (cleanSheets[0]) {
    tiles.push({
      label: 'Clean Sheets',
      headline: cleanSheets[0].player,
      sub: `${cleanSheets[0].clean_sheets}`,
    })
  }

  // Fall back to a runner-up minutes leader if we still only have 2 tiles
  if (tiles.length === 2 && minutes[1]) {
    tiles.push({
      label: 'Runner Up Minutes',
      headline: minutes[1].player,
      sub: `${minutes[1].minutes}'`,
    })
  }

  if (tiles.length === 0) return null

  return (
    <section className="mb-12 sm:mb-14 lg:mb-16">
      <h2 className="tl-eyebrow m-0 mb-4">By the Numbers</h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3 sm:gap-4">
        {tiles.map((tile, idx) => (
          <StatCallout key={idx} {...tile} />
        ))}
      </div>
    </section>
  )
}

export default ByTheNumbersGrid
