import React, { useState, useCallback, useMemo } from 'react'
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragOverlay,
} from '@dnd-kit/core'
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { BlockWrapper } from './BlockWrapper'
import { BlockTypeSelector } from './BlockTypeSelector'
import { ChartBlockEditor } from './ChartBlockEditor'
import { QuoteBlockEditor } from './QuoteBlockEditor'
import { CommentaryEditor } from '../CommentaryEditor'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Eye, EyeOff, Plus, Trash2, GripVertical, Lock, Unlock, BarChart3, Type, Minus } from 'lucide-react'
import { cn } from '@/lib/utils'

// Generate unique ID for blocks
const generateBlockId = () => `block_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`

// Default empty block templates
const BLOCK_TEMPLATES = {
  text: () => ({
    id: generateBlockId(),
    type: 'text',
    content: '',
    is_premium: false,
    position: 0,
  }),
  quote: () => ({
    id: generateBlockId(),
    type: 'quote',
    quote_text: '',
    source_name: '',
    source_type: 'direct_message',
    source_platform: '',
    source_url: '',
    quote_date: '',
    is_premium: false,
    position: 0,
  }),
  chart: (chartType = 'match_card') => ({
    id: generateBlockId(),
    type: 'chart',
    chart_type: chartType,
    chart_config: {
      stat_keys: ['goals', 'assists', 'rating'],
      date_range: 'week',
    },
    is_premium: false,
    position: 0,
  }),
  divider: () => ({
    id: generateBlockId(),
    type: 'divider',
    is_premium: false,
    position: 0,
  }),
}

