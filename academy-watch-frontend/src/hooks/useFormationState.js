import { useState, useMemo, useCallback } from 'react'
import { FORMATION_PRESETS, getPositionGroup } from '@/lib/formation-presets'

export function useFormationState(allPlayers) {
  const [formationType, setFormationType] = useState('4-3-3')
  const [placements, setPlacements] = useState({})
  const [selectedPlayer, setSelectedPlayer] = useState(null)
  const [selectedSlotKey, setSelectedSlotKey] = useState(null)

  const slots = useMemo(() => FORMATION_PRESETS[formationType] || [], [formationType])

  const placedIds = useMemo(() => {
    const ids = new Set()
    for (const p of Object.values(placements)) {
      if (p) ids.add(p.player_id || p.id)
    }
    return ids
  }, [placements])

  const benchPlayers = useMemo(
    () => allPlayers.filter((p) => !placedIds.has(p.player_id || p.id)),
    [allPlayers, placedIds]
  )

  const placedCount = useMemo(
    () => Object.values(placements).filter(Boolean).length,
    [placements]
  )

  const handleFormationChange = useCallback((newType) => {
    const newSlots = FORMATION_PRESETS[newType] || []
    const newSlotKeys = new Set(newSlots.map((s) => s.key))
    const preserved = {}
    for (const [key, player] of Object.entries(placements)) {
      if (newSlotKeys.has(key) && player) {
        preserved[key] = player
      }
    }
    setFormationType(newType)
    setPlacements(preserved)
  }, [placements])

  const handlePitchDrop = useCallback((targetSlotKey, dragData) => {
    setPlacements((prev) => {
      const next = { ...prev }
      if (dragData.source === 'bench') {
        const player = allPlayers.find(
          (p) => (p.player_id || p.id) === dragData.player_id
        )
        if (player) {
          next[targetSlotKey] = player
        }
      } else if (dragData.source === 'pitch') {
        const fromSlot = dragData.slotKey
        const playerA = prev[fromSlot] || null
        const playerB = prev[targetSlotKey] || null
        next[fromSlot] = playerB
        next[targetSlotKey] = playerA
      }
      return next
    })
  }, [allPlayers])

  const handleRemoveFromPitch = useCallback((slotKey) => {
    setPlacements((prev) => {
      const next = { ...prev }
      delete next[slotKey]
      return next
    })
    setSelectedPlayer(null)
  }, [])

  const handlePlayerClick = useCallback((player, slotKey) => {
    setSelectedPlayer(player)
    setSelectedSlotKey(slotKey)
  }, [])

  const handleAutoSuggest = useCallback(() => {
    const slotGroupMap = {
      Goalkeeper: slots.filter((s) => s.positionGroup === 'Goalkeeper'),
      Defender: slots.filter((s) => s.positionGroup === 'Defender'),
      Midfielder: slots.filter((s) => s.positionGroup === 'Midfielder'),
      Forward: slots.filter((s) => s.positionGroup === 'Forward'),
    }

    const newPlacements = { ...placements }
    const usedPlayerIds = new Set(
      Object.values(newPlacements).filter(Boolean).map((p) => p.player_id || p.id)
    )

    const available = allPlayers.filter((p) => !usedPlayerIds.has(p.player_id || p.id))
    available.sort((a, b) => (b.appearances || 0) - (a.appearances || 0))

    for (const player of available) {
      const group = getPositionGroup(player.position)
      const groupSlots = slotGroupMap[group] || []
      for (const slot of groupSlots) {
        if (!newPlacements[slot.key]) {
          newPlacements[slot.key] = player
          usedPlayerIds.add(player.player_id || player.id)
          break
        }
      }
    }

    setPlacements(newPlacements)
  }, [slots, placements, allPlayers])

  const clearSelection = useCallback(() => {
    setSelectedPlayer(null)
    setSelectedSlotKey(null)
  }, [])

  const clearAll = useCallback(() => {
    setPlacements({})
    setSelectedPlayer(null)
    setSelectedSlotKey(null)
  }, [])

  const selectedSlotLabel = useMemo(() => {
    if (!selectedSlotKey) return null
    const slot = slots.find((s) => s.key === selectedSlotKey)
    return slot ? `${slot.label} (${slot.positionGroup})` : selectedSlotKey
  }, [selectedSlotKey, slots])

  return {
    formationType,
    setFormationType,
    slots,
    placements,
    setPlacements,
    benchPlayers,
    placedCount,
    handleFormationChange,
    handlePitchDrop,
    handleRemoveFromPitch,
    handlePlayerClick,
    handleAutoSuggest,
    selectedPlayer,
    selectedSlotKey,
    selectedSlotLabel,
    clearSelection,
    clearAll,
  }
}
