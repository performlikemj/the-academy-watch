import { useState, useCallback, useEffect, useRef } from 'react'
import { APIService } from '@/lib/api'
import { createSseParser } from '@/lib/sse'

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

export function useGolChat(identityKey, initialUsage = {}, creditUiLit = false) {
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
    if (typeof usage?.top_up_path === 'string'
      && usage.top_up_path.startsWith('/')
      && !usage.top_up_path.startsWith('//')) {
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
    const requestEpoch = ++requestEpochRef.current
    const isCurrent = () => requestEpoch === requestEpochRef.current
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
    let receivedDone = false
    const updateAssistant = (updater) => updateMessages((previous) => previous.map(
      (message) => message.id === assistantMsg.id ? updater(message) : message,
    ))
    const failAttempt = (incomplete = false) => {
      if (!isCurrent()) return
      terminalError = true
      updateAssistant((message) => ({
        ...message,
        error: true,
        incomplete,
        content: incomplete
          ? 'The answer was interrupted before it finished. Please try again.'
          : creditUiLit ? 'Sorry, something went wrong. Please try again.' : message.content,
        toolCall: null,
      }))
      if (creditUiLit || incomplete) {
        setFailedAttempt({ content, history, clientMsgId, messageIds: [userMsg.id, assistantMsg.id] })
      }
    }

    try {
      const response = await APIService.streamChat(
        content,
        history,
        sessionId,
        clientMsgId,
        controller.signal,
      )

      if (!isCurrent()) {
        await response.body?.cancel()
        return
      }
      if (!response.ok) {
        const errorText = await response.text().catch(() => '')
        if (!isCurrent()) return
        let body = null
        try { body = errorText ? JSON.parse(errorText) : null } catch { /* non-JSON response */ }

        const isSignedOut = response.status === 401
        const isLegacyLock = response.status === 403
          && body?.error === 'scout_pro_required'
          && body?.feature === 'gol_chat'
        const isExhausted = response.status === 402
          && body?.error === 'credits_exhausted'
          && body?.feature === 'gol_chat'
        const isClientMessageReused = response.status === 409
          && body?.error === 'client_msg_id_reused'

        if (isClientMessageReused) {
          updateMessages((previous) => {
            const updated = [...previous]
            const last = { ...updated[updated.length - 1] }
            last.content = 'Please ask that as a new question.'
            updated[updated.length - 1] = last
            return updated
          })
          return
        }

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
      const parser = createSseParser(({ type, data: eventData }) => {
        if (!isCurrent() || receivedDone) return
        let data
        try { data = JSON.parse(eventData) } catch { return }
        if (!data || typeof data !== 'object') return

        // A refund usage frame may follow an error; it still updates the balance.
        if (type === 'usage') {
          updateUsage(data)
        } else if (type === 'error') {
          failAttempt()
        } else if (type === 'done') {
          receivedDone = true
          updateAssistant((message) => ({ ...message, toolCall: null }))
          if (!terminalError) setFailedAttempt(null)
        } else if (!terminalError) {
          if (type === 'token' || type === 'message') {
            updateAssistant((message) => ({ ...message, content: message.content + (data.content || '') }))
          } else if (type === 'replace') {
            updateAssistant((message) => ({ ...message, content: data.content || '' }))
          } else if (type === 'data_card') {
            updateAssistant((message) => ({ ...message, dataCards: [...message.dataCards, data] }))
          } else if (type === 'tool_call') {
            updateAssistant((message) => ({ ...message, toolCall: data.name }))
          } else if (type === 'history_entries') {
            updateAssistant((message) => ({ ...message, hiddenHistory: [...message.hiddenHistory, ...(data.entries || [])] }))
          }
        }
      })
      try {
        while (true) {
          const { done, value } = await reader.read()
          if (!isCurrent()) {
            await reader.cancel()
            return
          }
          if (done) {
            parser.push(decoder.decode())
            parser.flush()
            break
          }
          parser.push(decoder.decode(value, { stream: true }))
        }
      } finally {
        reader.releaseLock()
      }
      if (!receivedDone && !terminalError) failAttempt(true)
    } catch {
      // Includes a dropped connection or an explicit stop before completion.
      if (!receivedDone && !terminalError) failAttempt(true)
    } finally {
      if (requestEpoch === requestEpochRef.current) {
        abortRef.current = null
        setIsStreaming(false)
      }
    }
  }, [creditUiLit, sessionId, updateUsage])

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
