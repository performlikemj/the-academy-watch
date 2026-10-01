import * as React from "react"
import { useNavigate } from "react-router-dom"
import {
  Command,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
  CommandSeparator,
} from "@/components/ui/command"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import {
  Home,
  Clock,
  Search,
  X,
  ArrowRight,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Avatar, AvatarImage, AvatarFallback } from "@/components/ui/avatar"
import { APIService } from "@/lib/api"

// Debounce helper
function useDebounce(value, delay) {
  const [debouncedValue, setDebouncedValue] = React.useState(value)

  React.useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])

  return debouncedValue
}

/**
 * Global Search Dialog component
 * Opens with Cmd+K / Ctrl+K and allows searching for players
 */
export function GlobalSearchDialog({
  open,
  onOpenChange,
  recentSearches = [],
  onSelect,
  onClearRecent,
}) {
  const navigate = useNavigate()
  const [searchQuery, setSearchQuery] = React.useState("")
  const [isLoading, setIsLoading] = React.useState(false)
  const [players, setPlayers] = React.useState([])

  const debouncedQuery = useDebounce(searchQuery, 300)

  React.useEffect(() => {
    let cancelled = false
    if (!open || debouncedQuery.length < 2) {
      setPlayers([])
      setIsLoading(false)
      return
    }
    setIsLoading(true)
    APIService.searchPlayers(debouncedQuery)
      .then((results) => { if (!cancelled) setPlayers(Array.isArray(results) ? results.slice(0, 5) : []) })
      .catch(() => { if (!cancelled) setPlayers([]) })
      .finally(() => { if (!cancelled) setIsLoading(false) })
    return () => { cancelled = true }
  }, [open, debouncedQuery])

  // Old saved searches must not resurrect hidden pages.
  const visibleRecentSearches = recentSearches.filter((item) => item.type === 'player')

  // Handle item selection
  const handleSelect = React.useCallback(
    (type, item) => {
      let path = "/"
      let searchItem = null

      switch (type) {
        case "player":
          path = `/players/${item.player_api_id}`
          searchItem = {
            type: "player",
            id: item.player_api_id,
            name: item.player_name,
          }
          break
        case "page":
          path = item.path
          break
        case "recent":
          if (item.type !== "player") return
          path = `/players/${item.id}`
          break
        default:
          break
      }

      // Add to recent searches (except for quick actions)
      if (searchItem && onSelect) {
        onSelect(searchItem)
      }

      navigate(path)
      onOpenChange(false)
      setSearchQuery("")
    },
    [navigate, onOpenChange, onSelect]
  )

  // Quick actions for navigation
  const quickActions = [
    { name: "Home", icon: Home, path: "/" },
  ]

  const hasResults = players.length > 0
  const showQuickActions = !debouncedQuery || debouncedQuery.length < 2

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogHeader className="sr-only">
        <DialogTitle>Search</DialogTitle>
        <DialogDescription>Search for players</DialogDescription>
      </DialogHeader>
      <DialogContent className="overflow-hidden p-0 gap-0">
        <div className="flex items-center border-b px-3">
          <Search className="mr-2 h-4 w-4 shrink-0 opacity-50" />
          <Input
            placeholder="Search players..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="flex h-12 w-full border-0 bg-transparent py-3 text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-0 focus-visible:ring-offset-0"
            autoFocus
          />
        </div>
        <Command shouldFilter={false}>
          <CommandList>
        {isLoading && (
          <div className="py-6 text-center text-sm text-muted-foreground">
            <Search className="inline-block h-4 w-4 mr-2 animate-pulse" />
            Searching...
          </div>
        )}

        {!isLoading && debouncedQuery.length >= 2 && !hasResults && (
          <CommandEmpty>No results found for "{debouncedQuery}"</CommandEmpty>
        )}

        {/* Quick Actions - shown when no search query */}
        {showQuickActions && (
          <>
            <CommandGroup heading="Quick Actions">
              {quickActions.map((action) => (
                <CommandItem
                  key={action.path}
                  onSelect={() => handleSelect("page", action)}
                >
                  <action.icon className="mr-2 h-4 w-4" />
                  <span>{action.name}</span>
                </CommandItem>
              ))}
            </CommandGroup>

            {/* Recent Searches */}
            {visibleRecentSearches.length > 0 && (
              <>
                <CommandSeparator />
                <CommandGroup heading="Recent Searches">
                  {visibleRecentSearches.map((item, index) => (
                    <CommandItem
                      key={`${item.type}-${item.id}-${index}`}
                      onSelect={() => handleSelect("recent", item)}
                    >
                      <Clock className="mr-2 h-4 w-4 text-muted-foreground" />
                      <span>{item.name}</span>
                      {item.team && (
                        <span className="ml-2 text-xs text-muted-foreground">
                          {item.team}
                        </span>
                      )}
                      <ArrowRight className="ml-auto h-3 w-3 text-muted-foreground" />
                    </CommandItem>
                  ))}
                  <CommandItem
                    onSelect={() => {
                      if (onClearRecent) onClearRecent()
                    }}
                    className="text-muted-foreground"
                  >
                    <X className="mr-2 h-4 w-4" />
                    <span>Clear recent searches</span>
                  </CommandItem>
                </CommandGroup>
              </>
            )}
          </>
        )}

        {/* Search Results */}
        {!isLoading && hasResults && (
          <>
            {/* Players */}
            {players.length > 0 && (
              <>
                <CommandGroup heading="Players">
                  {players.map((player) => (
                    <CommandItem
                      key={`player-${player.player_api_id}`}
                      onSelect={() => handleSelect("player", player)}
                    >
                      <Avatar className="mr-2 h-5 w-5">
                        {player.photo_url ? (
                          <AvatarImage src={player.photo_url} alt={player.player_name} />
                        ) : null}
                        <AvatarFallback className="text-[10px] bg-secondary">
                          {(player.player_name || '?').substring(0, 1).toUpperCase()}
                        </AvatarFallback>
                      </Avatar>
                      <span>{player.player_name}</span>
                      {player.position && (
                        <Badge variant="outline" className="ml-2 text-xs px-1.5 py-0">
                          {player.position}
                        </Badge>
                      )}
                      {player.team_name && (
                        <span className="ml-2 text-xs text-muted-foreground truncate">
                          {player.team_name}
                        </span>
                      )}
                    </CommandItem>
                  ))}
                </CommandGroup>
              </>
            )}

          </>
        )}
          </CommandList>
        </Command>
      </DialogContent>
    </Dialog>
  )
}

export default GlobalSearchDialog
