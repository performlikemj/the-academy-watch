import { useEffect, useRef, useState } from 'react'
import { GolMessage } from './GolMessage'
import { GolInput } from './GolInput'
import { GolSuggestions } from './GolSuggestions'
import { PlayerPreviewDrawer } from './PlayerPreviewDrawer'
import { exportChatAsMarkdown } from './exportChat'
import { Button } from '@/components/ui/button'
import { Download, Trash2 } from 'lucide-react'

export function GolChatWindow({ messages, isStreaming, sendMessage, clearChat, stopStreaming, expanded }) {
  const [previewPlayerId, setPreviewPlayerId] = useState(null)
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
              <GolMessage key={msg.id} message={msg} expanded={expanded} onPlayerClick={setPreviewPlayerId} />
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      <div className="border-t px-4 py-3">
        {messages.length > 0 && (
          <div className="flex justify-end gap-1 mb-2">
            <Button
              variant="ghost"
              size="sm"
              className="text-xs text-muted-foreground"
              onClick={() => {
                const md = exportChatAsMarkdown(messages)
                const blob = new Blob([md], { type: 'text/markdown' })
                const url = URL.createObjectURL(blob)
                const a = document.createElement('a')
                a.href = url
                a.download = `gol-chat-${new Date().toISOString().slice(0, 10)}.md`
                a.click()
                URL.revokeObjectURL(url)
              }}
            >
              <Download className="h-3 w-3 mr-1" /> Save
            </Button>
            <Button variant="ghost" size="sm" onClick={clearChat} className="text-xs text-muted-foreground">
              <Trash2 className="h-3 w-3 mr-1" /> Clear
            </Button>
          </div>
        )}
        <GolInput onSend={sendMessage} isStreaming={isStreaming} onStop={stopStreaming} />
      </div>

      <PlayerPreviewDrawer
        playerId={previewPlayerId}
        open={!!previewPlayerId}
        onOpenChange={(open) => { if (!open) setPreviewPlayerId(null) }}
      />
    </div>
  )
}
