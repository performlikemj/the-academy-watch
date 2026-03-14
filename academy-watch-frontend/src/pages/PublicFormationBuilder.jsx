import { useState, useEffect, useMemo, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar'
import { ArrowLeft, Loader2, Search, X, CheckCircle } from 'lucide-react'
import { APIService } from '@/lib/api'
import { FORMATION_PRESETS } from '@/lib/formation-presets'
import { PitchSVG } from '@/components/formation/PitchSVG'
import { BenchSidebar } from '@/components/formation/BenchSidebar'
import { FormationHeader } from '@/components/formation/FormationHeader'
import { PlayerStatsPopover } from '@/components/formation/PlayerStatsPopover'
import { SquadSummaryStrip } from '@/components/formation/SquadSummaryStrip'
import { useFormationState } from '@/hooks/useFormationState'

function mapLoanToPlayer(loan) {
  return {
    player_id: loan.player_id,
    id: loan.player_id,
    player_name: loan.player_name,
    name: loan.player_name,
    position: loan.position,
    photo_url: loan.photo_url || loan.player_photo,
    photo: loan.photo_url || loan.player_photo,
    loan_team_name: loan.loan_team_name,
    appearances: loan.appearances,
    goals: loan.goals,
    assists: loan.assists,
    minutes_played: loan.minutes_played,
    yellows: loan.yellows,
    reds: loan.reds,
  }
}

export function PublicFormationBuilder() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [step, setStep] = useState('team-select')
  const [teams, setTeams] = useState([])
  const [teamsLoading, setTeamsLoading] = useState(true)
  const [teamSearch, setTeamSearch] = useState('')
  const [selectedTeam, setSelectedTeam] = useState(null)
  const [allPlayers, setAllPlayers] = useState([])
  const [playersLoading, setPlayersLoading] = useState(false)
  const [toast, setToast] = useState(null)

  const formation = useFormationState(allPlayers)

  // Fetch teams on mount
  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const data = await APIService.getTeams({ european_only: 'true', has_loans: 'true' })
        if (!cancelled) {
          const list = Array.isArray(data) ? data : []
          setTeams(list)
        }
      } catch (err) {
        console.error('Failed to load teams:', err)
      } finally {
        if (!cancelled) setTeamsLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [])

  // Restore from URL params
  useEffect(() => {
    const teamParam = searchParams.get('team')
    const formationParam = searchParams.get('f')
    const placementsParam = searchParams.get('p')
    if (teamParam && teams.length > 0) {
      const teamId = Number(teamParam)
      const team = teams.find((t) => t.id === teamId || t.team_id === teamId)
      if (team) {
        selectTeam(team, { formationType: formationParam, placementsStr: placementsParam })
      }
    }
  // Only run when teams are loaded and params exist
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [teams])

  const selectTeam = useCallback(async (team, restoreState = null) => {
    setSelectedTeam(team)
    setStep('builder')
    setPlayersLoading(true)
    try {
      const teamData = await APIService.getTeamPlayers(team.id || team.team_id)
      const players = (teamData?.players || []).map(mapLoanToPlayer)
      setAllPlayers(players)

      // Restore formation from URL params if provided
      if (restoreState?.formationType && FORMATION_PRESETS[restoreState.formationType]) {
        formation.setFormationType(restoreState.formationType)
      }
      if (restoreState?.placementsStr && players.length > 0) {
        const restored = {}
        const pairs = restoreState.placementsStr.split(',')
        for (const pair of pairs) {
          const [slotKey, pidStr] = pair.split(':')
          if (!slotKey || !pidStr) continue
          const pid = Number(pidStr)
          const player = players.find((p) => (p.player_id || p.id) === pid)
          if (player) {
            restored[slotKey] = player
          }
        }
        formation.setPlacements(restored)
      }
    } catch (err) {
      console.error('Failed to load players:', err)
    } finally {
      setPlayersLoading(false)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const goBackToTeams = useCallback(() => {
    setStep('team-select')
    setSelectedTeam(null)
    setAllPlayers([])
    formation.clearAll()
    setSearchParams({}, { replace: true })
  }, [formation, setSearchParams])

  const handleShare = useCallback(() => {
    if (!selectedTeam) return
    const teamId = selectedTeam.id || selectedTeam.team_id
    const params = new URLSearchParams()
    params.set('team', String(teamId))
    params.set('f', formation.formationType)

    const placementPairs = Object.entries(formation.placements)
      .filter(([, player]) => player)
      .map(([slotKey, player]) => `${slotKey}:${player.player_id || player.id}`)
    if (placementPairs.length > 0) {
      params.set('p', placementPairs.join(','))
    }

    const url = `${window.location.origin}/dream-team?${params.toString()}`
    navigator.clipboard.writeText(url).then(() => {
      setToast('Link copied!')
      setTimeout(() => setToast(null), 2000)
    }).catch(() => {
      setToast('Failed to copy')
      setTimeout(() => setToast(null), 2000)
    })

    setSearchParams(params, { replace: true })
  }, [selectedTeam, formation.formationType, formation.placements, setSearchParams])

  // Team search filtering
  const query = teamSearch.trim().toLowerCase()
  const filteredTeams = useMemo(() => {
    if (!query) return teams
    return teams.filter((t) =>
      t.name.toLowerCase().includes(query)
    ).sort((a, b) => {
      const aStarts = a.name.toLowerCase().startsWith(query) ? 0 : 1
      const bStarts = b.name.toLowerCase().startsWith(query) ? 0 : 1
      return aStarts - bStarts || a.name.localeCompare(b.name)
    })
  }, [teams, query])

  // Team selection step
  if (step === 'team-select') {
    return (
      <div className="max-w-5xl mx-auto px-4 py-8">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-foreground mb-2">Dream XI Builder</h1>
          <p className="text-muted-foreground">Pick a club, then build your ideal lineup from their academy players</p>
        </div>

        {/* Search */}
        <div className="relative max-w-md mx-auto mb-8">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/70" />
          <Input
            type="text"
            placeholder="Search clubs..."
            value={teamSearch}
            onChange={(e) => setTeamSearch(e.target.value)}
            className="pl-10 pr-10"
          />
          {teamSearch && (
            <button
              onClick={() => setTeamSearch('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground/70 hover:text-muted-foreground"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>

        {teamsLoading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground/70" />
          </div>
        ) : filteredTeams.length === 0 ? (
          <p className="text-center text-muted-foreground py-12">
            {query ? 'No clubs match your search.' : 'No clubs available.'}
          </p>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
            {filteredTeams.map((team) => (
              <button
                key={team.id}
                onClick={() => selectTeam(team)}
                className="flex flex-col items-center gap-2 p-4 rounded-xl border border-border bg-card hover:border-border hover:shadow-sm transition-all text-center"
              >
                <Avatar className="h-12 w-12">
                  {team.logo ? (
                    <AvatarImage src={team.logo} alt={team.name} />
                  ) : null}
                  <AvatarFallback className="text-xs bg-secondary">
                    {team.name.split(' ').map((n) => n[0]).join('').slice(0, 2).toUpperCase()}
                  </AvatarFallback>
                </Avatar>
                <span className="text-sm font-medium text-foreground leading-tight">{team.name}</span>
                {team.league_name && (
                  <span className="text-xs text-muted-foreground/70">{team.league_name}</span>
                )}
              </button>
            ))}
          </div>
        )}
      </div>
    )
  }

  // Builder step
  return (
    <div className="max-w-6xl mx-auto px-4 py-6">
      {/* Header */}
      <div className="flex items-center gap-3 mb-4">
        <Button variant="ghost" size="sm" onClick={goBackToTeams}>
          <ArrowLeft className="h-4 w-4 mr-1" />
          Teams
        </Button>
        <div className="flex items-center gap-2 flex-1 min-w-0">
          {selectedTeam?.logo && (
            <Avatar className="h-8 w-8">
              <AvatarImage src={selectedTeam.logo} alt={selectedTeam.name} />
              <AvatarFallback className="text-xs bg-secondary">
                {selectedTeam.name?.split(' ').map((n) => n[0]).join('').slice(0, 2).toUpperCase()}
              </AvatarFallback>
            </Avatar>
          )}
          <h1 className="text-lg font-semibold truncate">{selectedTeam?.name}</h1>
        </div>
        <Badge variant="secondary">
          {formation.placedCount}/11
        </Badge>
      </div>

      {playersLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground/70" />
        </div>
      ) : allPlayers.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground">
          <p className="mb-2">No academy players found for this team.</p>
          <Button variant="outline" size="sm" onClick={goBackToTeams}>
            Choose another team
          </Button>
        </div>
      ) : (
        <div className="space-y-4">
          <FormationHeader
            formationType={formation.formationType}
            onFormationChange={formation.handleFormationChange}
            onAutoSuggest={formation.handleAutoSuggest}
            mode="public"
            onClear={formation.clearAll}
            onShare={handleShare}
          />

          <div className="flex flex-col md:flex-row gap-4 items-start">
            <PitchSVG
              slots={formation.slots}
              placements={formation.placements}
              onDrop={formation.handlePitchDrop}
              onPlayerClick={formation.handlePlayerClick}
            />
            <BenchSidebar
              players={formation.benchPlayers}
              onDropFromPitch={formation.handleRemoveFromPitch}
            />
          </div>

          <SquadSummaryStrip placements={formation.placements} />
        </div>
      )}

      {/* Player Stats Popover */}
      {formation.selectedPlayer && (
        <PlayerStatsPopover
          player={formation.selectedPlayer}
          slotLabel={formation.selectedSlotLabel}
          onClose={() => formation.clearSelection()}
          onRemove={() => formation.handleRemoveFromPitch(formation.selectedSlotKey)}
        />
      )}

      {/* Toast */}
      {toast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-2 bg-foreground text-primary-foreground text-sm px-4 py-2.5 rounded-lg shadow-lg">
          <CheckCircle className="h-4 w-4 text-green-400" />
          {toast}
        </div>
      )}
    </div>
  )
}
