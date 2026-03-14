import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { BenchPlayer } from './BenchPlayer'
import { getPositionGroup } from '@/lib/formation-presets'

const GROUP_ORDER = ['Goalkeeper', 'Defender', 'Midfielder', 'Forward', 'Unknown']

export function BenchSidebar({ players, onDropFromPitch }) {
  const [collapsed, setCollapsed] = useState({})

  const groups = {}
  for (const g of GROUP_ORDER) groups[g] = []
  for (const p of players) {
    const g = getPositionGroup(p.position)
    if (!groups[g]) groups[g] = []
    groups[g].push(p)
  }

  const toggle = (group) => setCollapsed((prev) => ({ ...prev, [group]: !prev[group] }))

  return (
    <div
      className="w-64 shrink-0 border rounded-lg bg-card overflow-y-auto max-h-[700px]"
      onDragOver={(e) => {
        e.preventDefault()
        e.dataTransfer.dropEffect = 'move'
      }}
      onDrop={(e) => {
        e.preventDefault()
        try {
          const data = JSON.parse(e.dataTransfer.getData('application/json'))
          if (data.source === 'pitch' && data.slotKey) {
            onDropFromPitch(data.slotKey)
          }
        } catch { /* ignore bad drag data */ }
      }}
    >
      <div className="p-3 border-b">
        <h3 className="text-sm font-semibold">Bench</h3>
        <p className="text-xs text-muted-foreground">{players.length} players available</p>
      </div>
      <div className="p-2 space-y-1">
        {GROUP_ORDER.map((group) => {
          const list = groups[group]
          if (!list || list.length === 0) return null
          const isCollapsed = collapsed[group]
          return (
            <div key={group}>
              <button
                onClick={() => toggle(group)}
                className="flex items-center gap-1 w-full text-left px-1 py-1 text-xs font-semibold text-muted-foreground hover:text-foreground"
              >
                {isCollapsed ? <ChevronRight className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                {group}s ({list.length})
              </button>
              {!isCollapsed && (
                <div className="space-y-0.5 ml-1">
                  {list.map((p) => (
                    <BenchPlayer key={p.player_id || p.id} player={p} />
                  ))}
                </div>
              )}
            </div>
          )
        })}
        {players.length === 0 && (
          <p className="text-xs text-muted-foreground text-center py-4">All players placed</p>
        )}
      </div>
    </div>
  )
}
