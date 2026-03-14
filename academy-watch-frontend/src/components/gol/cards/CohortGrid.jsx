import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { STATUS_BADGE_CLASSES } from '../../../lib/theme-constants'

const STATUS_COLORS = {
  first_team: STATUS_BADGE_CLASSES.first_team,
  on_loan: STATUS_BADGE_CLASSES.on_loan,
  academy: STATUS_BADGE_CLASSES.academy,
  released: STATUS_BADGE_CLASSES.released,
  unknown: 'bg-violet-50 text-violet-800 border-violet-200',
}

export function CohortGrid({ data }) {
  const cohorts = data.cohorts || []
  if (cohorts.length === 0) {
    return (
      <Card className="text-xs">
        <CardContent className="p-3 text-muted-foreground">{data.error || 'No cohort data'}</CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-2">
      {cohorts.map((cohort, ci) => (
        <Card key={ci} className="text-xs">
          <CardHeader className="p-3 pb-1">
            <CardTitle className="text-sm">
              {cohort.team_name} — {cohort.league_name} ({cohort.season})
            </CardTitle>
          </CardHeader>
          <CardContent className="p-3 pt-0">
            <div className="grid grid-cols-2 gap-1">
              {(cohort.members || []).slice(0, 8).map((m, i) => (
                <div key={i} className="flex items-center gap-1 py-0.5">
                  {m.player_photo && <img src={m.player_photo} alt="" className="h-4 w-4 rounded-full" width={16} height={16} />}
                  <span className="truncate">{m.player_name}</span>
                  <Badge className={`text-[10px] px-1 ${STATUS_COLORS[m.current?.status] || STATUS_COLORS.unknown}`}>
                    {m.current?.status || '?'}
                  </Badge>
                </div>
              ))}
            </div>
            {(cohort.members || []).length > 8 && (
              <p className="text-muted-foreground mt-1">+{cohort.members.length - 8} more</p>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
