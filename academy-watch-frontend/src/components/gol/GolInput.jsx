import { useState, useRef } from 'react'
import { Button } from '@/components/ui/button'
import { Send, Square } from 'lucide-react'

export function GolInput({ onSend, isStreaming, onStop }) {
  const [text, setText] = useState('')
  const inputRef = useRef(null)

  const handleSend = () => {
    const trimmed = text.trim()
    if (!trimmed || isStreaming) return
    onSend(trimmed)
    setText('')
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex gap-2">
      <input
        ref={inputRef}
        type="text"
        autoComplete="off"
        value={text}
        onChange={e => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Ask about any player or team…"
        disabled={isStreaming}
        className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      />
      {isStreaming ? (
        <Button size="icon" variant="destructive" onClick={onStop} aria-label="Stop generating">
          <Square className="h-4 w-4" />
        </Button>
      ) : (
        <Button size="icon" onClick={handleSend} disabled={!text.trim()} aria-label="Send message">
          <Send className="h-4 w-4" />
        </Button>
      )}
    </div>
  )
}
