import { useState, useCallback, useEffect, useRef } from 'react'
import { APIService } from '@/lib/api'

/**
 * Build API history from messages, including tool-call context.
 * Each message may carry hiddenHistory entries (assistant tool_calls + tool results)
 * that must be replayed so the model retains context across turns.
 */
function buildHistory(messages) {
  const history = []
  for (const message of messages) {
    if (message.hiddenHistory?.length) {
      for (const entry of message.hiddenHistory) history.push(entry)
    }
    history.push({ role: message.role, content: message.content })
  }
  return history.slice(-20)
}

function questionId() {
  return crypto.randomUUID().replace(/-/g, '')
}

function finiteBalance(value) {
  return Number.isFinite(value) ? value : null
}

export function useGolChat(identityKey, initialUsage = {}) {
  const initialFreeQuestions = finiteBalance(initialUsage.freeQuestionsRemaining)
  const initialCreditBalance = finiteBalance(initialUsage.creditBalance)
  const [messages, setMessages] = useState([])
  // Each message: {id, role, content, dataCards, toolCall, hiddenHistory}
  const [isStreaming, setIsStreaming] = useState(false)
  const [sessionId, setSessionId] = useState(() => crypto.randomUUID())
  const [usage, setUsage] = useState(() => ({
    authFree: initialFreeQuestions,
    authCredit: initialCreditBalance,
    free: initialFreeQuestions,
    credit: initialCreditBalance,
  }))
  const [topUpPath, setTopUpPath] = useState('/account/billing')
  const [failedAttempt, setFailedAttempt] = useState(null)
  const [creditsExhausted, setCreditsExhausted] = useState(false)
  const abortRef = useRef(null)
  const requestEpochRef = useRef(0)
  const previousIdentityRef = useRef(identityKey)
  const authUsageChanged = usage.authFree !== initialFreeQuestions || usage.authCredit !== initialCreditBalance
  const freeQuestionsRemaining = authUsageChanged ? initialFreeQuestions : usage.free
  const creditBalance = authUsageChanged ? initialCreditBalance : usage.credit

  const updateUsage = useCallback((usage) => {
    setUsage((current) => ({
      authFree: initialFreeQuestions,
      authCredit: initialCreditBalance,
      free: Number.isFinite(usage?.free_questions_remaining)
        ? usage.free_questions_remaining
        : current.free,
      credit: Number.isFinite(usage?.credit_balance)
        ? usage.credit_balance
        : current.credit,
    }))
    if ((usage?.free_questions_remaining || 0) > 0 || (usage?.credit_balance || 0) > 0) {
      setCreditsExhausted(false)
    }
    if (typeof usage?.top_up_path === 'string' && usage.top_up_path.startsWith('/')) {
      setTopUpPath(usage.top_up_path)
    }
  }, [initialCreditBalance, initialFreeQuestions])

  const resetChat = useCallback(() => {
    requestEpochRef.current += 1
    abortRef.current?.abort()
    abortRef.current = null
    setMessages([])
    setIsStreaming(false)
    setSessionId(crypto.randomUUID())
    setFailedAttempt(null)
    setCreditsExhausted(false)
    setTopUpPath('/account/billing')
    setUsage({
      authFree: initialFreeQuestions,
      authCredit: initialCreditBalance,
      free: initialFreeQuestions,
      credit: initialCreditBalance,
    })
  }, [initialCreditBalance, initialFreeQuestions])

  useEffect(() => {
    if (Object.is(previousIdentityRef.current, identityKey)) return
    previousIdentityRef.current = identityKey
    resetChat()
  }, [identityKey, resetChat])

  useEffect(() => () => {
    requestEpochRef.current += 1
    abortRef.current?.abort()
  }, [])

  const runAttempt = useCallback(async ({ content, history, clientMsgId, replaceMessageIds = [] }) => {
    const requestEpoch = requestEpochRef.current
    const userMsg = { id: crypto.randomUUID(), role: 'user', content, dataCards: [], hiddenHistory: [] }
    const assistantMsg = { id: crypto.randomUUID(), role: 'assistant', content: '', dataCards: [], toolCall: null, hiddenHistory: [] }
    const replaceIds = new Set(replaceMessageIds)

    const updateMessages = (updater) => {
      setMessages((previous) => requestEpoch === requestEpochRef.current ? updater(previous) : previous)
    }

    setMessages((previous) => [
      ...previous.filter((message) => !replaceIds.has(message.id)),
      userMsg,
      assistantMsg,
    ])
    setFailedAttempt(null)
    setIsStreaming(true)

    const controller = new AbortController()
    abortRef.current = controller
    let terminalError = false

    try {
      const response = await APIService.streamChat(
        content,
        history,
        sessionId,
        clientMsgId,
        controller.signal,
      )

      if (!response.ok) {
        const errorText = await response.text().catch(() => '')
        let body = null
        try { body = errorText ? JSON.parse(errorText) : null } catch { /* non-JSON response */ }

        const isSignedOut = response.status === 401
        const isLegacyLock = response.status === 403
          && body?.error === 'scout_pro_required'
          && body?.feature === 'gol_chat'
        const isExhausted = response.status === 402
          && body?.error === 'credits_exhausted'
          && body?.feature === 'gol_chat'

        if (isSignedOut || isLegacyLock || isExhausted) {
          updateMessages((previous) => previous.filter(
            (message) => message.id !== userMsg.id && message.id !== assistantMsg.id,
          ))
          if (isExhausted) {
            updateUsage(body)
            setCreditsExhausted(true)
            setFailedAttempt({ content, history, clientMsgId, messageIds: [] })
          }
          return
        }
        throw new Error(`Chat request failed (${response.status})`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        let eventType = 'token'
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))

              if (eventType === 'token') {
                updateMessages((previous) => {
                  const updated = [...previous]
                  const last = { ...updated[updated.length - 1] }
                  last.content += data.content || ''
                  updated[updated.length - 1] = last
                  return updated
                })
              } else if (eventType === 'replace') {
                updateMessages((previous) => {
                  const updated = [...previous]
                  const last = { ...updated[updated.length - 1] }
                  last.content = data.content || ''
                  updated[updated.length - 1] = last
                  return updated
                })
              } else if (eventType === 'data_card') {
                updateMessages((previous) => {
                  const updated = [...previous]
                  const last = { ...updated[updated.length - 1] }
                  last.dataCards = [...last.dataCards, data]
                  updated[updated.length - 1] = last
                  return updated
                })
              } else if (eventType === 'tool_call') {
                updateMessages((previous) => {
                  const updated = [...previous]
                  const last = { ...updated[updated.length - 1] }
                  last.toolCall = data.name
                  updated[updated.length - 1] = last
                  return updated
                })
              } else if (eventType === 'history_entries') {
                updateMessages((previous) => {
                  const updated = [...previous]
                  const last = { ...updated[updated.length - 1] }
                  last.hiddenHistory = [...last.hiddenHistory, ...(data.entries || [])]
                  updated[updated.length - 1] = last
                  return updated
                })
              } else if (eventType === 'usage') {
                updateUsage(data)
              } else if (eventType === 'error') {
                terminalError = true
                updateMessages((previous) => {
                  const updated = [...previous]
                  const last = { ...updated[updated.length - 1] }
                  last.content = 'Sorry, something went wrong. Please try again.'
                  last.toolCall = null
                  updated[updated.length - 1] = last
                  return updated
                })
                setFailedAttempt({
                  content,
                  history,
                  clientMsgId,
                  messageIds: [userMsg.id, assistantMsg.id],
                })
              } else if (eventType === 'done') {
                updateMessages((previous) => {
                  const updated = [...previous]
                  const last = { ...updated[updated.length - 1] }
                  last.toolCall = null
                  updated[updated.length - 1] = last
                  return updated
                })
                if (!terminalError) setFailedAttempt(null)
              }
            } catch {
              // Skip malformed event data without breaking the stream.
            }
            eventType = 'token'
          }
        }
      }
    } catch (error) {
      if (error.name !== 'AbortError') {
        updateMessages((previous) => {
          const updated = [...previous]
          const last = { ...updated[updated.length - 1] }
          last.content = 'Sorry, something went wrong. Please try again.'
          updated[updated.length - 1] = last
          return updated
        })
        setFailedAttempt({
          content,
          history,
          clientMsgId,
          messageIds: [userMsg.id, assistantMsg.id],
        })
      }
    } finally {
      if (requestEpoch === requestEpochRef.current) {
        abortRef.current = null
        setIsStreaming(false)
      }
    }
  }, [sessionId, updateUsage])

  const sendMessage = useCallback((content) => runAttempt({
    content,
    history: buildHistory(messages),
    clientMsgId: questionId(),
  }), [messages, runAttempt])

  const retryFailedMessage = useCallback(() => {
    if (!failedAttempt || isStreaming) return
    return runAttempt({
      content: failedAttempt.content,
      history: failedAttempt.history,
      clientMsgId: failedAttempt.clientMsgId,
      replaceMessageIds: failedAttempt.messageIds,
    })
  }, [failedAttempt, isStreaming, runAttempt])

  const clearChat = resetChat
  const stopStreaming = useCallback(() => { abortRef.current?.abort() }, [])

  return {
    messages,
    isStreaming,
    sendMessage,
    retryFailedMessage,
    canRetry: Boolean(failedAttempt),
    freeQuestionsRemaining,
    creditBalance,
    topUpPath,
    creditsExhausted: authUsageChanged ? false : creditsExhausted,
    clearChat,
    stopStreaming,
  }
}
