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
  Users,
  FileText,
  User,
  Clock,
  Search,
  X,
  ArrowRight,
  Sparkles,
  PenLine,
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
 * Opens with Cmd+K / Ctrl+K and allows searching across teams, newsletters, and journalists
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
  const [teams, setTeams] = React.useState([])
  const [newsletters, setNewsletters] = React.useState([])
  const [journalists, setJournalists] = React.useState([])
  const [writeups, setWriteups] = React.useState([])
  const [players, setPlayers] = React.useState([])

  const debouncedQuery = useDebounce(searchQuery, 300)

  // Fetch search results when query changes
  React.useEffect(() => {
    if (!debouncedQuery || debouncedQuery.length < 2) {
      setTeams([])
      setNewsletters([])
      setWriteups([])
      setPlayers([])
      return
    }

    const fetchResults = async () => {
      setIsLoading(true)
      console.log("[GlobalSearch] Searching for:", debouncedQuery)
      try {
        const [teamsRes, newslettersRes, writeupsRes, playersRes] = await Promise.all([
          APIService.getTeams({ search: debouncedQuery }).catch((err) => {
            console.error("[GlobalSearch] Teams search failed:", err)
            return []
          }),
          APIService.getNewsletters({ search: debouncedQuery, published_only: 'true' }).catch((err) => {
            console.error("[GlobalSearch] Newsletters search failed:", err)
            return []
          }),
          APIService.searchCommentaries(debouncedQuery).catch((err) => {
            console.error("[GlobalSearch] Writeups search failed:", err)
            return []
          }),
          APIService.searchPlayers(debouncedQuery).catch((err) => {
            console.error("[GlobalSearch] Players search failed:", err)
            return []
          }),
        ])

        console.log("[GlobalSearch] Teams results:", teamsRes?.length || 0)
        console.log("[GlobalSearch] Newsletters results:", newslettersRes?.length || 0)
        console.log("[GlobalSearch] Writeups results:", writeupsRes?.length || 0)
        console.log("[GlobalSearch] Players results:", playersRes?.length || 0)

        setTeams(Array.isArray(teamsRes) ? teamsRes.slice(0, 5) : [])
        setNewsletters(Array.isArray(newslettersRes) ? newslettersRes.slice(0, 5) : [])
        setWriteups(Array.isArray(writeupsRes) ? writeupsRes.slice(0, 5) : [])
        setPlayers(Array.isArray(playersRes) ? playersRes.slice(0, 5) : [])
      } catch (error) {
        console.error("[GlobalSearch] Search error:", error)
      } finally {
        setIsLoading(false)
      }
    }

    fetchResults()
  }, [debouncedQuery])

  // Fetch journalists once on mount (small dataset, filter client-side)
  React.useEffect(() => {
    APIService.getJournalists()
      .then((res) => {
        setJournalists(Array.isArray(res) ? res : [])
      })
      .catch(() => setJournalists([]))
  }, [])

  // Filter journalists client-side
  const filteredJournalists = React.useMemo(() => {
    if (!debouncedQuery || debouncedQuery.length < 2) return []
    const query = debouncedQuery.toLowerCase()
    return journalists
      .filter((j) => j.display_name?.toLowerCase().includes(query))
      .slice(0, 3)
  }, [journalists, debouncedQuery])

  // Handle item selection
  const handleSelect = React.useCallback(
    (type, item) => {
      let path = "/"
      let searchItem = null

      switch (type) {
        case "team":
          path = `/teams?highlight=${item.id}`
          searchItem = {
            type: "team",
            id: item.id,
            name: item.name,
            logo: item.logo,
          }
          break
        case "newsletter":
          path = `/newsletters/${item.id}`
          searchItem = {
            type: "newsletter",
            id: item.id,
            name: item.title || `Newsletter #${item.id}`,
            team: item.team_name,
          }
          break
        case "journalist":
          path = `/journalists/${item.id}`
          searchItem = {
            type: "journalist",
            id: item.id,
            name: item.display_name,
          }
          break
        case "player":
          path = `/players/${item.player_api_id}`
          searchItem = {
            type: "player",
            id: item.player_api_id,
            name: item.player_name,
          }
          break
        case "writeup":
          path = `/writeups/${item.id}`
          searchItem = {
            type: "writeup",
            id: item.id,
            name: item.title,
            is_premium: item.is_premium,
          }
          break
        case "page":
          path = item.path
          break
        case "recent":
          // Navigate to the recent item
          if (item.type === "team") path = `/teams?highlight=${item.id}`
          else if (item.type === "newsletter") path = `/newsletters/${item.id}`
          else if (item.type === "journalist") path = `/journalists/${item.id}`
          else if (item.type === "player") path = `/players/${item.id}`
          else if (item.type === "writeup") path = `/writeups/${item.id}`
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
    { name: "Browse Teams", icon: Users, path: "/teams" },
    { name: "Newsletters", icon: FileText, path: "/newsletters" },
    { name: "Journalists", icon: User, path: "/journalists" },
  ]

  const hasResults =
    teams.length > 0 || newsletters.length > 0 || filteredJournalists.length > 0 || writeups.length > 0 || players.length > 0
  const showQuickActions = !debouncedQuery || debouncedQuery.length < 2

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogHeader className="sr-only">
        <DialogTitle>Search</DialogTitle>
        <DialogDescription>Search for teams, newsletters, and journalists</DialogDescription>
      </DialogHeader>
      <DialogContent className="overflow-hidden p-0 gap-0">
        <div className="flex items-center border-b px-3">
          <Search className="mr-2 h-4 w-4 shrink-0 opacity-50" />
          <Input
            placeholder="Search teams, newsletters, journalists..."
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
            {recentSearches.length > 0 && (
              <>
                <CommandSeparator />
                <CommandGroup heading="Recent Searches">
                  {recentSearches.map((item, index) => (
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
            {/* Teams */}
            {teams.length > 0 && (
              <CommandGroup heading="Teams">
                {teams.map((team) => (
                  <CommandItem
                    key={`team-${team.id}`}
                    onSelect={() => handleSelect("team", team)}
                  >
                    {team.logo ? (
                      <img
                        src={team.logo}
                        alt=""
                        className="mr-2 h-5 w-5 rounded object-contain"
                      />
                    ) : (
                      <Users className="mr-2 h-4 w-4" />
                    )}
                    <span>{team.name}</span>
                    {team.league_name && (
                      <span className="ml-2 text-xs text-muted-foreground">
                        {team.league_name}
                      </span>
                    )}
                  </CommandItem>
                ))}
              </CommandGroup>
            )}

            {/* Newsletters */}
            {newsletters.length > 0 && (
              <>
                {teams.length > 0 && <CommandSeparator />}
                <CommandGroup heading="Newsletters">
                  {newsletters.map((newsletter) => (
                    <CommandItem
                      key={`newsletter-${newsletter.id}`}
                      onSelect={() => handleSelect("newsletter", newsletter)}
                    >
                      <FileText className="mr-2 h-4 w-4" />
                      <span className="truncate">
                        {newsletter.title || `Newsletter #${newsletter.id}`}
                      </span>
                      {newsletter.team_name && (
                        <span className="ml-2 text-xs text-muted-foreground truncate">
                          {newsletter.team_name}
                        </span>
                      )}
                    </CommandItem>
                  ))}
                </CommandGroup>
              </>
            )}

            {/* Journalists */}
            {filteredJournalists.length > 0 && (
              <>
                {(teams.length > 0 || newsletters.length > 0) && (
                  <CommandSeparator />
                )}
                <CommandGroup heading="Writers">
                  {filteredJournalists.map((journalist) => (
                    <CommandItem
                      key={`journalist-${journalist.id}`}
                      onSelect={() => handleSelect("journalist", journalist)}
                    >
                      <User className="mr-2 h-4 w-4" />
                      <span>{journalist.display_name}</span>
                    </CommandItem>
                  ))}
                </CommandGroup>
              </>
            )}

            {/* Players */}
            {players.length > 0 && (
              <>
                {(teams.length > 0 || newsletters.length > 0 || filteredJournalists.length > 0) && (
                  <CommandSeparator />
                )}
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

            {/* Writeups */}
            {writeups.length > 0 && (
              <>
                {(teams.length > 0 || newsletters.length > 0 || filteredJournalists.length > 0 || players.length > 0) && (
                  <CommandSeparator />
                )}
                <CommandGroup heading="Writeups">
                  {writeups.map((writeup) => (
                    <CommandItem
                      key={`writeup-${writeup.id}`}
                      onSelect={() => handleSelect("writeup", writeup)}
                    >
                      <PenLine className="mr-2 h-4 w-4" />
                      <span className="truncate flex-1">{writeup.title}</span>
                      {writeup.is_premium && (
                        <Badge variant="outline" className="ml-2 text-amber-600 border-amber-300 text-xs">
                          <Sparkles className="h-3 w-3 mr-1" />
                          Premium
                        </Badge>
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
