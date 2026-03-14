import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Save, Trash2, Loader2, Wand2, Eraser, Share2 } from 'lucide-react'
import { FORMATION_OPTIONS } from '@/lib/formation-presets'

export function FormationHeader({
  formationType,
  onFormationChange,
  formationName,
  onNameChange,
  savedFormations,
  activeFormationId,
  onLoad,
  onSave,
  onDelete,
  onAutoSuggest,
  isDirty,
  saving,
  mode = 'admin',
  onClear,
  onShare,
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {/* Formation type selector */}
      <Select value={formationType} onValueChange={onFormationChange}>
        <SelectTrigger className="w-[120px]">
          <SelectValue placeholder="Formation" />
        </SelectTrigger>
        <SelectContent>
          {FORMATION_OPTIONS.map((f) => (
            <SelectItem key={f} value={f}>{f}</SelectItem>
          ))}
        </SelectContent>
      </Select>

      {mode === 'admin' && (
        <>
          {/* Formation name */}
          <Input
            value={formationName}
            onChange={(e) => onNameChange(e.target.value)}
            placeholder="Formation name..."
            className="w-[180px]"
          />

          {/* Load saved formation */}
          {savedFormations?.length > 0 && (
            <Select value={activeFormationId ? String(activeFormationId) : ''} onValueChange={(v) => onLoad(Number(v))}>
              <SelectTrigger className="w-[160px]">
                <SelectValue placeholder="Load saved..." />
              </SelectTrigger>
              <SelectContent>
                {savedFormations.map((f) => (
                  <SelectItem key={f.id} value={String(f.id)}>{f.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </>
      )}

      <div className="flex items-center gap-1.5">
        {/* Auto-suggest */}
        <Button variant="outline" size="sm" onClick={onAutoSuggest} title="Auto-place players by position">
          <Wand2 className="h-4 w-4 mr-1" />
          Auto
        </Button>

        {mode === 'admin' && (
          <>
            {/* Save */}
            <Button onClick={onSave} disabled={saving || !formationName?.trim()} size="sm">
              {saving ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Save className="h-4 w-4 mr-1" />}
              Save
              {isDirty && <span className="ml-1 h-2 w-2 rounded-full bg-orange-400 inline-block" />}
            </Button>

            {/* Delete */}
            {activeFormationId && (
              <Button variant="destructive" size="sm" onClick={onDelete}>
                <Trash2 className="h-4 w-4" />
              </Button>
            )}
          </>
        )}

        {mode === 'public' && (
          <>
            {/* Clear */}
            {onClear && (
              <Button variant="outline" size="sm" onClick={onClear} title="Clear all placements">
                <Eraser className="h-4 w-4 mr-1" />
                Clear
              </Button>
            )}

            {/* Share */}
            {onShare && (
              <Button variant="outline" size="sm" onClick={onShare} title="Copy share link">
                <Share2 className="h-4 w-4 mr-1" />
                Share
              </Button>
            )}
          </>
        )}
      </div>
    </div>
  )
}
