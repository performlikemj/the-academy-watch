import { useRef, useState, useCallback, useEffect } from 'react'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import { AlertCircle } from 'lucide-react'
import { cn } from '@/lib/utils'

const CHART_COLORS = [
  'var(--chart-1, #2563eb)',
  'var(--chart-2, #10b981)',
  'var(--chart-3, #f59e0b)',
  'var(--chart-4, #ef4444)',
  'var(--chart-5, #8b5cf6)',
]

export function AnalysisResultCard({ data, expanded }) {
  if (!data) return null

  const { result_type, display } = data

  if (result_type === 'error') {
    return <ErrorCard />
  }

  // Route to the right renderer based on display hint
  if (display === 'bar_chart' && result_type === 'table') {
    return <BarChartCard data={data} expanded={expanded} />
  }
  if (display === 'line_chart' && result_type === 'table') {
    return <LineChartCard data={data} expanded={expanded} />
  }
  if (display === 'number' || result_type === 'scalar') {
    return <NumberCard data={data} />
  }
  if (display === 'list' || result_type === 'list') {
    return <ListCard data={data} />
  }
  if (result_type === 'table') {
    return <TableCard data={data} />
  }
  if (result_type === 'dict') {
    return <DictCard data={data} />
  }

  return <ErrorCard />
}

/* ─── Metadata Bar ────────────────────────────────────────────────── */

function MetaBar({ data }) {
  const description = data.meta?.description
  if (!description) return null

  return (
    <div className="flex items-center gap-2 px-3 py-1.5 border-b text-xs text-muted-foreground">
      <span className="truncate">{description}</span>
      {data.total_rows != null && (
        <span className="shrink-0 tabular-nums text-muted-foreground/70">
          {data.total_rows.toLocaleString()} rows
        </span>
      )}
    </div>
  )
}

/* ─── Table ───────────────────────────────────────────────────────── */

