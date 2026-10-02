import './player-card.css'
import { useState } from 'react'
import { ConfirmedTick, clubColorStyle } from '@/components/player-card/PlayerCard'
import { formatSeasonLabel } from '@/lib/seasons'
import {
  MATCH_LINES_PREVIEW,
  cardsLabel,
  keeperFigure,
  lineSource,
  lineSummary,
  matchDateParts,
  matchResult,
  minutesShare,
  quietFigure,
  summarizeSeason,
  venueLabel,
} from '@/lib/player-card'

/** Facts strip: only fields with a value, reflowing 6 → 3 → 2 columns. */
export function PlayerFacts({ facts }) {
  if (!facts?.length) return null
  return (
    <dl className="pc pc-facts" style={{ '--pc-fact-cols': Math.min(facts.length, 6) }} data-testid="player-facts">
      {facts.map((fact) => (
        <div className="pc-fact" key={fact.label}>
          <dt>{fact.label}</dt>
          <dd>{fact.email ? <a href={`mailto:${fact.value}`}>{fact.value}</a> : fact.value}</dd>
        </div>
      ))}
    </dl>
  )
}

function Tile({ tile, lead = false }) {
  if (lead) {
    return (
      <div className="pc-tile pc-tile--lead" data-testid={`season-tile-${tile.key}`}>
        <div className="pc-tile-main">
          <div className="pc-tile-label">{tile.label}</div>
          <div className="pc-tile-value" data-quiet={tile.quiet}>{tile.value}</div>
        </div>
        <div className="pc-tile-meter">
          {tile.share == null ? null : (
            <div className="pc-meter" aria-hidden="true"><span style={{ width: `${Math.round(tile.share * 100)}%` }} /></div>
          )}
          {tile.note ? <div className="pc-tile-note">{tile.note}</div> : null}
        </div>
      </div>
    )
  }
  return (
    <div className="pc-tile" data-testid={`season-tile-${tile.key}`}>
      <div className="pc-tile-label">
        <span className="hidden min-[900px]:inline">{tile.label}</span>
        <span className="min-[900px]:hidden">{tile.shortLabel}</span>
      </div>
      <div className="pc-tile-value" data-quiet={tile.quiet} data-word={Boolean(tile.word)}>{tile.value}</div>
      {tile.note ? <div className="pc-tile-note">{tile.note}</div> : null}
    </div>
  )
}

function SourceMark({ source, size = 16 }) {
  return (
    <div className="pc-mark" data-confirmed={source.confirmed}>
      {source.confirmed ? <ConfirmedTick size={size} /> : <span className="pc-mark-ring" aria-hidden="true" />}
      <span>{source.mark}</span>
    </div>
  )
}

function Figure({ value }) {
  const quiet = value === '–'
  return (
    <span className="pc-figure" data-quiet={quiet}>
      <span aria-hidden={quiet || undefined}>{value}</span>
      {quiet ? <span className="pc-sr">none</span> : null}
    </span>
  )
}

function Result({ line }) {
  const result = matchResult(line)
  if (!result) return <span className="pc-figure" data-quiet="true"><span aria-hidden="true">–</span><span className="pc-sr">Result not recorded</span></span>
  return (
    <div className="pc-result">
      <span className="pc-outcome" data-outcome={result.outcome} aria-hidden="true">{result.outcome}</span>
      <span aria-hidden="true">{result.score}</span>
      <span className="pc-sr">{result.label}</span>
    </div>
  )
}

function Minutes({ minutes }) {
  const played = Number(minutes) || 0
  return (
    <div className="pc-minutes">
      <div className="pc-bar" aria-hidden="true"><span style={{ width: `${Math.round(minutesShare(played) * 100)}%` }} /></div>
      <div className="pc-minutes-value"><span aria-hidden="true">{played}′</span><span className="pc-sr">{played} minutes</span></div>
    </div>
  )
}

