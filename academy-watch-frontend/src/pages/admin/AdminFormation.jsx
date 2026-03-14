import { useState, useEffect, useMemo, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ArrowLeft, Loader2, GitCompareArrows } from 'lucide-react'
import { APIService } from '@/lib/api'
import { FORMATION_PRESETS } from '@/lib/formation-presets'
import { PitchSVG } from '@/components/formation/PitchSVG'
import { BenchSidebar } from '@/components/formation/BenchSidebar'
import { FormationHeader } from '@/components/formation/FormationHeader'
import { PlayerStatsPopover } from '@/components/formation/PlayerStatsPopover'
import { SquadSummaryStrip } from '@/components/formation/SquadSummaryStrip'
import { useFormationState } from '@/hooks/useFormationState'

export function AdminFormation() {
  const { teamId } = useParams()

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [teamName, setTeamName] = useState('')

  // Admin-specific state
  const [formationName, setFormationName] = useState('')
  const [notes, setNotes] = useState('')
  const [isDirty, setIsDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState(null)

  // Data
  const [allPlayers, setAllPlayers] = useState([])
  const [savedFormations, setSavedFormations] = useState([])
  const [activeFormationId, setActiveFormationId] = useState(null)

  // Comparison mode
  const [compareId, setCompareId] = useState(null)
  const [showCompare, setShowCompare] = useState(false)

  // Formation state via shared hook
  const formation = useFormationState(allPlayers)

  // Fetch data on mount
  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        setLoading(true)
        const [teamData, formations] = await Promise.all([
          APIService.getTeamPlayers(teamId),
          APIService.adminGetFormations(teamId),
        ])

        if (cancelled) return

        const rawPlayers = teamData?.players || []
        const players = rawPlayers.map((p) => ({
          player_id: p.player_id,
          id: p.player_id,
          player_name: p.player_name,
          name: p.player_name,
          position: p.position,
          photo_url: p.player_photo,
          photo: p.player_photo,
          loan_team_name: p.loan_team_name,
          appearances: p.appearances,
          goals: p.goals,
          assists: p.assists,
          minutes_played: p.minutes_played,
          yellows: p.yellows,
          reds: p.reds,
        }))

        setAllPlayers(players)
        setSavedFormations(formations)

        if (teamData?.team?.name) {
          setTeamName(teamData.team.name)
        }
      } catch (err) {
        if (!cancelled) setError(err.message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [teamId])

  // Wrap formation change to track dirty state
  const handleFormationChange = useCallback((newType) => {
    formation.handleFormationChange(newType)
    setIsDirty(true)
  }, [formation])

  const handlePitchDrop = useCallback((targetSlotKey, dragData) => {
    formation.handlePitchDrop(targetSlotKey, dragData)
    setIsDirty(true)
  }, [formation])

  const handleRemoveFromPitch = useCallback((slotKey) => {
    formation.handleRemoveFromPitch(slotKey)
    setIsDirty(true)
  }, [formation])

  const handleAutoSuggest = useCallback(() => {
    formation.handleAutoSuggest()
    setIsDirty(true)
  }, [formation])

  // Build positions payload for save
  const buildPositionsPayload = useCallback(() => {
    return formation.slots.map((slot) => {
      const player = formation.placements[slot.key]
      return {
        slot_key: slot.key,
        player_id: player ? (player.player_id || player.id) : null,
        player_name: player ? (player.player_name || player.name) : null,
        x: slot.x,
        y: slot.y,
      }
    })
  }, [formation.slots, formation.placements])

  // Save
  const handleSave = async () => {
    if (!formationName.trim()) return
    setSaving(true)
    setMessage(null)

    try {
      const payload = {
        name: formationName.trim(),
        formation_type: formation.formationType,
        positions: buildPositionsPayload(),
        notes: notes || null,
      }

      let result
      if (activeFormationId) {
        result = await APIService.adminUpdateFormation(teamId, activeFormationId, payload)
      } else {
        result = await APIService.adminCreateFormation(teamId, payload)
      }

      setActiveFormationId(result.id)
      setIsDirty(false)
      setMessage({ type: 'success', text: 'Formation saved' })

      const formations = await APIService.adminGetFormations(teamId)
      setSavedFormations(formations)
    } catch (err) {
      setMessage({ type: 'error', text: err.message })
    } finally {
      setSaving(false)
    }
  }

  // Load
  const handleLoad = useCallback((formationId) => {
    const fm = savedFormations.find((f) => f.id === formationId)
    if (!fm) return

    formation.setFormationType(fm.formation_type)
    setFormationName(fm.name)
    setNotes(fm.notes || '')
    setActiveFormationId(fm.id)

    const restored = {}
    for (const pos of fm.positions || []) {
      if (pos.player_id) {
        const player = allPlayers.find(
          (p) => (p.player_id || p.id) === pos.player_id
        )
        if (player) {
          restored[pos.slot_key] = player
        }
      }
    }
    formation.setPlacements(restored)
    setIsDirty(false)
    setMessage(null)
  }, [savedFormations, allPlayers, formation])

  // Delete
  const handleDelete = async () => {
    if (!activeFormationId) return
    try {
      await APIService.adminDeleteFormation(teamId, activeFormationId)
      setActiveFormationId(null)
      setFormationName('')
      setNotes('')
      formation.clearAll()
      setIsDirty(false)
      setMessage({ type: 'success', text: 'Formation deleted' })

      const formations = await APIService.adminGetFormations(teamId)
      setSavedFormations(formations)
    } catch (err) {
      setMessage({ type: 'error', text: err.message })
    }
  }

  // Comparison data
  const compareFormation = useMemo(
    () => savedFormations.find((f) => f.id === compareId),
    [savedFormations, compareId]
  )
  const compareSlots = useMemo(
    () => (compareFormation ? FORMATION_PRESETS[compareFormation.formation_type] || [] : []),
    [compareFormation]
  )
  const comparePlacements = useMemo(() => {
    if (!compareFormation) return {}
    const result = {}
    for (const pos of compareFormation.positions || []) {
      if (pos.player_id) {
        const player = allPlayers.find((p) => (p.player_id || p.id) === pos.player_id)
        if (player) result[pos.slot_key] = player
      }
    }
    return result
  }, [compareFormation, allPlayers])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (error) {
    return (
      <Alert variant="destructive" className="max-w-lg mx-auto mt-8">
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    )
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" asChild>
          <Link to="/admin/teams"><ArrowLeft className="h-4 w-4 mr-1" />Teams</Link>
        </Button>
        <h1 className="text-lg font-semibold">
          Formation Board{teamName ? ` — ${teamName}` : ''}
        </h1>
        <Badge variant="secondary" className="ml-auto">
          {formation.placedCount}/11 placed
        </Badge>
      </div>

      {/* Main formation card */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Formation</CardTitle>
          {allPlayers.length === 0 && (
            <CardDescription className="text-amber-600">
              No players found for this team. Track a team with active academy players to use the formation board.
            </CardDescription>
          )}
        </CardHeader>
        <CardContent className="space-y-4">
          <FormationHeader
            formationType={formation.formationType}
            onFormationChange={handleFormationChange}
            formationName={formationName}
            onNameChange={(v) => { setFormationName(v); setIsDirty(true) }}
            savedFormations={savedFormations}
            activeFormationId={activeFormationId}
            onLoad={handleLoad}
            onSave={handleSave}
            onDelete={handleDelete}
            onAutoSuggest={handleAutoSuggest}
            isDirty={isDirty}
            saving={saving}
          />

          {message && (
            <Alert variant={message.type === 'error' ? 'destructive' : 'default'}>
              <AlertDescription>{message.text}</AlertDescription>
            </Alert>
          )}

          <div className="flex gap-4 items-start">
            <PitchSVG
              slots={formation.slots}
              placements={formation.placements}
              onDrop={handlePitchDrop}
              onPlayerClick={formation.handlePlayerClick}
            />
            <BenchSidebar
              players={formation.benchPlayers}
              onDropFromPitch={handleRemoveFromPitch}
            />
          </div>

          <SquadSummaryStrip placements={formation.placements} />

          {/* Notes */}
          <Textarea
            value={notes}
            onChange={(e) => { setNotes(e.target.value); setIsDirty(true) }}
            placeholder="Notes about this formation..."
            rows={2}
            className="text-sm"
          />
        </CardContent>
      </Card>

      {/* Formation Comparison */}
      {savedFormations.length >= 2 && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base flex items-center gap-2">
                <GitCompareArrows className="h-4 w-4" />
                Compare Formations
              </CardTitle>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowCompare(!showCompare)}
              >
                {showCompare ? 'Hide' : 'Show'}
              </Button>
            </div>
          </CardHeader>
          {showCompare && (
            <CardContent>
              <div className="mb-3">
                <Select value={compareId ? String(compareId) : ''} onValueChange={(v) => setCompareId(Number(v))}>
                  <SelectTrigger className="w-[220px]">
                    <SelectValue placeholder="Select formation to compare..." />
                  </SelectTrigger>
                  <SelectContent>
                    {savedFormations
                      .filter((f) => f.id !== activeFormationId)
                      .map((f) => (
                        <SelectItem key={f.id} value={String(f.id)}>{f.name} ({f.formation_type})</SelectItem>
                      ))}
                  </SelectContent>
                </Select>
              </div>
              {compareFormation ? (
                <div className="flex gap-4 items-start">
                  <div className="flex-1">
                    <p className="text-xs font-semibold text-muted-foreground mb-2 text-center">
                      Current: {formation.formationType}
                    </p>
                    <PitchSVG
                      slots={formation.slots}
                      placements={formation.placements}
                      onDrop={() => {}}
                    />
                    <div className="mt-2">
                      <SquadSummaryStrip placements={formation.placements} />
                    </div>
                  </div>
                  <div className="flex-1">
                    <p className="text-xs font-semibold text-muted-foreground mb-2 text-center">
                      {compareFormation.name}: {compareFormation.formation_type}
                    </p>
                    <PitchSVG
                      slots={compareSlots}
                      placements={comparePlacements}
                      onDrop={() => {}}
                    />
                    <div className="mt-2">
                      <SquadSummaryStrip placements={comparePlacements} />
                    </div>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground text-center py-4">
                  Select a saved formation above to compare side-by-side
                </p>
              )}
            </CardContent>
          )}
        </Card>
      )}

      {/* Player Stats Popover */}
      {formation.selectedPlayer && (
        <PlayerStatsPopover
          player={formation.selectedPlayer}
          slotLabel={formation.selectedSlotLabel}
          onClose={() => formation.clearSelection()}
          onRemove={() => handleRemoveFromPitch(formation.selectedSlotKey)}
        />
      )}
    </div>
  )
}
