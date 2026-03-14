import React, { useState, useEffect, useCallback } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Loader2, BarChart3, PieChart, LineChart, LayoutList, Table2, Eye } from 'lucide-react'
import { APIService } from '@/lib/api'
import { ChartPreview } from './ChartPreview'
import { cn } from '@/lib/utils'

// Available stats grouped by category
const STAT_CATEGORIES = {
  basic: {
    label: 'Basic',
    stats: [
      { key: 'minutes', label: 'Minutes Played' },
      { key: 'rating', label: 'Match Rating' },
    ],
  },
  attacking: {
    label: 'Attacking',
    stats: [
      { key: 'goals', label: 'Goals' },
      { key: 'assists', label: 'Assists' },
      { key: 'shots_total', label: 'Shots' },
      { key: 'shots_on', label: 'Shots on Target' },
    ],
  },
  passing: {
    label: 'Passing',
    stats: [
      { key: 'passes_total', label: 'Total Passes' },
      { key: 'passes_key', label: 'Key Passes' },
    ],
  },
  defending: {
    label: 'Defending',
    stats: [
      { key: 'tackles_total', label: 'Tackles' },
      { key: 'tackles_blocks', label: 'Blocks' },
      { key: 'tackles_interceptions', label: 'Interceptions' },
    ],
  },
  duels: {
    label: 'Duels',
    stats: [
      { key: 'duels_total', label: 'Total Duels' },
      { key: 'duels_won', label: 'Duels Won' },
    ],
  },
  discipline: {
    label: 'Discipline',
    stats: [
      { key: 'yellows', label: 'Yellow Cards' },
      { key: 'reds', label: 'Red Cards' },
    ],
  },
  goalkeeper: {
    label: 'Goalkeeper',
    stats: [
      { key: 'saves', label: 'Saves' },
      { key: 'goals_conceded', label: 'Goals Conceded' },
    ],
  },
}

const CHART_TYPE_OPTIONS = [
  { value: 'match_card', label: 'Match Cards', icon: LayoutList },
  { value: 'radar', label: 'Radar', icon: PieChart },
  { value: 'bar', label: 'Bar Chart', icon: BarChart3 },
  { value: 'line', label: 'Line Chart', icon: LineChart },
  { value: 'stat_table', label: 'Stats Table', icon: Table2 },
]

const DATE_RANGE_OPTIONS = [
  { value: 'week', label: 'This Week' },
  { value: 'month', label: 'Last 30 Days' },
  { value: 'season', label: 'Full Season' },
]

