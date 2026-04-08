/**
 * "By the numbers" — three stat callouts in a responsive grid.
 *
 * Reads `byNumbers.minutes_leaders` (array of {player, minutes}) and
 * `byNumbers.ga_leaders` (array of {player, g, a}). The third tile is a
 * "Top rating" surface if any item carries a rating; otherwise hidden.
 */

function StatCallout({ label, headline, sub }) {
  return (
    <div
      className="rounded-lg p-5"
      style={{ background: 'var(--tl-section)' }}
    >
      <p className="tl-eyebrow m-0 mb-2">{label}</p>
      <p className="tl-headline text-2xl sm:text-3xl text-[var(--tl-text)] m-0 leading-tight">
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

  if (minutes.length === 0 && ga.length === 0) return null

  const minutesTop = minutes[0]
  const gaTop = ga[0]
  const tiles = []
  if (minutesTop) {
    tiles.push({
      label: 'Minutes Leader',
      headline: minutesTop.player,
      sub: `${minutesTop.minutes}'`,
    })
  }
  if (gaTop) {
    tiles.push({
      label: 'Goal Contributors',
      headline: gaTop.player,
      sub: `${gaTop.g || 0}G ${gaTop.a || 0}A`,
    })
  }

  // Optional third tile from the next minutes leader if we have one
  if (minutes[1]) {
    tiles.push({
      label: 'Runner Up',
      headline: minutes[1].player,
      sub: `${minutes[1].minutes}'`,
    })
  }

  if (tiles.length === 0) return null

  return (
    <section className="mb-10 sm:mb-12">
      <h2 className="tl-eyebrow m-0 mb-4">By the Numbers</h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 sm:gap-4">
        {tiles.map((tile, idx) => (
          <StatCallout key={idx} {...tile} />
        ))}
      </div>
    </section>
  )
}

export default ByTheNumbersGrid
