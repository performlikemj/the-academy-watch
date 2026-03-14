import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'

export function PlayerJourneyMini({ data }) {
  if (data.error) {
    return (
      <Card className="text-xs">
        <CardContent className="p-3 text-muted-foreground">{data.error}</CardContent>
      </Card>
    )
  }

  const entries = data.entries || []
  // Group by club
  const clubs = {}
  for (const e of entries) {
    const key = e.club?.id || 'unknown'
    if (!clubs[key]) {
      clubs[key] = { name: e.club?.name, logo: e.club?.logo, seasons: [], totalApps: 0, totalGoals: 0, level: e.level }
    }
    clubs[key].seasons.push(e.season)
    clubs[key].totalApps += e.stats?.appearances || 0
    clubs[key].totalGoals += e.stats?.goals || 0
  }

  return (
    <Card className="text-xs">
      <CardHeader className="p-3 pb-1">
        <CardTitle className="text-sm">{data.player_name} — Career Journey</CardTitle>
      </CardHeader>
      <CardContent className="p-3 pt-0">
        <div className="space-y-2">
          {Object.values(clubs).map((club, i) => {
            const seasons = [...new Set(club.seasons)].sort()
            const years = seasons.length === 1 ? String(seasons[0]) : `${seasons[0]}-${seasons[seasons.length - 1]}`
            return (
              <div key={i} className="flex items-center gap-2 py-1 border-b last:border-0">
                {club.logo && <img src={club.logo} alt="" className="h-5 w-5" width={20} height={20} />}
                <div className="flex-1">
                  <span className="font-medium">{club.name}</span>
                  <span className="text-muted-foreground ml-2">{years}</span>
                </div>
                <Badge variant="outline">{club.totalApps} apps</Badge>
                {club.totalGoals > 0 && <Badge variant="outline">{club.totalGoals}G</Badge>}
              </div>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}