export function ChartBlockEditor({
  open,
  onOpenChange,
  block,
  onSave,
  playerId,
  weekRange,
}) {
  const [chartType, setChartType] = useState(block?.chart_type || 'match_card')
  const [dateRange, setDateRange] = useState(block?.chart_config?.date_range || 'week')
  const [selectedStats, setSelectedStats] = useState(
    block?.chart_config?.stat_keys || ['goals', 'assists', 'rating']
  )
  const [previewData, setPreviewData] = useState(null)
  const [loading, setLoading] = useState(false)

  // Fetch preview data when settings change
  const fetchPreview = useCallback(async () => {
    if (!playerId) return

    setLoading(true)
    try {
      const params = {
        player_id: playerId,
        chart_type: chartType,
        stat_keys: selectedStats.join(','),
        date_range: dateRange,
      }

      // Add week dates if using week range
      if (dateRange === 'week' && weekRange?.start && weekRange?.end) {
        params.week_start = weekRange.start
        params.week_end = weekRange.end
      }

      const data = await APIService.getChartData(params)
      setPreviewData(data)
    } catch (err) {
      console.error('Failed to fetch chart preview:', err)
    } finally {
      setLoading(false)
    }
  }, [playerId, chartType, selectedStats, dateRange, weekRange])

  useEffect(() => {
    if (open && playerId) {
      fetchPreview()
    }
  }, [open, fetchPreview, playerId])

  const handleToggleStat = (statKey) => {
    setSelectedStats((prev) => {
      if (prev.includes(statKey)) {
        return prev.filter((k) => k !== statKey)
      } else {
        return [...prev, statKey]
      }
    })
  }

  const handleSave = () => {
    onSave({
      chart_type: chartType,
      chart_config: {
        stat_keys: selectedStats,
        date_range: dateRange,
        player_id: playerId,
      },
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[700px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <BarChart3 className="h-5 w-5 text-primary" />
            Configure Chart
          </DialogTitle>
          <DialogDescription>
            Customize how player statistics are displayed
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Chart Type Selection */}
          <div className="space-y-3">
            <Label className="text-sm font-medium">Chart Type</Label>
            <div className="grid grid-cols-5 gap-2">
              {CHART_TYPE_OPTIONS.map((opt) => {
                const Icon = opt.icon
                return (
                  <button
                    key={opt.value}
                    type="button"
                    className={cn(
                      'flex flex-col items-center justify-center p-3 rounded-lg border-2 transition-all',
                      chartType === opt.value
                        ? 'border-primary bg-primary/5 text-primary'
                        : 'border-border hover:border-border'
                    )}
                    onClick={() => setChartType(opt.value)}
                  >
                    <Icon className="h-5 w-5 mb-1" />
                    <span className="text-xs">{opt.label}</span>
                  </button>
                )
              })}
            </div>
          </div>

          {/* Date Range */}
          <div className="space-y-3">
            <Label className="text-sm font-medium">Date Range</Label>
            <RadioGroup
              value={dateRange}
              onValueChange={setDateRange}
              className="flex gap-4"
            >
              {DATE_RANGE_OPTIONS.map((opt) => (
                <div key={opt.value} className="flex items-center space-x-2">
                  <RadioGroupItem value={opt.value} id={`range-${opt.value}`} />
                  <Label htmlFor={`range-${opt.value}`} className="text-sm cursor-pointer">
                    {opt.label}
                  </Label>
                </div>
              ))}
            </RadioGroup>
          </div>

          {/* Stat Selection (only for radar, bar, line) */}
          {['radar', 'bar', 'line', 'stat_table'].includes(chartType) && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label className="text-sm font-medium">Statistics to Display</Label>
                <Badge variant="secondary" className="text-xs">
                  {selectedStats.length} selected
                </Badge>
              </div>
              
              <Tabs defaultValue="attacking" className="w-full">
                <TabsList className="grid grid-cols-4 lg:grid-cols-7 h-auto">
                  {Object.entries(STAT_CATEGORIES).map(([key, cat]) => (
                    <TabsTrigger
                      key={key}
                      value={key}
                      className="text-xs py-1.5 px-2"
                    >
                      {cat.label}
                    </TabsTrigger>
                  ))}
                </TabsList>
                
                {Object.entries(STAT_CATEGORIES).map(([catKey, cat]) => (
                  <TabsContent key={catKey} value={catKey} className="mt-3">
                    <div className="grid grid-cols-2 gap-2">
                      {cat.stats.map((stat) => (
                        <div
                          key={stat.key}
                          className="flex items-center space-x-2"
                        >
                          <Checkbox
                            id={stat.key}
                            checked={selectedStats.includes(stat.key)}
                            onCheckedChange={() => handleToggleStat(stat.key)}
                          />
                          <Label
                            htmlFor={stat.key}
                            className="text-sm cursor-pointer"
                          >
                            {stat.label}
                          </Label>
                        </div>
                      ))}
                    </div>
                  </TabsContent>
                ))}
              </Tabs>
            </div>
          )}

          {/* Preview */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label className="text-sm font-medium flex items-center gap-2">
                <Eye className="h-4 w-4" /> Preview
              </Label>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={fetchPreview}
                disabled={loading}
              >
                {loading && <Loader2 className="h-4 w-4 mr-1 animate-spin" />}
                Refresh
              </Button>
            </div>
            
            <Card className="bg-secondary">
              <CardContent className="p-4">
                {!playerId ? (
                  <div className="text-center text-muted-foreground py-8">
                    Select a player to preview chart data
                  </div>
                ) : loading ? (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 className="h-6 w-6 animate-spin text-muted-foreground/70" />
                  </div>
                ) : (
                  <ChartPreview
                    block={{
                      ...block,
                      chart_type: chartType,
                      chart_config: {
                        stat_keys: selectedStats,
                        date_range: dateRange,
                      },
                    }}
                    playerId={playerId}
                    weekRange={weekRange}
                    previewData={previewData}
                  />
                )}
              </CardContent>
            </Card>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSave}>
            Save Configuration
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default ChartBlockEditor

