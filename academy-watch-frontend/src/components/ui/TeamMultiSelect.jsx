import { useMemo, useState, useEffect } from 'react'
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command.jsx'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover.jsx'
import { Button } from '@/components/ui/button.jsx'
import { Badge } from '@/components/ui/badge.jsx'
import { CheckCircle, ChevronsUpDown, X } from 'lucide-react'

// Accessible, searchable multi-select for teams with grouping support.
// Props:
// - teams: Array<{ id: number, name: string, league_name?: string }>
// - value: number[] (selected team ids)
// - onChange: (ids: number[]) => void
// - placeholder?: string
// - maxChips?: number – how many selected chips to show before "+N"
// - groupByLeague?: boolean
// - className?: string
export default function TeamMultiSelect({
  teams = [],
  value = [],
  onChange,
  placeholder = 'Select teams…',
  maxChips = 3,
  groupByLeague = true,
  className = ''
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')

  const filteredTeams = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return teams
    return teams.filter(t =>
      t.name?.toLowerCase().includes(q) ||
      (t.league_name || '').toLowerCase().includes(q)
    )
  }, [teams, query])

  const teamsByLeague = useMemo(() => {
    if (!groupByLeague) return { All: filteredTeams }
    return filteredTeams.reduce((acc, team) => {
      const league = team.league_name || 'Other'
      if (!acc[league]) acc[league] = []
      acc[league].push(team)
      return acc
    }, {})
  }, [filteredTeams, groupByLeague])

  const selectedTeams = useMemo(() => {
    const idSet = new Set(value)
    return teams.filter(t => idSet.has(t.id))
  }, [teams, value])

  const toggle = (id) => {
    if (!onChange) return
    const exists = value.includes(id)
    if (exists) onChange(value.filter(v => v !== id))
    else onChange([...value, id])
  }

  const clearAll = () => onChange?.([])

  // Close menu when teams list changes drastically (e.g., after fetch)
  useEffect(() => {
    setQuery('')
  }, [teams.length])

  return (
    <div className={className}>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            role="combobox"
            aria-expanded={open}
            className="w-full justify-between"
          >
            <div className="flex items-center gap-2 flex-wrap text-left">
              {selectedTeams.length === 0 ? (
                <span className="text-muted-foreground">{placeholder}</span>
              ) : (
                <div className="flex items-center gap-1 flex-wrap">
                  {selectedTeams.slice(0, maxChips).map((t) => (
                    <Badge key={t.id} variant="secondary" className="flex items-center gap-1">
                      {t.name}
                      <X className="h-3 w-3 cursor-pointer" onClick={(e) => { e.stopPropagation(); toggle(t.id) }} />
                    </Badge>
                  ))}
                  {selectedTeams.length > maxChips && (
                    <Badge variant="secondary">+{selectedTeams.length - maxChips}</Badge>
                  )}
                </div>
              )}
            </div>
            <ChevronsUpDown className="h-4 w-4 opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[min(640px,90vw)] p-0">
          <Command>
            <CommandInput placeholder="Search teams or leagues…" value={query} onValueChange={setQuery} />
            <CommandEmpty>No teams found.</CommandEmpty>
            <CommandList>
              {Object.entries(teamsByLeague).map(([league, leagueTeams]) => (
                <CommandGroup key={league} heading={league}>
                  {leagueTeams.map((team) => {
                    const active = value.includes(team.id)
                    return (
                      <CommandItem
                        key={team.id}
                        value={`${team.name}`}
                        onSelect={() => toggle(team.id)}
                      >
                        <CheckCircle className={`h-4 w-4 mr-2 ${active ? 'text-primary' : 'opacity-20'}`} />
                        <span className="flex-1">{team.name}</span>
                        {(team.tracked_player_count ?? team.current_loaned_out_count) != null && (
                          <span className="text-xs text-muted-foreground">{team.tracked_player_count ?? team.current_loaned_out_count} players</span>
                        )}
                      </CommandItem>
                    )
                  })}
                </CommandGroup>
              ))}
            </CommandList>
          </Command>
          <div className="flex items-center justify-between border-t p-2">
            <div className="text-xs text-muted-foreground">{value.length} selected</div>
            <div className="flex gap-2">
              <Button size="sm" variant="ghost" onClick={clearAll} disabled={value.length === 0}>Clear</Button>
              <Button size="sm" onClick={() => setOpen(false)}>Done</Button>
            </div>
          </div>
        </PopoverContent>
      </Popover>
    </div>
  )
}