export function ContentBlockBuilder({ 
  blocks = [], 
  onChange, 
  playerId,
  weekRange,
  className 
}) {
  const [activeId, setActiveId] = useState(null)
  const [editingChartBlockId, setEditingChartBlockId] = useState(null)
  const [editingQuoteBlockId, setEditingQuoteBlockId] = useState(null)
  const [showBlockSelector, setShowBlockSelector] = useState(false)
  const [insertPosition, setInsertPosition] = useState(null)

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8,
      },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  )

  // Ensure blocks have valid IDs and positions
  const normalizedBlocks = useMemo(() => {
    return blocks.map((block, idx) => ({
      ...block,
      id: block.id || generateBlockId(),
      position: idx,
    }))
  }, [blocks])

  const handleDragStart = useCallback((event) => {
    setActiveId(event.active.id)
  }, [])

  const handleDragEnd = useCallback((event) => {
    const { active, over } = event
    setActiveId(null)

    if (over && active.id !== over.id) {
      const oldIndex = normalizedBlocks.findIndex((b) => b.id === active.id)
      const newIndex = normalizedBlocks.findIndex((b) => b.id === over.id)

      if (oldIndex !== -1 && newIndex !== -1) {
        const newBlocks = arrayMove(normalizedBlocks, oldIndex, newIndex).map((b, i) => ({
          ...b,
          position: i,
        }))
        onChange(newBlocks)
      }
    }
  }, [normalizedBlocks, onChange])

  const handleAddBlock = useCallback((type, chartType) => {
    const newBlock = type === 'chart' 
      ? BLOCK_TEMPLATES.chart(chartType)
      : BLOCK_TEMPLATES[type]()

    let newBlocks
    if (insertPosition !== null) {
      newBlocks = [
        ...normalizedBlocks.slice(0, insertPosition + 1),
        newBlock,
        ...normalizedBlocks.slice(insertPosition + 1),
      ]
    } else {
      newBlocks = [...normalizedBlocks, newBlock]
    }

    newBlocks = newBlocks.map((b, i) => ({ ...b, position: i }))
    onChange(newBlocks)
    setShowBlockSelector(false)
    setInsertPosition(null)

    // Open chart editor for new chart blocks
    if (type === 'chart') {
      setEditingChartBlockId(newBlock.id)
    }

    // Open quote editor for new quote blocks
    if (type === 'quote') {
      setEditingQuoteBlockId(newBlock.id)
    }
  }, [normalizedBlocks, onChange, insertPosition])

  const handleRemoveBlock = useCallback((blockId) => {
    const newBlocks = normalizedBlocks
      .filter((b) => b.id !== blockId)
      .map((b, i) => ({ ...b, position: i }))
    onChange(newBlocks)
  }, [normalizedBlocks, onChange])

  const handleUpdateBlock = useCallback((blockId, updates) => {
    const newBlocks = normalizedBlocks.map((b) =>
      b.id === blockId ? { ...b, ...updates } : b
    )
    onChange(newBlocks)
  }, [normalizedBlocks, onChange])

  const handleTogglePremium = useCallback((blockId) => {
    const newBlocks = normalizedBlocks.map((b) =>
      b.id === blockId ? { ...b, is_premium: !b.is_premium } : b
    )
    onChange(newBlocks)
  }, [normalizedBlocks, onChange])

  const handleOpenInsert = useCallback((position) => {
    setInsertPosition(position)
    setShowBlockSelector(true)
  }, [])

  const activeBlock = activeId ? normalizedBlocks.find((b) => b.id === activeId) : null
  const editingChartBlock = editingChartBlockId
    ? normalizedBlocks.find((b) => b.id === editingChartBlockId)
    : null
  const editingQuoteBlock = editingQuoteBlockId
    ? normalizedBlocks.find((b) => b.id === editingQuoteBlockId)
    : null

  return (
    <div className={cn('space-y-3', className)}>
      {/* Block list with drag and drop */}
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
      >
        <SortableContext
          items={normalizedBlocks.map((b) => b.id)}
          strategy={verticalListSortingStrategy}
        >
          {normalizedBlocks.length === 0 ? (
            <Card className="border-dashed border-2 border-border">
              <CardContent className="py-12 text-center">
                <Type className="h-10 w-10 mx-auto text-muted-foreground/70 mb-4" />
                <p className="text-muted-foreground mb-4">Start building your article</p>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setShowBlockSelector(true)}
                >
                  <Plus className="h-4 w-4 mr-2" /> Add First Block
                </Button>
              </CardContent>
            </Card>
          ) : (
            normalizedBlocks.map((block, index) => (
              <div key={block.id}>
                <BlockWrapper
                  block={block}
                  onRemove={() => handleRemoveBlock(block.id)}
                  onTogglePremium={() => handleTogglePremium(block.id)}
                  onUpdate={(updates) => handleUpdateBlock(block.id, updates)}
                  onEditChart={() => setEditingChartBlockId(block.id)}
                  onEditQuote={() => setEditingQuoteBlockId(block.id)}
                  playerId={playerId}
                  weekRange={weekRange}
                />
                
                {/* Insert button between blocks */}
                <div className="flex justify-center py-1 group">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-6 px-2 opacity-0 group-hover:opacity-100 transition-opacity"
                    onClick={() => handleOpenInsert(index)}
                  >
                    <Plus className="h-3 w-3 mr-1" /> Insert
                  </Button>
                </div>
              </div>
            ))
          )}
        </SortableContext>

        {/* Drag overlay */}
        <DragOverlay>
          {activeBlock ? (
            <Card className="opacity-90 shadow-xl border-2 border-primary">
              <CardContent className="py-3">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <GripVertical className="h-4 w-4" />
                  <span className="font-medium">
                    {activeBlock.type === 'text' && 'Text Block'}
                    {activeBlock.type === 'chart' && `${activeBlock.chart_type?.replace('_', ' ')} Chart`}
                    {activeBlock.type === 'divider' && 'Divider'}
                  </span>
                </div>
              </CardContent>
            </Card>
          ) : null}
        </DragOverlay>
      </DndContext>

      {/* Add block button at bottom */}
      {normalizedBlocks.length > 0 && (
        <Button
          type="button"
          variant="outline"
          className="w-full border-dashed"
          onClick={() => {
            setInsertPosition(null)
            setShowBlockSelector(true)
          }}
        >
          <Plus className="h-4 w-4 mr-2" /> Add Block
        </Button>
      )}

      {/* Block type selector modal */}
      <BlockTypeSelector
        open={showBlockSelector}
        onOpenChange={setShowBlockSelector}
        onSelect={handleAddBlock}
      />

      {/* Chart editor modal */}
      {editingChartBlock && (
        <ChartBlockEditor
          open={!!editingChartBlock}
          onOpenChange={(open) => !open && setEditingChartBlockId(null)}
          block={editingChartBlock}
          onSave={(updates) => {
            handleUpdateBlock(editingChartBlockId, updates)
            setEditingChartBlockId(null)
          }}
          playerId={playerId}
          weekRange={weekRange}
        />
      )}

      {/* Quote editor modal */}
      {editingQuoteBlock && (
        <QuoteBlockEditor
          open={!!editingQuoteBlock}
          onOpenChange={(open) => !open && setEditingQuoteBlockId(null)}
          block={editingQuoteBlock}
          onSave={(updates) => {
            handleUpdateBlock(editingQuoteBlockId, updates)
            setEditingQuoteBlockId(null)
          }}
        />
      )}

      {/* Summary of blocks */}
      <div className="flex flex-wrap gap-2 pt-2 border-t">
        <Badge variant="outline" className="text-xs">
          {normalizedBlocks.length} block{normalizedBlocks.length !== 1 ? 's' : ''}
        </Badge>
        {normalizedBlocks.some((b) => b.is_premium) && (
          <Badge variant="outline" className="text-xs text-amber-700 border-amber-300">
            <Lock className="h-3 w-3 mr-1" />
            {normalizedBlocks.filter((b) => b.is_premium).length} premium
          </Badge>
        )}
      </div>
    </div>
  )
}

export default ContentBlockBuilder

