import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import { SlidersHorizontal } from 'lucide-react'

/**
 * Bottom-sheet home for the Scout Desk filters on mobile (< sm). On desktop
 * these controls stay inline; on a phone they'd crowd the header, so a sticky
 * "Filters" pill opens this sheet. Filters apply live (no Apply button) — the
 * sheet is a container for the same state the desktop selects drive, so query
 * params, leaderboards and results all stay in sync.
 */
export function ScoutFilterSheet({
  open,
  onOpenChange,
  phase,
  agePresets,
  agePreset,
  onAgePresetChange,
  position,
  onPositionChange,
  status,
  onStatusChange,
  sort,
  onSortChange,
  sortOptions,
  activeCount,
  onReset,
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="bottom"
        className="max-h-[85vh] gap-0 overflow-y-auto rounded-t-2xl px-4 pb-[calc(1.5rem+env(safe-area-inset-bottom))] pt-2"
      >
        {/* Grabber */}
        <div aria-hidden className="mx-auto mb-2 h-1.5 w-10 shrink-0 rounded-full bg-border" />
        <SheetHeader className="px-0 pt-0">
          <SheetTitle className="flex items-center gap-2">
            <SlidersHorizontal className="h-4 w-4 text-primary" />
            Filters
          </SheetTitle>
          <SheetDescription>Narrow the ranked list by age, position, status and sort order.</SheetDescription>
        </SheetHeader>

        <div className="space-y-5 py-4">
          {/* Age band */}
          <div className="space-y-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Age band</p>
            <div className="flex flex-wrap gap-2">
              {agePresets.map((preset) => (
                <button
                  key={preset.key}
                  type="button"
                  onClick={() => onAgePresetChange(preset.key)}
                  className={`min-h-11 rounded-full px-4 text-sm font-semibold transition-colors ${
                    agePreset === preset.key
                      ? 'bg-primary text-primary-foreground shadow-sm'
                      : 'border border-border bg-card text-foreground/80 hover:bg-secondary active:bg-secondary'
                  }`}
                >
                  {preset.label}
                </button>
              ))}
            </div>
          </div>

          {/* Position — only meaningful on the All phase */}
          {phase === 'all' && (
            <label className="block space-y-2">
              <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Position</span>
              <Select value={position} onValueChange={onPositionChange}>
                <SelectTrigger className="h-11 w-full" aria-label="Filter by position">
                  <SelectValue placeholder="Position" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All positions</SelectItem>
                  <SelectItem value="Goalkeeper">Goalkeeper</SelectItem>
                  <SelectItem value="Defender">Defender</SelectItem>
                  <SelectItem value="Midfielder">Midfielder</SelectItem>
                  <SelectItem value="Attacker">Attacker</SelectItem>
                </SelectContent>
              </Select>
            </label>
          )}

          {/* Status */}
          <label className="block space-y-2">
            <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Pathway status</span>
            <Select value={status} onValueChange={onStatusChange}>
              <SelectTrigger className="h-11 w-full" aria-label="Filter by pathway status">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                <SelectItem value="academy">Academy</SelectItem>
                <SelectItem value="on_loan">On loan</SelectItem>
                <SelectItem value="first_team">First team</SelectItem>
                <SelectItem value="sold">Sold</SelectItem>
                <SelectItem value="released">Released</SelectItem>
                <SelectItem value="left">Left</SelectItem>
              </SelectContent>
            </Select>
          </label>

          {/* Sort */}
          <label className="block space-y-2">
            <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Sort by</span>
            <Select value={sort} onValueChange={onSortChange}>
              <SelectTrigger className="h-11 w-full" aria-label="Sort by">
                <SelectValue placeholder="Sort by" />
              </SelectTrigger>
              <SelectContent>
                {sortOptions.map((option) => (
                  <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </label>
        </div>

        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            className="h-11 flex-1"
            onClick={onReset}
            disabled={!activeCount}
          >
            Reset
          </Button>
          <Button className="h-11 flex-1" onClick={() => onOpenChange(false)}>
            Show results
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  )
}

export default ScoutFilterSheet
