import { useEffect, useRef } from 'react'
import { GolMessage } from './GolMessage'
import { GolInput } from './GolInput'
import { GolSuggestions } from './GolSuggestions'
import { Button } from '@/components/ui/button'
import { Trash2 } from 'lucide-react'

export function GolChatWindow({ messages, isStreaming, sendMessage, clearChat, stopStreaming, expanded }) {
  const scrollRef = useRef(null)
  const bottomRef = useRef(null)
  const prefersReducedMotion = useRef(
    typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  )

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: prefersReducedMotion.current ? 'instant' : 'smooth' })
  }, [messages])

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <div
        ref={scrollRef}
        className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden overscroll-contain px-4 py-3"
      >
        {messages.length === 0 ? (
          <GolSuggestions onSelect={sendMessage} />
        ) : (
          <div className="space-y-4 min-w-0">
            {messages.map(msg => (
              <GolMessage key={msg.id} message={msg} expanded={expanded} />
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      <div className="border-t px-4 py-3">
        {messages.length > 0 && (
          <div className="flex justify-end mb-2">
            <Button variant="ghost" size="sm" onClick={clearChat} className="text-xs text-muted-foreground">
              <Trash2 className="h-3 w-3 mr-1" /> Clear
            </Button>
          </div>
        )}
        <GolInput onSend={sendMessage} isStreaming={isStreaming} onStop={stopStreaming} />
      </div>
    </div>
  )
}
