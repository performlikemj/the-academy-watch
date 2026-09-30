export function PublicMatchPanels({ stats }) {
  const publicData = stats?.public_match_data
  const clubData = stats?.club_verified
  const asOf = publicData?.as_of ? publicData.as_of.slice(0, 10) : 'unknown'
  return (
    <div className="grid gap-4 md:grid-cols-2" data-testid="source-stat-panels">
      {[
        { block: publicData, title: `Public match data — last updated ${asOf}` },
        { block: clubData, title: 'Club-verified' },
      ].map(({ block, title }) => (
        <section key={title} className="rounded-xl border bg-card p-5" aria-label={title}>
          <h3 className="text-sm font-semibold">{title}</h3>
          {block?.available ? (
            <dl className="mt-4 grid grid-cols-4 gap-3">
              {['appearances', 'minutes', 'goals', 'assists'].map((key) => (
                <div key={key}>
                  <dt className="text-xs capitalize text-muted-foreground">{key}</dt>
                  <dd className="mt-1 text-xl font-semibold tabular-nums">{block.totals?.[key] ?? '—'}</dd>
                </div>
              ))}
            </dl>
          ) : <p className="mt-3 text-sm text-muted-foreground">No stored results for this season.</p>}
        </section>
      ))}
    </div>
  )
}
