import { Card, CardContent } from '@/components/ui/card'

export function CommunityTakesList({ data }) {
  const takes = data.takes || []
  if (takes.length === 0) {
    return (
      <Card className="text-xs">
        <CardContent className="p-3 text-muted-foreground">No community takes found</CardContent>
      </Card>
    )
  }

  return (
    <Card className="text-xs">
      <CardContent className="p-3">
        <div className="space-y-3">
          {takes.map((t, i) => (
            <blockquote key={i} className="border-l-2 border-primary pl-3 py-1">
              <p className="text-sm italic">"{t.content}"</p>
              <footer className="text-muted-foreground mt-1">
                — {t.author}
                {t.platform && <span className="ml-1">({t.platform})</span>}
                {t.upvotes > 0 && <span className="ml-2">&uarr;{t.upvotes}</span>}
              </footer>
            </blockquote>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
