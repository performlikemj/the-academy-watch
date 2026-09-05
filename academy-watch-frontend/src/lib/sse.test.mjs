import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createSseParser } from './sse.js'

const frame = (type, data) => `event: ${type}\ndata: ${JSON.stringify(data)}\n\n`
const sampleEvents = [
  { type: 'usage', data: { free_questions_remaining: 2, credit_balance: 7 } },
  { type: 'token', data: { content: 'Académie ⚽' } },
  { type: 'replace', data: { content: 'Replacement answer' } },
  { type: 'data_card', data: { type: 'player', player_id: 42 } },
  { type: 'history_entries', data: { entries: [{ role: 'tool', content: 'Hidden context' }] } },
  { type: 'error', data: { error: 'generation_failed' } },
  { type: 'done', data: {} },
]
const sample = sampleEvents.map(({ type, data }) => frame(type, data)).join('')
const expected = sampleEvents.map(({ type, data }) => ({ type, data: JSON.stringify(data) }))

function parse(chunks) {
  const events = []
  const parser = createSseParser((event) => events.push(event))
  for (const chunk of chunks) parser.push(chunk)
  parser.flush()
  return events
}

for (const newline of ['\n', '\r', '\r\n']) {
  test(`parser preserves all seven frame types at every split with ${JSON.stringify(newline)}`, () => {
    const text = sample.replaceAll('\n', newline)
    for (let split = 0; split <= text.length; split++) {
      assert.deepEqual(parse([text.slice(0, split), text.slice(split)]), expected, `split ${split}`)
    }
    assert.deepEqual(parse([...text]), expected)
  })
}

test('multiple frames in one chunk and usage/token/error sample at every split', () => {
  assert.deepEqual(parse([sample]), expected)
  const events = [sampleEvents[0], sampleEvents[1], sampleEvents[5]]
  const text = events.map(({ type, data }) => frame(type, data)).join('')
  for (let split = 0; split <= text.length; split++) {
    assert.deepEqual(parse([text.slice(0, split), text.slice(split)]), events.map(({ type, data }) => ({ type, data: JSON.stringify(data) })))
  }
})

test('streaming TextDecoder preserves every byte split, including multibyte characters', () => {
  const bytes = new TextEncoder().encode(sample)
  for (let split = 0; split <= bytes.length; split++) {
    const decoder = new TextDecoder()
    assert.deepEqual(parse([
      decoder.decode(bytes.slice(0, split), { stream: true }),
      decoder.decode(bytes.slice(split), { stream: true }),
      decoder.decode(),
    ]), expected, `byte split ${split}`)
  }
})

test('event-only frame resets type; optional event, empty data, comments and multiline data', () => {
  assert.deepEqual(parse([
    'event: usage\n\n: comment\ndata:no space\ndata: second line\n: ignored\ndata:\n\n',
    'event:\ndata\n\nunknown: ignored\nid: 17\nretry: 20\ndata:  one leading space\n\n',
  ]), [
    { type: 'message', data: 'no space\nsecond line\n' },
    { type: 'message', data: '' },
    { type: 'message', data: ' one leading space' },
  ])
})

test('mixed CR/LF/CRLF boundaries dispatch only at blank lines', () => {
  assert.deepEqual(parse(['event: usage\r', '\ndata:x\r', '\n\r', '\ndata:y\n\ndata:z\r\r']), [
    { type: 'usage', data: 'x' }, { type: 'message', data: 'y' }, { type: 'message', data: 'z' },
  ])
})

test('flush discards every form of unterminated frame and clears all state', () => {
  for (const tail of ['event: usage', 'event: usage\n', 'event: usage\ndata:x', 'event: usage\ndata:x\n']) {
    const events = []
    const parser = createSseParser((event) => events.push(event))
    parser.push(tail)
    parser.flush()
    parser.flush()
    assert.deepEqual(events, [])
    parser.push('data:y\n\n')
    assert.deepEqual(events, [{ type: 'message', data: 'y' }])
  }
})

// Run the actual hook source with a minimal synchronous hook runtime. This keeps
// the Node runner dependency-free; billing E2E also exercises the mounted React UI.
const hookSource = (await readFile(new URL('../hooks/useGolChat.js', import.meta.url), 'utf8'))
  .replace(/^import .*\n/gm, '')
  .replace('export function useGolChat', 'function useGolChat')

