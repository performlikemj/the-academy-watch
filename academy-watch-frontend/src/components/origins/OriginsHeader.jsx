import { PieChart, Pie, Cell } from 'recharts'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

const COLORS = {
  homegrown: '#10b981',
  external: '#334155',
}

const CURRENT_SEASON =
  new Date().getFullYear() - (new Date().getMonth() < 7 ? 1 : 0)

function generateSeasons(count = 4) {
  return Array.from({ length: count }, (_, i) => {
    const year = CURRENT_SEASON - i
    return {
      value: year,
      label: `${year}/${String(year + 1).slice(2)}`,
    }
  })
}

export function OriginsHeader({ origins, season, onSeasonChange }) {
  const { squad_size = 0, homegrown_count = 0, homegrown_pct = 0, academy_breakdown = [] } =
    origins ?? {}

  const chartData = [
    { name: 'Homegrown', value: homegrown_count },
    { name: 'External', value: Math.max(0, squad_size - homegrown_count) },
  ]

  const seasons = generateSeasons()
  const pctDisplay = Math.round(homegrown_pct)

  return (
    <div className="flex flex-wrap items-center justify-between gap-4 sm:gap-6">
      {/* Donut chart */}
      <div className="relative h-16 w-16 shrink-0 sm:h-20 sm:w-20">
        <PieChart width={80} height={80} className="hidden sm:block">
          <Pie
            data={chartData}
            dataKey="value"
            cx="50%"
            cy="50%"
            innerRadius={28}
            outerRadius={36}
            startAngle={90}
            endAngle={-270}
            strokeWidth={0}
          >
            <Cell fill={COLORS.homegrown} />
            <Cell fill={COLORS.external} />
          </Pie>
        </PieChart>

        <PieChart width={64} height={64} className="block sm:hidden">
          <Pie
            data={chartData}
            dataKey="value"
            cx="50%"
            cy="50%"
            innerRadius={22}
            outerRadius={30}
            startAngle={90}
            endAngle={-270}
            strokeWidth={0}
          >
            <Cell fill={COLORS.homegrown} />
            <Cell fill={COLORS.external} />
          </Pie>
        </PieChart>

        {/* Percentage label centered over the donut */}
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-sm font-bold leading-none text-slate-100 sm:text-base">
            {pctDisplay}%
          </span>
          <span className="mt-0.5 text-[9px] leading-none text-slate-400 sm:text-[10px]">
            Homegrown
          </span>
        </div>
      </div>

      {/* Stats row */}
      <div className="flex items-center gap-5 sm:gap-8">
        <StatItem value={squad_size} label="Squad" />
        <StatItem value={homegrown_count} label="Homegrown" highlight />
        <StatItem value={academy_breakdown.length} label="Feeder Clubs" />
      </div>

      {/* Season selector */}
      <Select
        value={String(season)}
        onValueChange={(v) => onSeasonChange(Number(v))}
      >
        <SelectTrigger className="w-[7.5rem] bg-slate-800 border-slate-700 text-slate-200">
          <SelectValue placeholder="Season" />
        </SelectTrigger>
        <SelectContent>
          {seasons.map((s) => (
            <SelectItem key={s.value} value={String(s.value)}>
              {s.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}

function StatItem({ value, label, highlight = false }) {
  return (
    <div className="flex flex-col items-center gap-0.5">
      <span
        className={`text-lg font-bold leading-none sm:text-xl ${
          highlight ? 'text-emerald-400' : 'text-slate-100'
        }`}
      >
        {value}
      </span>
      <span className="text-[11px] text-slate-400 sm:text-xs">{label}</span>
    </div>
  )
}

export default OriginsHeader
