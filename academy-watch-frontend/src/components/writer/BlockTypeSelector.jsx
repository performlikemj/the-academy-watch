import React from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Type,
  BarChart3,
  PieChart,
  LineChart,
  LayoutList,
  Table2,
  Minus,
  Sparkles,
  Quote,
} from 'lucide-react'
import { cn } from '@/lib/utils'

const BLOCK_TYPES = [
  {
    type: 'text',
    label: 'Text',
    description: 'Rich text with formatting',
    icon: Type,
    color: 'bg-primary/5 text-primary border-primary/20 hover:bg-primary/10',
  },
  {
    type: 'quote',
    label: 'Quote',
    description: 'Attributed quote from a source',
    icon: Quote,
    color: 'bg-amber-50 text-amber-700 border-amber-200 hover:bg-amber-100',
  },
  {
    type: 'divider',
    label: 'Divider',
    description: 'Visual section separator',
    icon: Minus,
    color: 'bg-secondary text-foreground/80 border-border hover:bg-muted',
  },
]

const CHART_TYPES = [
  {
    chartType: 'match_card',
    label: 'Match Cards',
    description: 'Fixture results with player stats',
    icon: LayoutList,
    color: 'bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100',
  },
  {
    chartType: 'radar',
    label: 'Radar Chart',
    description: 'Multi-stat spider chart',
    icon: PieChart,
    color: 'bg-purple-50 text-purple-700 border-purple-200 hover:bg-purple-100',
  },
  {
    chartType: 'bar',
    label: 'Bar Chart',
    description: 'Compare stats across matches',
    icon: BarChart3,
    color: 'bg-orange-50 text-orange-700 border-orange-200 hover:bg-orange-100',
  },
  {
    chartType: 'line',
    label: 'Line Chart',
    description: 'Stat trends over time',
    icon: LineChart,
    color: 'bg-cyan-50 text-cyan-700 border-cyan-200 hover:bg-cyan-100',
  },
  {
    chartType: 'stat_table',
    label: 'Stats Table',
    description: 'Detailed tabular view',
    icon: Table2,
    color: 'bg-rose-50 text-rose-700 border-rose-200 hover:bg-rose-100',
  },
]

function BlockOption({ type, chartType, label, description, icon: Icon, color, onClick }) {
  return (
    <Card
      className={cn(
        'cursor-pointer transition-all border-2 hover:shadow-md',
        color
      )}
      onClick={onClick}
    >
      <CardContent className="p-4 flex items-start gap-3">
        <div className={cn('p-2 rounded-lg', color.split(' ')[0])}>
          <Icon className="h-5 w-5" />
        </div>
        <div className="flex-1 min-w-0">
          <h4 className="font-semibold text-sm">{label}</h4>
          <p className="text-xs text-muted-foreground mt-0.5">{description}</p>
        </div>
      </CardContent>
    </Card>
  )
}

export function BlockTypeSelector({ open, onOpenChange, onSelect }) {
  const handleSelect = (type, chartType = null) => {
    onSelect(type, chartType)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px] max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-primary" />
            Add Content Block
          </DialogTitle>
          <DialogDescription>
            Choose the type of content you want to add to your article
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 pt-4">
          {/* Basic blocks */}
          <div>
            <h3 className="text-sm font-medium text-foreground/80 mb-3">Content</h3>
            <div className="grid grid-cols-2 gap-3">
              {BLOCK_TYPES.map((block) => (
                <BlockOption
                  key={block.type}
                  {...block}
                  onClick={() => handleSelect(block.type)}
                />
              ))}
            </div>
          </div>

          {/* Chart blocks */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-medium text-foreground/80">Data Visualizations</h3>
              <Badge variant="secondary" className="text-xs">
                <BarChart3 className="h-3 w-3 mr-1" />
                Player Stats
              </Badge>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {CHART_TYPES.map((chart) => (
                <BlockOption
                  key={chart.chartType}
                  type="chart"
                  {...chart}
                  onClick={() => handleSelect('chart', chart.chartType)}
                />
              ))}
            </div>
          </div>

          {/* Hint */}
          <div className="text-xs text-muted-foreground bg-secondary p-3 rounded-lg">
            <strong>Tip:</strong> You can mark any block as premium to make it visible only to subscribers.
            Drag blocks to reorder them.
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

export default BlockTypeSelector

