import { useState, useMemo } from 'react'
import { Badge } from '@/components/ui/badge'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion' // eslint-disable-line no-unused-vars

function sortAcademies(academies) {
  return [...academies].sort((a, b) => {
    if (a.is_homegrown !== b.is_homegrown) {
      return a.is_homegrown ? -1 : 1
    }
    return b.count - a.count
  })
}

export function OriginsList({ academies = [], onAcademyClick }) {
  const [expanded, setExpanded] = useState(false)

  const sorted = useMemo(() => sortAcademies(academies), [academies])

  if (sorted.length === 0) return null

  return (
    <div className="mt-4">
      <button
        type="button"
        onClick={() => setExpanded((prev) => !prev)}
        className="inline-flex items-center gap-1.5 text-sm text-slate-400 transition-colors hover:text-slate-200"
      >
        <ChevronDown
          className={`size-4 transition-transform duration-200 ${
            expanded ? 'rotate-180' : ''
          }`}
        />
        {expanded
          ? 'Hide feeder academies'
          : `Show all ${sorted.length} feeder academies`}
      </button>

      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            key="origins-list"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: 'easeInOut' }}
            className="overflow-hidden"
          >
            <div className="mt-3 flex flex-col gap-2">
              {sorted.map((group) => (
                <button
                  key={group.academy?.api_id ?? group.academy?.name}
                  type="button"
                  onClick={() => onAcademyClick?.(group)}
                  className="flex w-full items-center gap-3 rounded-lg border border-slate-700/50 bg-slate-800/50 p-3 text-left transition-colors hover:bg-slate-700/50 cursor-pointer"
                >
                  {/* Club logo */}
                  {group.academy?.logo ? (
                    <img
                      src={group.academy.logo}
                      alt={group.academy.name ?? ''}
                      className="size-8 shrink-0 rounded-full object-contain"
                    />
                  ) : (
                    <div className="size-8 shrink-0 rounded-full bg-slate-700" />
                  )}

                  {/* Name + badges */}
                  <div className="flex min-w-0 flex-1 items-center gap-2">
                    <span className="truncate text-sm font-medium text-slate-200">
                      {group.academy?.name ?? 'Unknown'}
                    </span>

                    {group.is_homegrown && (
                      <Badge
                        variant="outline"
                        className="border-emerald-700/50 bg-emerald-900/50 text-xs text-emerald-400"
                      >
                        Homegrown
                      </Badge>
                    )}
                  </div>

                  {/* Count */}
                  <span className="shrink-0 text-xs text-slate-400">
                    {group.count} {group.count === 1 ? 'player' : 'players'}
                  </span>

                  <ChevronRight className="size-4 shrink-0 text-slate-500" />
                </button>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export default OriginsList