/** One line per match: a table on desktop, cards on phones. */
export function MatchLines({ lines, goalkeeper = false }) {
  const [showAll, setShowAll] = useState(false)
  if (!lines?.length) return null
  const canCollapse = lines.length > MATCH_LINES_PREVIEW + 2
  const visible = canCollapse && !showAll ? lines.slice(0, MATCH_LINES_PREVIEW) : lines
  const firstFigure = goalkeeper ? { head: 'SV', name: 'Saves', key: 'saves' } : { head: 'G', name: 'Goals', key: 'goals' }
  const secondFigure = goalkeeper ? { head: 'GC', name: 'Goals conceded', key: 'goals_conceded' } : { head: 'A', name: 'Assists', key: 'assists' }
  const figure = goalkeeper ? keeperFigure : quietFigure

  return (
    <section className="pc pc-section" style={{ gap: 16 }} aria-labelledby="pc-match-by-match" data-testid="match-lines">
      <div className="pc-matches-head">
        <h2 className="pc-h2" id="pc-match-by-match">Match by match</h2>
        <p className="pc-hint">One line per match. Where the club has confirmed, the club&apos;s figures are shown.</p>
      </div>

      <div className="pc-table" role="table" aria-labelledby="pc-match-by-match">
        <div className="pc-row pc-row--head" role="row">
          <div role="columnheader">Date</div>
          <div role="columnheader">Match</div>
          <div role="columnheader">Result</div>
          <div role="columnheader">Minutes</div>
          <div role="columnheader"><abbr title={firstFigure.name} style={{ textDecoration: 'none' }}>{firstFigure.head}</abbr></div>
          <div role="columnheader"><abbr title={secondFigure.name} style={{ textDecoration: 'none' }}>{secondFigure.head}</abbr></div>
          <div role="columnheader">Cards</div>
          <div role="columnheader">Source</div>
        </div>
        {visible.map((line) => {
          const date = matchDateParts(line.match_date)
          const venue = venueLabel(line.home_away)
          const cards = cardsLabel(line)
          const source = lineSource(line)
          return (
            <div className="pc-row" role="row" key={line.key} data-testid="match-line" data-confirmation={line.confirmation} data-self-report={line.self_report || 'none'}>
              <div className="pc-cell-stack" role="cell">
                <span className="pc-date">{date.day}</span>
                <span className="pc-sub">{date.year}</span>
              </div>
              <div className="pc-cell-stack" role="cell">
                <span className="pc-opponent">{line.opponent}{venue ? <span> · {venue}</span> : null}</span>
                {line.competition ? <span className="pc-sub">{line.competition}</span> : null}
              </div>
              <div role="cell"><Result line={line} /></div>
              <div role="cell"><Minutes minutes={line.minutes} /></div>
              <div role="cell"><Figure value={figure(line[firstFigure.key])} /></div>
              <div role="cell"><Figure value={figure(line[secondFigure.key])} /></div>
              <div role="cell" className="pc-cards" data-has={Boolean(cards && cards !== 'None')}>{cards}</div>
              <div className="pc-cell-stack" role="cell">
                <SourceMark source={source} />
                {source.lead ? <span className="pc-sub">{source.lead}</span> : null}
                {source.note ? <span className="pc-sub">{source.note}</span> : null}
              </div>
            </div>
          )
        })}
      </div>

      <ul className="pc-match-cards">
        {visible.map((line) => {
          const date = matchDateParts(line.match_date)
          const venue = venueLabel(line.home_away)
          const source = lineSource(line)
          const note = [source.lead, source.note].filter(Boolean).join(' · ')
          return (
            <li className="pc-match-card" key={line.key} data-testid="match-card" data-confirmation={line.confirmation}>
              <div className="pc-match-top">
                <div className="pc-cell-stack">
                  <span className="pc-match-when">{date.compact}{venue ? ` · ${venue}` : ''}</span>
                  <span className="pc-opponent">{line.opponent}</span>
                  {line.competition ? <span className="pc-sub">{line.competition}</span> : null}
                </div>
                <Result line={line} />
              </div>
              <Minutes minutes={line.minutes} />
              <div className="pc-match-foot">
                <span>{lineSummary(line, { goalkeeper })}</span>
                <SourceMark source={source} />
              </div>
              {note ? <p className="pc-match-note">{note}</p> : null}
            </li>
          )
        })}
      </ul>

      {canCollapse ? (
        <button type="button" className="pc-pill pc-pill--outline pc-more" aria-expanded={showAll} onClick={() => setShowAll((value) => !value)}>
          {showAll ? `Show the latest ${MATCH_LINES_PREVIEW}` : `Show all ${lines.length} matches`}
        </button>
      ) : null}
      <p className="pc-foot-hint">One card per match. Where the club has confirmed, the club&apos;s figures are shown.</p>
    </section>
  )
}

/**
 * The season block: tiles, then the sentence that says where they come from.
 * Totals are either the provider's (shown whole, labelled) or exactly the
 * merged match lines below — never both added together.
 */
export function PlayerSeason({
  season,
  lines = [],
  totals = null,
  provider = null,
  goalkeeper = false,
  frozen = false,
  minutesKnown = true,
  playerName = 'this player',
  clubColors,
  control = null,
  loading = false,
}) {
  const summary = summarizeSeason({ lines, totals, provider, goalkeeper, frozen, minutesKnown })
  const label = formatSeasonLabel(season)
  const [lead, ...rest] = summary.tiles

  return (
    <section className="pc pc-section" style={clubColorStyle(clubColors)} aria-labelledby="pc-season-title" data-testid="player-season" data-source={summary.source}>
      <div className="pc-section-head">
        <div>
          <div className="pc-kicker">This season</div>
          <h2 className="pc-season-title" id="pc-season-title">{label}<span className="pc-sr"> Totals</span></h2>
        </div>
        {control}
      </div>

      {summary.source === 'none' ? (
        <div className="pc-empty" data-testid="season-empty" aria-busy={loading || undefined}>
          <p className="pc-empty-title">{loading ? 'Loading the season…' : 'No matches recorded yet'}</p>
          {loading ? null : (
            <p className="pc-empty-text">
              Nothing has been entered for {label}. When the club confirms a match, or {playerName} adds one, it appears here with where it came from.
            </p>
          )}
        </div>
      ) : (
        <>
          <div
            className="pc-tiles"
            style={{ '--pc-tile-cols': summary.tiles.length, '--pc-tile-small-cols': Math.max(1, rest.length) }}
          >
            <Tile tile={lead} lead />
            {rest.map((tile) => <Tile key={tile.key} tile={tile} />)}
          </div>
          <p className="pc-source" data-testid="season-source">
            {summary.confirmed ? <ConfirmedTick size={18} /> : null}
            <span>
              {summary.sentence}
              {summary.avgRating != null ? ` Average rating ${summary.avgRating}.` : ''}
            </span>
          </p>
        </>
      )}
    </section>
  )
}

export default PlayerSeason
