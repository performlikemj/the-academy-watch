import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'

export function PlayerStatsCard({ data, type }) {
  if (type === 'search_players' || type === 'get_team_loans') {
    const items = data.players || data.loans || []
    return (
      <Card className="text-xs">
        <CardContent className="p-3">
          <div className="space-y-2">
            {items.map((p, i) => (
              <div key={i} className="flex items-center justify-between py-1 border-b last:border-0">
                <div>
                  <span className="font-medium">{p.player_name}</span>
                  <span className="text-muted-foreground ml-2">
                    {p.parent_club} → {p.loan_club}
                  </span>
                </div>
                <div className="flex gap-1">
                  {p.appearances > 0 && <Badge variant="outline">{p.appearances} apps</Badge>}
                  {p.goals > 0 && <Badge variant="outline">{p.goals} goals</Badge>}
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    )
  }

  // Match stats
  const matches = data.matches || []
  return (
    <Card className="text-xs">
      <CardHeader className="p-3 pb-1">
        <CardTitle className="text-sm">Recent Matches</CardTitle>
      </CardHeader>
      <CardContent className="p-3 pt-0">
        <div className="space-y-1">
          {matches.map((m, i) => (
            <div key={i} className="flex items-center justify-between py-1 border-b last:border-0">
              <div className="text-muted-foreground">
                {m.date ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(m.date)) : 'N/A'}
                <span className="ml-2">{m.competition}</span>
              </div>
              <div className="flex gap-1">
                <Badge variant="outline">{m.minutes}&prime;</Badge>
                {m.goals > 0 && <Badge className="bg-emerald-100 text-emerald-800">{m.goals}G</Badge>}
                {m.assists > 0 && <Badge className="bg-amber-100 text-amber-800">{m.assists}A</Badge>}
                {m.rating && <Badge variant="secondary">{m.rating}</Badge>}
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
