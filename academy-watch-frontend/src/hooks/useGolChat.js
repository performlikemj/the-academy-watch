import { useState, useCallback, useRef } from 'react'
import { APIService } from '@/lib/api'

/**
 * Build API history from messages, including tool-call context.
 * Each message may carry hiddenHistory entries (assistant tool_calls + tool results)
 * that must be replayed so the model retains context across turns.
 */
function buildHistory(messages) {
  const history = []
  for (const m of messages) {
    // Insert tool-call context entries first (assistant w/ tool_calls + tool results)
    if (m.hiddenHistory?.length) {
      for (const entry of m.hiddenHistory) {
        history.push(entry)
      }
    }
    // Then the visible message itself
    history.push({ role: m.role, content: m.content })
  }
  return history.slice(-20)
}

export function useGolChat() {
  const [messages, setMessages] = useState([])
  // Each message: {id, role, content, dataCards, toolCall, hiddenHistory}
  const [isStreaming, setIsStreaming] = useState(false)
  const [sessionId] = useState(() => crypto.randomUUID())
  const abortRef = useRef(null)

  const sendMessage = useCallback(async (content) => {
    const userMsg = { id: Date.now(), role: 'user', content, dataCards: [], hiddenHistory: [] }
    const assistantMsg = { id: Date.now() + 1, role: 'assistant', content: '', dataCards: [], toolCall: null, hiddenHistory: [] }

    setMessages(prev => [...prev, userMsg, assistantMsg])
    setIsStreaming(true)

    const controller = new AbortController()
    abortRef.current = controller

    try {
      // Build history with tool-call context from previous turns
      const history = buildHistory(messages)

      const response = await APIService.streamChat(content, history, sessionId, controller.signal)

      if (!response.ok) {
        const errorText = await response.text().catch(() => 'Unknown error')
        throw new Error(`Chat request failed (${response.status}): ${errorText}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })

        // Parse SSE events from buffer
        const lines = buffer.split('\n')
        buffer = lines.pop() || '' // Keep incomplete line in buffer

        let eventType = 'token'
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))

              if (eventType === 'token') {
                setMessages(prev => {
                  const updated = [...prev]
                  const last = { ...updated[updated.length - 1] }
                  last.content += data.content || ''
                  updated[updated.length - 1] = last
                  return updated
                })
              } else if (eventType === 'replace') {
                // Output guard corrected the response — swap content
                setMessages(prev => {
                  const updated = [...prev]
                  const last = { ...updated[updated.length - 1] }
                  last.content = data.content || ''
                  updated[updated.length - 1] = last
                  return updated
                })
              } else if (eventType === 'data_card') {
                setMessages(prev => {
                  const updated = [...prev]
                  const last = { ...updated[updated.length - 1] }
                  last.dataCards = [...last.dataCards, data]
                  updated[updated.length - 1] = last
                  return updated
                })
              } else if (eventType === 'tool_call') {
                setMessages(prev => {
                  const updated = [...prev]
                  const last = { ...updated[updated.length - 1] }
                  last.toolCall = data.name
                  updated[updated.length - 1] = last
                  return updated
                })
              } else if (eventType === 'history_entries') {
                // Store tool-call context for replay in future turns
                setMessages(prev => {
                  const updated = [...prev]
                  const last = { ...updated[updated.length - 1] }
                  last.hiddenHistory = [...last.hiddenHistory, ...(data.entries || [])]
                  updated[updated.length - 1] = last
                  return updated
                })
              } else if (eventType === 'done') {
                setMessages(prev => {
                  const updated = [...prev]
                  const last = { ...updated[updated.length - 1] }
                  last.toolCall = null
                  updated[updated.length - 1] = last
                  return updated
                })
              }
            } catch {
              // Skip malformed data
            }
            eventType = 'token' // Reset for next event
          }
        }
      }
    } catch (e) {
      if (e.name !== 'AbortError') {
        setMessages(prev => {
          const updated = [...prev]
          const last = { ...updated[updated.length - 1] }
          last.content = 'Sorry, something went wrong. Please try again.'
          updated[updated.length - 1] = last
          return updated
        })
      }
    } finally {
      setIsStreaming(false)
    }
  }, [messages, sessionId])

  const clearChat = useCallback(() => setMessages([]), [])
  const stopStreaming = useCallback(() => { abortRef.current?.abort() }, [])

  return { messages, isStreaming, sendMessage, clearChat, stopStreaming }
}
