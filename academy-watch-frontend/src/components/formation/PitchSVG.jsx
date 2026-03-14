import { useState, useRef } from 'react'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar'

/**
 * Football pitch with HTML overlay for drag-and-drop.
 *
 * SVG handles pitch markings only. All interactive elements (drop zones,
 * player cards) are HTML divs positioned absolutely over the SVG via
 * percentage-based coordinates — avoids foreignObject drag-and-drop issues.
 */
export function PitchSVG({ slots, placements, onDrop, onPlayerClick }) {
  const [dragOverSlot, setDragOverSlot] = useState(null)
  const containerRef = useRef(null)

  const handleDragOver = (e, slotKey) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    setDragOverSlot(slotKey)
  }

  const handleDragLeave = () => setDragOverSlot(null)

  const handleDrop = (e, slotKey) => {
    e.preventDefault()
    setDragOverSlot(null)
    try {
      const data = JSON.parse(e.dataTransfer.getData('application/json'))
      onDrop(slotKey, data)
    } catch { /* ignore */ }
  }

  return (
    <div className="flex-1 min-w-0">
      <div
        ref={containerRef}
        className="relative w-full max-w-[520px] mx-auto select-none"
        style={{ aspectRatio: '68 / 105' }}
      >
        {/* SVG pitch markings only */}
        <svg
          viewBox="0 0 68 105"
          className="absolute inset-0 w-full h-full"
          preserveAspectRatio="xMidYMid meet"
        >
          {/* Grass background with subtle stripe pattern */}
          <defs>
            <pattern id="grass" width="68" height="10.5" patternUnits="userSpaceOnUse">
              <rect width="68" height="5.25" fill="#2e8b4a" />
              <rect y="5.25" width="68" height="5.25" fill="#2a7f44" />
            </pattern>
          </defs>
          <rect x="0" y="0" width="68" height="105" rx="1.5" fill="url(#grass)" />

          {/* Pitch markings */}
          <g stroke="rgba(255,255,255,0.55)" strokeWidth="0.25" fill="none">
            {/* Outline */}
            <rect x="2" y="2" width="64" height="101" />
            {/* Halfway line */}
            <line x1="2" y1="52.5" x2="66" y2="52.5" />
            {/* Centre circle */}
            <circle cx="34" cy="52.5" r="9.15" />
            <circle cx="34" cy="52.5" r="0.4" fill="rgba(255,255,255,0.55)" />

            {/* Bottom penalty area (GK end) */}
            <rect x="13.84" y="84.5" width="40.32" height="18.5" />
            <rect x="24.84" y="96.5" width="18.32" height="6.5" />
            <circle cx="34" cy="92" r="0.35" fill="rgba(255,255,255,0.55)" />
            <path d="M 22 84.5 A 9.15 9.15 0 0 1 46 84.5" />

            {/* Top penalty area */}
            <rect x="13.84" y="2" width="40.32" height="18.5" />
            <rect x="24.84" y="2" width="18.32" height="6.5" />
            <circle cx="34" cy="13" r="0.35" fill="rgba(255,255,255,0.55)" />
            <path d="M 22 20.5 A 9.15 9.15 0 0 0 46 20.5" />

            {/* Corner arcs */}
            <path d="M 2 3.5 A 1.5 1.5 0 0 0 3.5 2" />
            <path d="M 64.5 2 A 1.5 1.5 0 0 0 66 3.5" />
            <path d="M 3.5 103 A 1.5 1.5 0 0 0 2 101.5" />
            <path d="M 66 101.5 A 1.5 1.5 0 0 0 64.5 103" />
          </g>
        </svg>

        {/* HTML overlay for interactive player slots */}
        {slots.map((slot) => {
          const player = placements[slot.key]
          const isOver = dragOverSlot === slot.key

          return (
            <div
              key={slot.key}
              className="absolute"
              style={{
                left: `${slot.x}%`,
                top: `${slot.y}%`,
                transform: 'translate(-50%, -50%)',
                width: '72px',
                zIndex: isOver ? 20 : 10,
              }}
              onDragOver={(e) => handleDragOver(e, slot.key)}
              onDragLeave={handleDragLeave}
              onDrop={(e) => handleDrop(e, slot.key)}
            >
              {player ? (
                <PlacedPlayer
                  player={player}
                  slotKey={slot.key}
                  onClick={() => onPlayerClick?.(player, slot.key)}
                />
              ) : (
                <EmptySlot label={slot.label} isOver={isOver} />
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function PlacedPlayer({ player, slotKey, onClick }) {
  const surname = (player.player_name || player.name || '').split(' ').pop()
  const goals = player.goals || 0
  const apps = player.appearances || 0

  return (
    <div
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData('application/json', JSON.stringify({
          source: 'pitch',
          slotKey,
          player_id: player.player_id || player.id,
        }))
        e.dataTransfer.effectAllowed = 'move'
      }}
      onClick={onClick}
      className="flex flex-col items-center gap-0.5 cursor-grab active:cursor-grabbing group"
    >
      <div className="relative">
        <Avatar className="h-10 w-10 border-2 border-white shadow-lg ring-2 ring-black/20 group-hover:ring-white/60 transition-all">
          <AvatarImage src={player.photo_url || player.photo} alt={surname} />
          <AvatarFallback className="text-xs bg-white text-foreground/80 font-bold">
            {surname.slice(0, 2).toUpperCase()}
          </AvatarFallback>
        </Avatar>
        {goals > 0 && (
          <span className="absolute -top-1 -right-1 bg-yellow-400 text-black text-[8px] font-bold rounded-full h-4 w-4 flex items-center justify-center shadow">
            {goals}
          </span>
        )}
      </div>
      <span className="text-[11px] font-bold text-white text-center leading-tight drop-shadow-[0_1px_3px_rgba(0,0,0,0.9)] max-w-[68px] truncate">
        {surname}
      </span>
      {apps > 0 && (
        <span className="text-[9px] text-white/70 leading-tight drop-shadow-[0_1px_1px_rgba(0,0,0,0.7)]">
          {apps} apps
        </span>
      )}
    </div>
  )
}

function EmptySlot({ label, isOver }) {
  return (
    <div className="flex flex-col items-center gap-1">
      <div
        className={`h-10 w-10 rounded-full border-2 border-dashed flex items-center justify-center transition-all ${
          isOver
            ? 'border-white bg-white/25 scale-110'
            : 'border-white/40 bg-white/5'
        }`}
      >
        <span className={`text-[10px] font-semibold transition-colors ${isOver ? 'text-white' : 'text-white/50'}`}>
          {label}
        </span>
      </div>
    </div>
  )
}
