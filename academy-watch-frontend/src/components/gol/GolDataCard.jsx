import { AnalysisResultCard } from './cards/AnalysisResultCard'
import { PlayerStatsCard } from './cards/PlayerStatsCard'
import { PlayerJourneyMini } from './cards/PlayerJourneyMini'
import { CohortGrid } from './cards/CohortGrid'
import { CommunityTakesList } from './cards/CommunityTakesList'
import { Card, CardContent } from '@/components/ui/card'

export function GolDataCard({ card, expanded }) {
  const { type, payload } = card

  switch (type) {
    case 'analysis_result':
      return <AnalysisResultCard data={payload} expanded={expanded} />
    case 'search_players':
    case 'get_player_stats':
    case 'get_team_loans':
      return <PlayerStatsCard data={payload} type={type} />
    case 'get_player_journey':
      return <PlayerJourneyMini data={payload} />
    case 'get_cohort':
      return <CohortGrid data={payload} />
    case 'get_community_takes':
      return <CommunityTakesList data={payload} />
    default:
      return (
        <Card className="text-xs">
          <CardContent className="p-3">
            <pre className="overflow-auto max-h-40 text-muted-foreground">
              {JSON.stringify(payload, null, 2)}
            </pre>
          </CardContent>
        </Card>
      )
  }
}
