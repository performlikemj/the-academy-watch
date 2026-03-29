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
import { CHART_POSITION_COLORS, CHART_AXIS_COLOR, CHART_POSITION_AVG_COLOR } from '../../lib/theme-constants'

export function PlayerRadarChart({ data }) {
  // Detect new (percentile-based) vs old (normalized) response format
  const isNewFormat = !!data?.position_group

  if (isNewFormat) {
    return <PercentileRadar data={data} />
  }

  return <LegacyRadar data={data} />
}

// ---------------------------------------------------------------------------
// New percentile-based dual-layer radar
// ---------------------------------------------------------------------------

function PercentileRadar({ data }) {
  const radarData = data?.data || []
  const matchesCount = data?.matches_count || 0
  const formationPosition = data?.formation_position || 'Unknown'
  const positionGroupLabel = data?.position_group_label || 'Unknown'
  const positionMatches = data?.position_matches || 0
  const peersCount = data?.peers_count || 0
  const minMinutesMet = data?.min_minutes_met !== false

  if (!radarData.length) {
    return (
      <div className="text-center text-muted-foreground py-4 text-sm">
        No data available for radar chart
      </div>
    )
  }

  // Transform for recharts — two data keys: playerPercentile + avgPercentile
  const chartData = radarData.map((item) => ({
    stat: item.label,
    playerPercentile: item.player_percentile || 0,
    avgPercentile: item.position_avg_percentile || 50,
    playerPer90: item.player_per90,
    positionAvgPer90: item.position_avg_per90,
    statKey: item.stat,
  }))

  // Use position group to pick color
  const positionCategory = _groupToCategory(data.position_group)
  const chartColor = CHART_POSITION_COLORS[positionCategory] || CHART_POSITION_COLORS.Midfielder

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        {data?.player?.name && (
          <div className="text-sm font-medium text-foreground/80">
            {data.player.name} - {matchesCount} match{matchesCount !== 1 ? 'es' : ''}
          </div>
        )}
        <div className="flex items-center gap-2">
          {formationPosition !== 'Unknown' && (
            <div
              className="text-xs px-2 py-0.5 rounded-full font-medium"
              style={{
                backgroundColor: `${chartColor}20`,
                color: chartColor,
              }}
            >
              {formationPosition} ({positionGroupLabel})
            </div>
          )}
          {peersCount > 0 && (
            <div className="text-xs text-muted-foreground">
              vs {peersCount} {positionGroupLabel.toLowerCase()}s
            </div>
          )}
        </div>
      </div>

      {!minMinutesMet && (
        <div className="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded px-2 py-1">
          Limited data — percentiles may not be representative.
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
              tick={false}
              tickCount={5}
              axisLine={false}
            />
            {/* Position average layer (behind) */}
            <Radar
              name={`${positionGroupLabel} Avg`}
              dataKey="avgPercentile"
              stroke={CHART_POSITION_AVG_COLOR}
              fill={CHART_POSITION_AVG_COLOR}
              fillOpacity={0.08}
              strokeWidth={1.5}
              strokeDasharray="4 3"
            />
            {/* Player layer (front) */}
            <Radar
              name="Player"
              dataKey="playerPercentile"
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
                        <span className="text-muted-foreground">Per 90:</span>
                        <span className="font-medium">{item.playerPer90}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Percentile:</span>
                        <span className="font-medium" style={{ color: chartColor }}>
                          {item.playerPercentile}{_ordinalSuffix(item.playerPercentile)}
                        </span>
                      </div>
                      <div className="flex justify-between text-muted-foreground/70 pt-1 border-t mt-1">
                        <span>{positionGroupLabel} avg:</span>
                        <span className="font-medium">{item.positionAvgPer90}/90</span>
                      </div>
                    </div>
                  </div>
                )
              }}
            />
            <Legend
              wrapperStyle={{ fontSize: 11 }}
              formatter={(value) => (
                <span className="text-xs text-muted-foreground">{value}</span>
              )}
            />
          </RadarChart>
        </ResponsiveContainer>
      </div>

      {/* Disclaimer */}
      <div className="text-xs text-muted-foreground text-center leading-relaxed">
        {formationPosition !== 'Unknown' && positionMatches > 0 && (
          <>
            Position based on most frequently played role ({formationPosition} in{' '}
            {positionMatches} of {matchesCount} starts).
          </>
        )}
        {peersCount > 0 && peersCount < 10 && (
          <> Small sample ({peersCount} peers).</>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Legacy radar (old normalized format) — kept for backward compat
// ---------------------------------------------------------------------------

function LegacyRadar({ data }) {
  const radarData = data?.data || []
  const matchesCount = data?.matches_count || 0
  const position = data?.position || 'Unknown'
  const positionCategory = data?.position_category || 'Midfielder'

  if (!radarData.length) {
    return (
      <div className="text-center text-muted-foreground py-4 text-sm">
        No data available for radar chart
      </div>
    )
  }

  const chartData = radarData.map((item) => ({
    stat: item.label,
    value: item.normalized || 0,
    avgPerGame: item.value,
    total: item.total,
    maxValue: item.max_value,
  }))

  const chartColor = CHART_POSITION_COLORS[positionCategory] || CHART_AXIS_COLOR

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        {data?.player?.name && (
          <div className="text-sm font-medium text-foreground/80">
            {data.player.name} - {matchesCount} match{matchesCount !== 1 ? 'es' : ''}
          </div>
        )}
        {position !== 'Unknown' && (
          <div
            className="text-xs px-2 py-0.5 rounded-full font-medium"
            style={{
              backgroundColor: `${chartColor}20`,
              color: chartColor,
            }}
          >
            {position} ({positionCategory})
          </div>
        )}
      </div>

      <div className="h-[300px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart data={chartData} cx="50%" cy="50%" outerRadius="80%">
            <PolarGrid gridType="polygon" />
            <PolarAngleAxis
              dataKey="stat"
              tick={{ fontSize: 11, fill: CHART_AXIS_COLOR }}
            />
            <PolarRadiusAxis
              angle={30}
              domain={[0, 100]}
              tick={false}
              tickCount={5}
              axisLine={false}
            />
            <Radar
              name="Stats"
              dataKey="value"
              stroke={chartColor}
              fill={chartColor}
              fillOpacity={0.4}
              strokeWidth={2}
            />
            <Tooltip
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null
                const item = payload[0].payload
                return (
                  <div className="bg-card border shadow-lg rounded-lg px-3 py-2 min-w-[160px]">
                    <div className="font-semibold text-sm text-foreground mb-1">{item.stat}</div>
                    <div className="space-y-0.5 text-xs">
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Per game:</span>
                        <span className="font-medium">{item.avgPerGame}</span>
                      </div>
                      {matchesCount > 1 && (
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Total:</span>
                          <span className="font-medium">{item.total}</span>
                        </div>
                      )}
                      <div className="flex justify-between text-muted-foreground/70 pt-1 border-t mt-1">
                        <span>vs {positionCategory} avg:</span>
                        <span className="font-medium" style={{ color: chartColor }}>
                          {item.value}%
                        </span>
                      </div>
                      <div className="flex justify-between text-muted-foreground/70">
                        <span>Expected max:</span>
                        <span>{item.maxValue}/game</span>
                      </div>
                    </div>
                  </div>
                )
              }}
            />
          </RadarChart>
        </ResponsiveContainer>
      </div>

      <div className="text-xs text-muted-foreground text-center">
        Values normalized to % of expected {positionCategory.toLowerCase()} performance per game
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function _groupToCategory(group) {
  const map = {
    GK: 'Goalkeeper',
    CB: 'Defender',
    FB: 'Defender',
    DM: 'Midfielder',
    CM: 'Midfielder',
    AM: 'Midfielder',
    W: 'Forward',
    ST: 'Forward',
  }
  return map[group] || 'Midfielder'
}

function _ordinalSuffix(n) {
  const s = ['th', 'st', 'nd', 'rd']
  const v = n % 100
  return s[(v - 20) % 10] || s[v] || s[0]
}

export default PlayerRadarChart
