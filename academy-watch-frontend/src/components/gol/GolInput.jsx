import { useState, useRef } from 'react'
import { Button } from '@/components/ui/button'
import { Send, Square } from 'lucide-react'

export function GolInput({ onSend, isStreaming, onStop, disabled = false }) {
  const [text, setText] = useState('')
  const inputRef = useRef(null)

  const handleSend = () => {
    const trimmed = text.trim()
    if (!trimmed || isStreaming || disabled) return
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
    <div className="flex items-center gap-2 rounded-full border border-chalk/30 py-1.5 pl-5 pr-1.5 focus-within:border-gold">
      <input
        ref={inputRef}
        type="text"
        autoComplete="off"
        value={text}
        onChange={e => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Ask about any player or team…"
        disabled={isStreaming || disabled}
        aria-label="Ask GOL"
        className="min-w-0 flex-1 border-0 bg-transparent py-2 text-[15px] text-chalk placeholder:text-[#8C9791] focus-visible:outline-none disabled:opacity-60"
      />
      {isStreaming ? (
        <Button size="icon" variant="destructive" className="rounded-full" onClick={onStop} aria-label="Stop generating">
          <Square className="h-4 w-4" />
        </Button>
      ) : (
        <Button size="icon" variant="on-dark" className="rounded-full" onClick={handleSend} disabled={disabled || !text.trim()} aria-label="Send message">
          <Send className="h-4 w-4" />
        </Button>
      )}
    </div>
  )
}