function mountChat(streamChat, { lit = true, decoder = TextDecoder } = {}) {
  const slots = []
  let cursor = 0
  const hooks = {
    useState(initial) {
      const i = cursor++
      if (!(i in slots)) slots[i] = typeof initial === 'function' ? initial() : initial
      return [slots[i], (value) => { slots[i] = typeof value === 'function' ? value(slots[i]) : value }]
    },
    useRef(initial) {
      const i = cursor++
      if (!(i in slots)) slots[i] = { current: initial }
      return slots[i]
    },
    useCallback(callback) { return callback },
    useEffect() {},
  }
  const useGolChat = new Function('hooks', 'APIService', 'createSseParser', 'TextDecoder',
    `const { useState, useRef, useCallback, useEffect } = hooks;\n${hookSource}\nreturn useGolChat`,
  )(hooks, { streamChat }, createSseParser, decoder)
  return () => {
    cursor = 0
    return useGolChat('account-a', { freeQuestionsRemaining: 3, creditBalance: 0 }, lit)
  }
}

function streamResponse(text) {
  const bytes = new TextEncoder().encode(text)
  let offset = 0
  return new Response(new ReadableStream({
    pull(controller) {
      if (offset === bytes.length) controller.close()
      else controller.enqueue(bytes.slice(offset, ++offset))
    },
  }))
}