function TableCard({ data }) {
  const { columns = [], rows = [], total_rows, truncated } = data
  const scrollRef = useRef(null)
  const [canScrollLeft, setCanScrollLeft] = useState(false)
  const [canScrollRight, setCanScrollRight] = useState(false)

  const updateScroll = useCallback(() => {
    const el = scrollRef.current
    if (!el) return
    setCanScrollLeft(el.scrollLeft > 4)
    setCanScrollRight(el.scrollLeft < el.scrollWidth - el.clientWidth - 4)
  }, [])

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    updateScroll()
    el.addEventListener('scroll', updateScroll, { passive: true })
    const ro = new ResizeObserver(updateScroll)
    ro.observe(el)
    return () => {
      el.removeEventListener('scroll', updateScroll)
      ro.disconnect()
    }
  }, [rows.length, updateScroll])

  if (!rows.length) {
    return (
      <Card>
        <CardContent className="p-3 text-sm text-muted-foreground text-center">
          No data found
        </CardContent>
      </Card>
    )
  }

  const isTall = rows.length > 15

  return (
    <Card>
      <CardContent className="p-0">
        <MetaBar data={data} />
        <div className="relative rounded-lg">
          {canScrollLeft && (
            <div className="absolute left-0 top-0 bottom-0 w-6 bg-gradient-to-r from-background to-transparent z-10 pointer-events-none rounded-l-lg" />
          )}
          {canScrollRight && (
            <div className="absolute right-0 top-0 bottom-0 w-6 bg-gradient-to-l from-background to-transparent z-10 pointer-events-none rounded-r-lg" />
          )}
          <div
            ref={scrollRef}
            className={cn(
              'overflow-x-auto overflow-y-hidden overscroll-x-contain',
              isTall && 'max-h-[400px] !overflow-y-auto',
            )}
          >
            <Table>
              <TableHeader className={cn(isTall && 'sticky top-0 z-20')}>
                <TableRow className="bg-muted/50">
                  {columns.map((col) => (
                    <TableHead key={col} className="text-xs font-semibold whitespace-nowrap">
                      {col}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row, i) => (
                  <TableRow key={i} className="hover:bg-muted/30">
                    {row.map((cell, j) => (
                      <TableCell
                        key={j}
                        className={cn(
                          'text-xs whitespace-nowrap',
                          typeof cell === 'number' && 'tabular-nums text-right',
                          columns[j]?.toLowerCase().includes('goal') && cell > 0 && 'font-bold text-emerald-700',
                          columns[j]?.toLowerCase().includes('assist') && cell > 0 && 'font-bold text-amber-700',
                        )}
                      >
                        {cell ?? '\u2013'}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
        {truncated && (
          <div className="px-3 py-1.5 text-xs text-muted-foreground border-t">
            Showing 100 of {total_rows.toLocaleString()} rows
          </div>
        )}
      </CardContent>
    </Card>
  )
}

/* ─── Bar Chart ───────────────────────────────────────────────────── */

function BarChartCard({ data, expanded }) {
  const { columns = [], rows = [] } = data

  if (!rows.length || columns.length < 2) {
    return <ErrorCard />
  }

  const chartData = rows.map((row) => {
    const obj = {}
    columns.forEach((col, i) => {
      obj[col] = row[i]
    })
    return obj
  })

  const labelKey = columns[0]
  const dataKeys = columns.slice(1)
  const chartHeight = expanded ? 350 : 250

  return (
    <Card>
      <MetaBar data={data} />
      <CardContent className="p-3">
        <div className="w-full" style={{ height: chartHeight }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-border/50" />
              <XAxis
                dataKey={labelKey}
                tick={{ fontSize: 11 }}
                className="fill-muted-foreground"
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                tick={{ fontSize: 11 }}
                className="fill-muted-foreground"
                tickLine={false}
                axisLine={false}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'hsl(var(--background))',
                  border: '1px solid hsl(var(--border))',
                  borderRadius: '8px',
                  boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)',
                  fontSize: 12,
                }}
              />
              {dataKeys.length > 1 && (
                <Legend
                  wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
                  iconType="circle"
                  iconSize={8}
                />
              )}
              {dataKeys.map((key, i) => (
                <Bar
                  key={key}
                  dataKey={key}
                  fill={CHART_COLORS[i % CHART_COLORS.length]}
                  radius={[4, 4, 0, 0]}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  )
}

/* ─── Line Chart ──────────────────────────────────────────────────── */

function LineChartCard({ data, expanded }) {
  const { columns = [], rows = [] } = data

  if (!rows.length || columns.length < 2) {
    return <ErrorCard />
  }

  const chartData = rows.map((row) => {
    const obj = {}
    columns.forEach((col, i) => {
      obj[col] = row[i]
    })
    return obj
  })

  const labelKey = columns[0]
  const dataKeys = columns.slice(1)
  const chartHeight = expanded ? 350 : 250

  return (
    <Card>
      <MetaBar data={data} />
      <CardContent className="p-3">
        <div className="w-full" style={{ height: chartHeight }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-border/50" />
              <XAxis
                dataKey={labelKey}
                tick={{ fontSize: 11 }}
                className="fill-muted-foreground"
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                tick={{ fontSize: 11 }}
                className="fill-muted-foreground"
                tickLine={false}
                axisLine={false}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'hsl(var(--background))',
                  border: '1px solid hsl(var(--border))',
                  borderRadius: '8px',
                  boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)',
                  fontSize: 12,
                }}
              />
              {dataKeys.length > 1 && (
                <Legend
                  wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
                  iconType="circle"
                  iconSize={8}
                />
              )}
              {dataKeys.map((key, i) => (
                <Line
                  key={key}
                  type="monotone"
                  dataKey={key}
                  stroke={CHART_COLORS[i % CHART_COLORS.length]}
                  strokeWidth={2}
                  dot={{ r: 3, fill: CHART_COLORS[i % CHART_COLORS.length] }}
                  activeDot={{ r: 5 }}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  )
}

/* ─── Number ──────────────────────────────────────────────────────── */

function NumberCard({ data }) {
  const value = data.value ?? data.rows?.[0]?.[0] ?? '\u2013'
  const label = data.columns?.[0]
  const isNumeric = typeof value === 'number'

  const formatted = isNumeric
    ? value.toLocaleString(undefined, { maximumFractionDigits: 2 })
    : value

  return (
    <Card>
      <CardContent className="p-4 text-center">
        <div className={cn(
          isNumeric
            ? 'text-3xl font-bold tabular-nums'
            : 'text-sm text-muted-foreground break-words'
        )}>
          {formatted}
        </div>
        {label && (
          <div className="text-sm text-muted-foreground mt-1">{label}</div>
        )}
      </CardContent>
    </Card>
  )
}

/* ─── List ────────────────────────────────────────────────────────── */

function ListCard({ data }) {
  const items = data.items || []

  if (!items.length) {
    return (
      <Card>
        <CardContent className="p-3 text-sm text-muted-foreground text-center">
          No items found
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardContent className="p-3">
        <ol className="space-y-1.5">
          {items.map((item, i) => (
            <li key={i} className="flex items-start gap-2 text-sm">
              <Badge variant="outline" className="shrink-0 tabular-nums text-xs min-w-[1.5rem] justify-center">
                {i + 1}
              </Badge>
              <span className="min-w-0 break-words">{String(item)}</span>
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  )
}

/* ─── Dict ────────────────────────────────────────────────────────── */

function DictCard({ data }) {
  const entries = Object.entries(data.data || {})

  if (!entries.length) {
    return (
      <Card>
        <CardContent className="p-3 text-sm text-muted-foreground text-center">
          No data found
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardContent className="p-3">
        <dl className="space-y-1">
          {entries.map(([key, val]) => (
            <div key={key} className="flex items-baseline gap-2 text-sm">
              <dt className="text-muted-foreground shrink-0">{key}:</dt>
              <dd className="font-medium tabular-nums min-w-0 break-words">
                {typeof val === 'number' ? val.toLocaleString() : String(val ?? '\u2013')}
              </dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  )
}

/* ─── Error ───────────────────────────────────────────────────────── */

function ErrorCard() {
  return (
    <Card className="border-destructive/30">
      <CardContent className="p-3 flex items-start gap-2">
        <AlertCircle className="h-4 w-4 text-destructive shrink-0 mt-0.5" aria-hidden="true" />
        <p className="text-sm text-destructive min-w-0 break-words">
          Something went wrong. Try rephrasing your question.
        </p>
      </CardContent>
    </Card>
  )
}
