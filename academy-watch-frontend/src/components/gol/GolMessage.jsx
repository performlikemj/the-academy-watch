import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { GolDataCard } from './GolDataCard'
import { Loader2 } from 'lucide-react'

const TOOL_LABELS = {
  'run_analysis': 'Analysing data',
  'search_web': 'Searching the web',
}

export function GolMessage({ message, expanded }) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      <Avatar className="h-8 w-8 shrink-0">
        <AvatarFallback className={isUser ? 'bg-primary text-primary-foreground' : 'bg-emerald-600 text-white'}>
          {isUser ? 'U' : 'G'}
        </AvatarFallback>
      </Avatar>

      <div className={`flex-1 min-w-0 ${isUser ? 'text-right' : ''}`}>
        <div className={`inline-block max-w-[85%] rounded-lg px-3 py-2 text-sm ${
          isUser
            ? 'bg-primary text-primary-foreground'
            : 'bg-muted text-foreground'
        }`}>
          {message.content || (message.toolCall && (
            <span className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="h-3 w-3 animate-spin motion-reduce:animate-none" aria-hidden="true" />
              {TOOL_LABELS[message.toolCall] || `Looking up ${message.toolCall}`}{'\u2026'}
            </span>
          ))}
        </div>

        {message.dataCards?.length > 0 && (
          <div className="mt-2 space-y-2 text-left">
            {message.dataCards.map((card, i) => (
              <GolDataCard key={i} card={card} expanded={expanded} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
