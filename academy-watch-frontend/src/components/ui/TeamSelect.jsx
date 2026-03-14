import { useMemo, useState } from 'react'
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command.jsx'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover.jsx'
import { Button } from '@/components/ui/button.jsx'
import { ChevronsUpDown, CheckCircle } from 'lucide-react'

// Searchable single-select for teams. Expects teams with fields: { id (db id), name, league_name? }
export default function TeamSelect({
  teams = [],
  value = null, // selected team db id
  onChange,
  placeholder = 'Select team…',
  groupByLeague = true,
  className = ''
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return teams
    return teams.filter(t => t.name?.toLowerCase().includes(q) || (t.league_name || '').toLowerCase().includes(q))
  }, [teams, query])

  const teamsByLeague = useMemo(() => {
    if (!groupByLeague) return { All: filtered }
    return filtered.reduce((acc, t) => {
      const league = t.league_name || 'Other'
      if (!acc[league]) acc[league] = []
      acc[league].push(t)
      return acc
    }, {})
  }, [filtered, groupByLeague])

  const selected = useMemo(() => teams.find(t => t.id === value) || null, [teams, value])

  const select = (id) => {
    onChange?.(id)
    setOpen(false)
  }

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
            <span className="truncate text-left">
              {selected ? selected.name : <span className="text-muted-foreground">{placeholder}</span>}
            </span>
            <ChevronsUpDown className="h-4 w-4 opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[min(560px,90vw)] p-0">
          <Command>
            <CommandInput placeholder="Search teams or leagues…" value={query} onValueChange={setQuery} />
            <CommandEmpty>No teams found.</CommandEmpty>
            <CommandList>
              {Object.entries(teamsByLeague).map(([league, leagueTeams]) => (
                <CommandGroup key={league} heading={league}>
                  {leagueTeams.map((t) => {
                    const active = t.id === value
                    return (
                      <CommandItem key={t.id} value={`${t.name}`} onSelect={() => select(t.id)}>
                        <CheckCircle className={`h-4 w-4 mr-2 ${active ? 'text-primary' : 'opacity-20'}`} />
                        <span className="flex-1">{t.name}</span>
                      </CommandItem>
                    )
                  })}
                </CommandGroup>
              ))}
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
    </div>
  )
}


