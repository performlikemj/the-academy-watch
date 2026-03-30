import React from 'react'
import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  Tooltip,
  Legend,
} from 'recharts'
import { CHART_POSITION_COLORS, CHART_AXIS_COLOR } from '../../lib/theme-constants'

const AVG_COLOR = '#94a3b8' // slate-400

export function PlayerRadarChart({ data }) {
  // Detect league-based format (new) vs old format
  if (data?.league_name !== undefined) {
    return <LeagueRadar data={data} />
  }
  if (data?.position_group) {
    return <PercentileRadar data={data} />
  }
  return <LegacyRadar data={data} />
}

// ---------------------------------------------------------------------------
// League-based radar (current — per-90 vs league average)
// ---------------------------------------------------------------------------

function LeagueRadar({ data }) {
  const radarData = data?.data || []
  const matchesCount = data?.matches_count || 0
  const formationPosition = data?.formation_position || 'Unknown'
  const positionGroupLabel = data?.position_group_label || 'Unknown'
  const positionMatches = data?.position_matches || 0
  const leagueName = data?.league_name || 'League'
  const leaguePeers = data?.league_peers || 0
  const minMinutesMet = data?.min_minutes_met !== false
  const hasOverlay = radarData.some((d) => d.league_avg_normalized != null)

  if (!radarData.length) {
    return (
      <div className="text-center text-muted-foreground py-4 text-sm">
        No data available for radar chart
      </div>
    )
  }

  const chartData = radarData.map((item) => ({
    stat: item.label,
    playerValue: item.player_normalized || 0,
    avgValue: item.league_avg_normalized ?? null,
    playerPer90: item.player_per90,
    leagueAvgPer90: item.league_avg_per90,
    statKey: item.stat,
  }))

  const positionCategory = _groupToCategory(data.position_group)
  const chartColor = CHART_POSITION_COLORS[positionCategory] || CHART_POSITION_COLORS.Midfielder

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between flex-wrap gap-1">
        {data?.player?.name && (
          <div className="text-sm font-medium text-foreground/80">
            {data.player.name} - {matchesCount} match{matchesCount !== 1 ? 'es' : ''}
          </div>
        )}
        <div className="flex items-center gap-2">
          {formationPosition !== 'Unknown' && (
            <div
              className="text-xs px-2 py-0.5 rounded-full font-medium"
              style={{ backgroundColor: `${chartColor}20`, color: chartColor }}
            >
              {formationPosition} ({positionGroupLabel})
            </div>
          )}
        </div>
      </div>

      {!minMinutesMet && (
        <div className="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded px-2 py-1">
          Limited data — fewer than 200 minutes played.
        </div>
      )}

      <div className="h-[320px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart data={chartData} cx="50%" cy="50%" outerRadius="80%">
            <PolarGrid gridType="polygon" />
            <PolarAngleAxis
              dataKey="stat"
              tick={{ fontSize: 10, fill: CHART_AXIS_COLOR }}
            />
            <PolarRadiusAxis
              angle={30}
              domain={[0, 100]}
              tick={{ fontSize: 9, fill: CHART_AXIS_COLOR }}
              tickCount={5}
              axisLine={false}
              tickFormatter={(v) => (v === 0 ? '' : `${v}%`)}
            />
            {/* League average overlay (behind) */}
            {hasOverlay && (
              <Radar
                name={`${leagueName} Avg`}
                dataKey="avgValue"
                stroke={AVG_COLOR}
                fill={AVG_COLOR}
                fillOpacity={0.08}
                strokeWidth={1.5}
                strokeDasharray="4 3"
              />
            )}
            {/* Player layer (front) */}
            <Radar
              name="Player"
              dataKey="playerValue"
              stroke={chartColor}
              fill={chartColor}
              fillOpacity={0.35}
              strokeWidth={2}
            />
            <Tooltip
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null
                const item = payload[0]?.payload
                if (!item) return null
                return (
                  <div className="bg-card border shadow-lg rounded-lg px-3 py-2 min-w-[180px]">
                    <div className="font-semibold text-sm text-foreground mb-1">{item.stat}</div>
                    <div className="space-y-0.5 text-xs">
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Player per 90:</span>
                        <span className="font-medium">{item.playerPer90}</span>
                      </div>
                      {item.leagueAvgPer90 != null && (
                        <div className="flex justify-between text-muted-foreground/70 pt-1 border-t mt-1">
                          <span>{leagueName} avg:</span>
                          <span className="font-medium">{item.leagueAvgPer90}/90</span>
                        </div>
                      )}
                    </div>
                  </div>
                )
              }}
            />
            {hasOverlay && (
              <Legend
                wrapperStyle={{ fontSize: 11 }}
                formatter={(value) => (
                  <span className="text-xs text-muted-foreground">{value}</span>
                )}
              />
            )}
          </RadarChart>
        </ResponsiveContainer>
      </div>

      {/* Footer */}
      <div className="text-xs text-muted-foreground text-center leading-relaxed">
        {hasOverlay
          ? `Per 90 minutes vs ${leaguePeers} ${positionGroupLabel.toLowerCase()}s in ${leagueName}. 100% = best in league.`
          : leaguePeers > 0
            ? `Per 90 minutes. Limited league data (${leaguePeers} players).`
            : 'Per 90 minutes.'
        }
        {formationPosition !== 'Unknown' && positionMatches > 0 && (
          <> Most played: {formationPosition} ({positionMatches}/{matchesCount}).</>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Percentile radar (fallback if league data unavailable)
// ---------------------------------------------------------------------------

function PercentileRadar({ data }) {
  const radarData = data?.data || []
  const matchesCount = data?.matches_count || 0
  const positionGroupLabel = data?.position_group_label || 'Unknown'
  const peersCount = data?.peers_count || 0

  if (!radarData.length) {
    return <div className="text-center text-muted-foreground py-4 text-sm">No data available</div>
  }

  const chartData = radarData.map((item) => ({
    stat: item.label,
    playerPercentile: item.player_percentile || 0,
    playerPer90: item.player_per90,
  }))

  const positionCategory = _groupToCategory(data.position_group)
  const chartColor = CHART_POSITION_COLORS[positionCategory] || CHART_POSITION_COLORS.Midfielder

  return (
    <div className="space-y-2">
      {data?.player?.name && (
        <div className="text-sm font-medium text-foreground/80">
          {data.player.name} - {matchesCount} match{matchesCount !== 1 ? 'es' : ''}
        </div>
      )}
      <div className="h-[300px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart data={chartData} cx="50%" cy="50%" outerRadius="80%">
            <PolarGrid gridType="polygon" />
            <PolarAngleAxis dataKey="stat" tick={{ fontSize: 10, fill: CHART_AXIS_COLOR }} />
            <PolarRadiusAxis angle={30} domain={[0, 100]} tick={false} tickCount={5} axisLine={false} />
            <Radar name="Player" dataKey="playerPercentile" stroke={chartColor} fill={chartColor} fillOpacity={0.35} strokeWidth={2} />
          </RadarChart>
        </ResponsiveContainer>
      </div>
      <div className="text-xs text-muted-foreground text-center">
        Percentile rank vs {peersCount} {positionGroupLabel.toLowerCase()}s. 50th = median.
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Legacy radar (old normalized format)
// ---------------------------------------------------------------------------

function LegacyRadar({ data }) {
  const radarData = data?.data || []
  const matchesCount = data?.matches_count || 0
  const positionCategory = data?.position_category || 'Midfielder'

  if (!radarData.length) {
    return <div className="text-center text-muted-foreground py-4 text-sm">No data available</div>
  }

  const chartData = radarData.map((item) => ({
    stat: item.label,
    value: item.normalized || 0,
  }))

  const chartColor = CHART_POSITION_COLORS[positionCategory] || CHART_AXIS_COLOR

  return (
    <div className="space-y-2">
      {data?.player?.name && (
        <div className="text-sm font-medium text-foreground/80">
          {data.player.name} - {matchesCount} match{matchesCount !== 1 ? 'es' : ''}
        </div>
      )}
      <div className="h-[300px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart data={chartData} cx="50%" cy="50%" outerRadius="80%">
            <PolarGrid gridType="polygon" />
            <PolarAngleAxis dataKey="stat" tick={{ fontSize: 11, fill: CHART_AXIS_COLOR }} />
            <PolarRadiusAxis angle={30} domain={[0, 100]} tick={false} tickCount={5} axisLine={false} />
            <Radar name="Stats" dataKey="value" stroke={chartColor} fill={chartColor} fillOpacity={0.4} strokeWidth={2} />
          </RadarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function _groupToCategory(group) {
  return { GK: 'Goalkeeper', CB: 'Defender', FB: 'Defender', DM: 'Midfielder', CM: 'Midfielder', AM: 'Midfielder', W: 'Forward', ST: 'Forward' }[group] || 'Midfielder'
}

export default PlayerRadarChart