function deferred() {
  let resolve
  let reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

test('hook decodes real one-byte chunks, replaces text, keeps cards/history and updates usage', async () => {
  const calls = []
  const hidden = [{ role: 'assistant', tool_calls: [{ id: 'tool-1' }], content: null }, { role: 'tool', tool_call_id: 'tool-1', content: 'Private context' }]
  const card = { type: 'player', player_id: 42 }
  let decoderFlushed = 0
  class ObservedDecoder extends TextDecoder {
    decode(...args) {
      if (!args.length) decoderFlushed++
      return super.decode(...args)
    }
  }
  const chat = mountChat(async (...args) => {
    calls.push(args)
    return streamResponse(frame('usage', { free_questions_remaining: 2, credit_balance: 9 })
      + frame('token', { content: 'Draft' }) + frame('tool_call', { name: 'lookup' })
      + frame('replace', { content: 'Académie ⚽' }) + frame('data_card', card)
      + frame('history_entries', { entries: hidden }) + frame('done', {}))
  }, { decoder: ObservedDecoder })
  await chat().sendMessage('First question')
  const state = chat()
  assert.equal(state.messages[1].content, 'Académie ⚽')
  assert.deepEqual(state.messages[1].dataCards, [card])
  assert.deepEqual(state.messages[1].hiddenHistory, hidden)
  assert.equal(state.messages[1].toolCall, null)
  assert.equal(state.freeQuestionsRemaining, 2)
  assert.equal(state.creditBalance, 9)
  assert.equal(state.canRetry, false)
  assert.equal(state.isStreaming, false)
  assert.equal(decoderFlushed, 1)
  await chat().sendMessage('Follow-up')
  assert.deepEqual(calls[1][1], [{ role: 'user', content: 'First question' }, ...hidden, { role: 'assistant', content: 'Académie ⚽' }])
})

for (const failure of ['402', 'error', 'eof', 'unterminated-done', 'network', 'read-error']) {
  test(`hook allows same-id, same-history retry after ${failure}`, async () => {
    const calls = []
    const chat = mountChat(async (...args) => {
      calls.push(args)
      if (calls.length > 1) return streamResponse(frame('token', { content: 'Recovered' }) + frame('done', {}))
      if (failure === '402') return new Response(JSON.stringify({ error: 'credits_exhausted', feature: 'gol_chat', free_questions_remaining: 0, credit_balance: 0 }), { status: 402 })
      if (failure === 'network') throw new TypeError('Connection lost')
      if (failure === 'read-error') {
        let emitted = false
        return new Response(new ReadableStream({
          pull(controller) {
            if (emitted) throw new TypeError('Connection dropped during the answer')
            emitted = true
            controller.enqueue(new TextEncoder().encode(frame('token', { content: 'Partial answer' })))
          },
        }))
      }
      return streamResponse(frame('token', { content: 'Partial answer' }) + (failure === 'error'
        ? frame('error', { error: 'generation_failed' }) + frame('usage', { free_questions_remaining: 3 }) + frame('done', {})
        : failure === 'unterminated-done' ? 'event: done\ndata: {}\n' : ''))
    })
    await chat().sendMessage('Retry this')
    let state = chat()
    assert.equal(state.canRetry, true)
    assert.equal(state.isStreaming, false)
    if (failure === '402') {
      assert.equal(state.creditsExhausted, true)
      assert.deepEqual(state.messages, [])
    } else {
      assert.equal(state.messages[1].error, true)
      assert.equal(state.messages[1].incomplete, failure !== 'error')
    }
    await state.retryFailedMessage()
    state = chat()
    assert.equal(calls.length, 2)
    assert.equal(calls[1][3], calls[0][3])
    assert.deepEqual(calls[1][1], calls[0][1])
    assert.equal(calls[1][2], calls[0][2])
    assert.equal(state.messages.length, 2)
    assert.equal(state.messages[1].content, 'Recovered')
    assert.equal(state.canRetry, false)
  })
}

test('hook accepts default token events and skips malformed data without losing the next frame', async () => {
  const chat = mountChat(async () => streamResponse('event: usage\n\ndata:{bad json}\n\ndata:null\n\ndata:{"content":"Default answer"}\n\n' + frame('done', {})))
  await chat().sendMessage('Question')
  assert.equal(chat().messages[1].content, 'Default answer')
  assert.equal(chat().canRetry, false)
})

test('incomplete stream is an error even when credit UI is dark', async () => {
  const chat = mountChat(async () => streamResponse(frame('token', { content: 'Partial' })), { lit: false })
  await chat().sendMessage('Question')
  assert.equal(chat().messages[1].incomplete, true)
  assert.equal(chat().messages[1].error, true)
  assert.equal(chat().canRetry, true)
})

for (const lateResult of ['402-body', 'fetch', 'stream', 'rejection']) {
  test(`reset chat ignores delayed ${lateResult} usage and retry callbacks`, async () => {
    const pending = deferred()
    const started = deferred()
    let oldStream
    const calls = []
    const chat = mountChat(async (...args) => {
      calls.push(args)
      if (calls.length > 1) return streamResponse(frame('error', { error: 'generation_failed' }))
      if (lateResult === '402-body') return { ok: false, status: 402, text() { started.resolve(); return pending.promise } }
      if (lateResult === 'stream') return new Response(new ReadableStream({ start(controller) { oldStream = controller; started.resolve() } }))
      started.resolve()
      return pending.promise
    })
    const oldAttempt = chat().sendMessage('Old question')
    await started.promise
    // Let streamChat resolve and reader.read become pending before resetting.
    await new Promise((resolve) => setImmediate(resolve))
    chat().clearChat()
    await chat().sendMessage('New question')
    const before = chat()
    assert.equal(before.canRetry, true)
    if (lateResult === '402-body') pending.resolve(JSON.stringify({ error: 'credits_exhausted', feature: 'gol_chat', free_questions_remaining: 0, credit_balance: 99, top_up_path: '/stale' }))
    if (lateResult === 'fetch') pending.resolve(streamResponse(frame('usage', { credit_balance: 99 }) + frame('done', {})))
    if (lateResult === 'rejection') pending.reject(new TypeError('Late connection failure'))
    if (lateResult === 'stream') {
      oldStream.enqueue(new TextEncoder().encode(frame('usage', { credit_balance: 99, top_up_path: '/stale' }) + frame('error', {}) + frame('done', {})))
      oldStream.close()
    }
    await oldAttempt
    const after = chat()
    for (const key of ['messages', 'canRetry', 'isStreaming', 'freeQuestionsRemaining', 'creditBalance', 'topUpPath', 'creditsExhausted']) {
      assert.deepEqual(after[key], before[key], key)
    }
    await after.retryFailedMessage()
    assert.equal(calls[2][0], 'New question')
    assert.equal(calls[2][3], calls[1][3])
    assert.notEqual(calls[2][3], calls[0][3])
  })
}

for (const received of ['nothing', 'metadata', 'text', 'card']) {
  for (const ending of ['stop', 'network-cut', 'network-abort']) {
    test(`${ending} after ${received}: only user stop preserves the partial answer without an error`, async () => {
      const started = deferred()
      const calls = []
      let stream
      const partial = received === 'text' ? 'Partial Académie answer' : ''
      const cards = received === 'card' ? [{ type: 'fixture', payload: { result: 'Partial card' } }] : []
      const chat = mountChat(async (...args) => {
        calls.push(args)
        if (calls.length > 1) return streamResponse(frame('token', { content: 'Retried answer' }) + frame('done', {}))
        const signal = args[4]
        return new Response(new ReadableStream({
          start(controller) {
            stream = controller
            signal.addEventListener('abort', () => controller.error(signal.reason), { once: true })
            if (received === 'metadata') controller.enqueue(new TextEncoder().encode(
              frame('usage', { free_questions_remaining: 2 }) + frame('tool_call', { name: 'lookup' }),
            ))
            if (partial) controller.enqueue(new TextEncoder().encode(frame('token', { content: partial })))
            if (cards.length) controller.enqueue(new TextEncoder().encode(frame('data_card', cards[0])))
            started.resolve()
          },
        }))
      })
      const attempt = chat().sendMessage('Stop or disconnect?')
      await started.promise
      await new Promise((resolve) => setImmediate(resolve))
      assert.equal(chat().messages[1].content, partial)
      assert.deepEqual(chat().messages[1].dataCards, cards)
      if (ending === 'stop') chat().stopStreaming()
      else stream.error(ending === 'network-abort'
        ? new DOMException('Network aborted without a user stop', 'AbortError')
        : new TypeError('Network connection dropped'))
      await attempt
      const state = chat()
      const assistant = state.messages[1]
      const stopped = ending === 'stop'
      const retryAllowed = !stopped || (!partial && !cards.length)
      assert.equal(state.isStreaming, false)
      assert.equal(Boolean(assistant.stopped), stopped)
      assert.equal(assistant.error, !stopped)
      assert.equal(assistant.incomplete, !stopped)
      assert.equal(assistant.toolCall, null)
      assert.equal(assistant.content, stopped ? partial : 'The answer was interrupted before it finished. Please try again.')
      assert.deepEqual(assistant.dataCards, cards)
      assert.equal(state.canRetry, retryAllowed)
      await state.retryFailedMessage()
      assert.equal(calls.length, retryAllowed ? 2 : 1)
      if (retryAllowed) {
        assert.equal(calls[1][3], calls[0][3])
        assert.deepEqual(calls[1][1], calls[0][1])
        assert.equal(chat().messages[1].content, 'Retried answer')
      }
    })
  }
}

test('user stop before response headers marks an empty message stopped and permits same-id retry', async () => {
  const calls = []
  const chat = mountChat(async (...args) => {
    calls.push(args)
    if (calls.length > 1) return streamResponse(frame('token', { content: 'Retried answer' }) + frame('done', {}))
    return new Promise((_, reject) => args[4].addEventListener('abort', () => reject(args[4].reason), { once: true }))
  })
  const attempt = chat().sendMessage('Stop before headers')
  chat().stopStreaming()
  await attempt
  assert.equal(chat().messages[1].stopped, true)
  assert.equal(chat().messages[1].error, false)
  assert.equal(chat().messages[1].content, '')
  assert.equal(chat().canRetry, true)
  await chat().retryFailedMessage()
  assert.equal(calls[1][3], calls[0][3])
})

test('a replayed cut-off answer flags cutOff on the assistant message without a failed attempt', async () => {
  const calls = []
  const chat = mountChat(async (...args) => {
    calls.push(args)
    return streamResponse(
      frame('token', { content: 'Partial' })
        + frame('replace', { content: 'Replayed cut-off answer' })
        + frame('done', { partial: true, delivered_chars: 'Replayed cut-off answer'.length }),
    )
  })
  await chat().sendMessage('Cut-off question')
  const state = chat()
  const assistant = state.messages[1]
  assert.equal(assistant.content, 'Replayed cut-off answer')
  assert.equal(assistant.cutOff, true)
  assert.equal(Boolean(assistant.error), false)
  assert.equal(Boolean(assistant.stopped), false)
  assert.equal(Boolean(assistant.incomplete), false)
  assert.equal(state.canRetry, false)
  assert.equal(state.isStreaming, false)
  await state.retryFailedMessage()
  assert.equal(calls.length, 1)
  await chat().sendMessage('A brand new question')
  assert.equal(calls.length, 2)
  assert.notEqual(calls[1][3], calls[0][3])
})

test('a plain done frame leaves cutOff falsy and a partial flag on an errored stream stays inert', async () => {
  const calls = []
  let stream
  const chat = mountChat(async (...args) => {
    calls.push(args)
    if (calls.length === 1) {
      return streamResponse(frame('token', { content: 'Complete answer' }) + frame('done', {}))
    }
    if (calls.length === 2) {
      return streamResponse(frame('token', { content: 'Follow-up' }) + frame('done', { partial: false }))
    }
    return new Response(new ReadableStream({
      start(controller) {
        stream = controller
        controller.enqueue(new TextEncoder().encode(frame('token', { content: 'Doomed answer' })))
      },
    }))
  })
  await chat().sendMessage('First question')
  const state = chat()
  assert.equal(state.messages[1].content, 'Complete answer')
  assert.equal(Boolean(state.messages[1].cutOff), false)
  assert.equal(state.canRetry, false)
  await chat().sendMessage('Follow-up question')
  assert.equal(chat().messages[3].content, 'Follow-up')
  assert.equal(Boolean(chat().messages[3].cutOff), false)
  // An error after a done-carrying-partial flag must not resurrect a retry.
  const doomed = chat().sendMessage('Doomed question')
  await new Promise((resolve) => setImmediate(resolve))
  stream.error(new TypeError('Connection dropped'))
  await doomed
  const attempts = chat()
  assert.equal(attempts.messages[5].error, true)
  assert.equal(Boolean(attempts.messages[5].cutOff), false)
  assert.equal(attempts.canRetry, true)
})

for (const lit of [false, true]) {
  test(`in_flight retains the question and retries the same ID/history/session until completed (credit UI ${lit})`, async () => {
    const calls = []
    const chat = mountChat(async (...args) => {
      calls.push(args)
      return calls.length <= 2
        ? new Response(JSON.stringify({ error: 'in_flight' }), { status: 409 })
        : streamResponse(frame('token', { content: 'Completed answer' }) + frame('done', {}))
    }, { lit })
    await chat().sendMessage('Pending question')
    for (let attempt = 0; attempt < 2; attempt++) {
      const state = chat()
      assert.equal(state.messages.length, 2)
      assert.equal(state.messages[0].content, 'Pending question')
      assert.equal(state.messages[1].content, 'Still working on your previous question — give it a moment and try again.')
      assert.equal(Boolean(state.messages[1].incomplete), false)
      assert.equal(state.isStreaming, false)
      assert.equal(state.canRetry, true)
      await state.retryFailedMessage()
    }
    assert.equal(calls.length, 3)
    for (const call of calls) assert.deepEqual(call.slice(0, 4), calls[0].slice(0, 4))
    assert.equal(chat().messages.length, 2)
    assert.equal(chat().messages[1].content, 'Completed answer')
    assert.equal(chat().canRetry, false)
  })

  test(`recovery_exhausted keeps its notice, disables retry and assigns a new ID to a new question (credit UI ${lit})`, async () => {
    const calls = []
    const chat = mountChat(async (...args) => {
      calls.push(args)
      return calls.length === 1
        ? new Response(JSON.stringify({ error: 'recovery_exhausted' }), { status: 409 })
        : streamResponse(frame('token', { content: 'New answer' }) + frame('done', {}))
    }, { lit })
    await chat().sendMessage('Exhausted question')
    const state = chat()
    assert.equal(state.messages.length, 2)
    assert.equal(state.messages[0].content, 'Exhausted question')
    assert.equal(state.messages[1].content, 'That question could not be completed; your credit was returned.')
    assert.equal(state.isStreaming, false)
    assert.equal(state.canRetry, false)
    await state.retryFailedMessage()
    assert.equal(calls.length, 1)
    await chat().sendMessage('A new question')
    assert.equal(calls.length, 2)
    assert.notEqual(calls[1][3], calls[0][3])
    assert.equal(calls[1][0], 'A new question')
    assert.equal(chat().messages[3].content, 'New answer')
  })
}

test('recovery_exhausted clears the retry created by an earlier in_flight response', async () => {
  const calls = []
  const chat = mountChat(async (...args) => {
    calls.push(args)
    return new Response(JSON.stringify({ error: calls.length === 1 ? 'in_flight' : 'recovery_exhausted' }), { status: 409 })
  })
  await chat().sendMessage('Pending question')
  assert.equal(chat().canRetry, true)
  await chat().retryFailedMessage()
  assert.equal(calls[1][3], calls[0][3])
  assert.equal(chat().messages.length, 2)
  assert.equal(chat().messages[1].content, 'That question could not be completed; your credit was returned.')
  assert.equal(chat().canRetry, false)
  await chat().retryFailedMessage()
  assert.equal(calls.length, 2)
})

for (const error of ['in_flight', 'recovery_exhausted']) {
  test(`a delayed ${error} response cannot change retry state after a chat reset`, async () => {
    const pending = deferred()
    const started = deferred()
    const calls = []
    const chat = mountChat(async (...args) => {
      calls.push(args)
      if (calls.length === 1) return { ok: false, status: 409, text() { started.resolve(); return pending.promise } }
      return new Response(JSON.stringify({ error: 'in_flight' }), { status: 409 })
    })
    const oldAttempt = chat().sendMessage('Old question')
    await started.promise
    chat().clearChat()
    await chat().sendMessage('Current question')
    const before = chat()
    pending.resolve(JSON.stringify({ error }))
    await oldAttempt
    assert.deepEqual(chat().messages, before.messages)
    assert.equal(chat().canRetry, true)
    await chat().retryFailedMessage()
    assert.equal(calls[2][0], 'Current question')
    assert.equal(calls[2][3], calls[1][3])
  })
}
