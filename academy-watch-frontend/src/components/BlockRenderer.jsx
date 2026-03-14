import React, { useState, useEffect } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Lock, Loader2, ExternalLink } from 'lucide-react'
import { APIService } from '@/lib/api'
import { 
  MatchPerformanceCards, 
  PlayerRadarChart, 
  PlayerBarChart, 
  PlayerLineChart, 
  PlayerStatTable 
} from '@/components/charts'
import { cn } from '@/lib/utils'
import { formatTextToHtml } from '@/lib/formatText'

// Render a single chart block
function ChartBlock({ block, playerId, weekRange }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Use player_id from props OR from block's chart_config (for intro/summary commentaries)
  const effectivePlayerId = playerId || block?.chart_config?.player_id

  useEffect(() => {
    const fetchData = async () => {
      if (!effectivePlayerId || !block?.chart_type) {
        setLoading(false)
        return
      }

      setLoading(true)
      try {
        const params = {
          player_id: effectivePlayerId,
          chart_type: block.chart_type,
          stat_keys: block.chart_config?.stat_keys?.join(',') || 'goals,assists,rating',
          date_range: block.chart_config?.date_range || 'week',
        }

        if (params.date_range === 'week' && weekRange?.start && weekRange?.end) {
          params.week_start = weekRange.start
          params.week_end = weekRange.end
        }

        const result = await APIService.getChartData(params)
        setData(result)
      } catch (err) {
        console.error('Failed to fetch chart data:', err)
        setError('Failed to load chart')
      } finally {
        setLoading(false)
      }
    }

    fetchData()
  }, [block, effectivePlayerId, weekRange])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground/70" />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="text-center text-muted-foreground py-4 text-sm">
        {error || 'No chart data available'}
      </div>
    )
  }

  switch (block.chart_type) {
    case 'match_card':
      return <MatchPerformanceCards data={data} />
    case 'radar':
      return <PlayerRadarChart data={data} />
    case 'bar':
      return <PlayerBarChart data={data} />
    case 'line':
      return <PlayerLineChart data={data} />
    case 'stat_table':
      return <PlayerStatTable data={data} />
    default:
      return <div className="text-muted-foreground">Unknown chart type</div>
  }
}

// Quote attribution helper
function QuoteAttribution({ block }) {
  const { source_name, source_type, source_platform, source_url, quote_date } = block

  // Format date
  let dateStr = ''
  if (quote_date) {
    try {
      const [year, month] = quote_date.split('-')
      const monthNames = [
        'Jan',
        'Feb',
        'Mar',
        'Apr',
        'May',
        'Jun',
        'Jul',
        'Aug',
        'Sep',
        'Oct',
        'Nov',
        'Dec',
      ]
      dateStr = ` (${monthNames[parseInt(month) - 1]} ${year})`
    } catch {
      dateStr = ` (${quote_date})`
    }
  }

  if (source_type === 'public_link' && source_url) {
    return (
      <>
        <a
          href={source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-primary hover:underline inline-flex items-center gap-1"
        >
          {source_name}
          <ExternalLink className="h-3 w-3" />
        </a>
        {dateStr}
      </>
    )
  }

  if (source_type === 'direct_message') {
    const platform = source_platform ? `${source_platform} DM` : 'DM'
    return (
      <span>
        {source_name}, via {platform}
        {dateStr}
      </span>
    )
  }

  if (source_type === 'email') {
    return (
      <span>
        {source_name}, via email{dateStr}
      </span>
    )
  }

  if (source_type === 'personal') {
    return (
      <span>
        {source_name}, speaking to The Academy Watch{dateStr}
      </span>
    )
  }

  if (source_type === 'anonymous') {
    return <span>according to sources{dateStr}</span>
  }

  return (
    <span>
      {source_name}
      {dateStr}
    </span>
  )
}

// Locked premium block placeholder
function LockedBlock({ authorName, authorId, onSubscribe }) {
  return (
    <Card className="border-dashed border-2 border-amber-200 bg-amber-50/50">
      <CardContent className="py-8 text-center">
        <Lock className="h-8 w-8 text-amber-500 mx-auto mb-3" />
        <p className="text-foreground/80 font-medium mb-2">
          Premium Content
        </p>
        <p className="text-sm text-muted-foreground mb-4">
          Subscribe to {authorName || 'this writer'} to unlock this section
        </p>
        {onSubscribe && (
          <Button 
            onClick={onSubscribe}
            className="bg-amber-600 hover:bg-amber-700 text-white"
          >
            Subscribe to Unlock
          </Button>
        )}
      </CardContent>
    </Card>
  )
}

// Main BlockRenderer component
export function BlockRenderer({ 
  blocks, 
  isSubscribed = false, 
  playerId,
  weekRange,
  authorName,
  authorId,
  onSubscribe,
  className 
}) {
  if (!blocks || blocks.length === 0) {
    return null
  }

  return (
    <div className={cn('space-y-4', className)}>
      {blocks.map((block, index) => {
        // Check if block is premium and user is not subscribed
        const blockLocked = block.is_premium && !isSubscribed

        if (blockLocked) {
          return (
            <LockedBlock 
              key={block.id || index}
              authorName={authorName}
              authorId={authorId}
              onSubscribe={onSubscribe}
            />
          )
        }

        switch (block.type) {
          case 'text':
            return (
              <div 
                key={block.id || index}
                className="prose prose-stone max-w-none
                  prose-headings:text-foreground prose-headings:font-bold
                  prose-p:text-foreground/80 prose-p:leading-relaxed prose-p:my-2
                  prose-ul:my-2 prose-ul:pl-5 prose-li:my-1
                  prose-strong:text-foreground
                  prose-a:text-violet-600 prose-a:no-underline hover:prose-a:underline"
                dangerouslySetInnerHTML={{ __html: formatTextToHtml(block.content) }}
              />
            )

          case 'chart':
            return (
              <Card key={block.id || index} className="overflow-hidden">
                <CardContent className="p-4">
                  <ChartBlock 
                    block={block} 
                    playerId={playerId}
                    weekRange={weekRange}
                  />
                </CardContent>
              </Card>
            )

          case 'divider':
            return (
              <hr
                key={block.id || index}
                className="border-t-2 border-border my-6"
              />
            )

          case 'quote':
            return (
              <blockquote
                key={block.id || index}
                className="border-l-4 border-primary pl-4 py-3 my-4 bg-primary/5 rounded-r"
              >
                <p className="text-foreground italic text-lg">"{block.quote_text}"</p>
                <footer className="mt-2 text-sm text-muted-foreground flex items-center gap-1">
                  <span>—</span>
                  <QuoteAttribution block={block} />
                </footer>
              </blockquote>
            )

          default:
            return null
        }
      })}
    </div>
  )
}

export default BlockRenderer

