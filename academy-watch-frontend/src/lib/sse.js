/** Parse SSE text incrementally; only a blank line commits an event. */
export function createSseParser(onEvent) {
  let eventType = ''
  let dataLines = []
  let partialLine = ''
  let skipLf = false

  function lineReceived(line) {
    if (line === '') {
      const event = { type: eventType || 'message', data: dataLines.join('\n') }
      const hasData = dataLines.length > 0
      eventType = ''
      dataLines = []
      if (hasData) onEvent(event)
      return
    }
    if (line.startsWith(':')) return
    const colon = line.indexOf(':')
    const field = colon === -1 ? line : line.slice(0, colon)
    let value = colon === -1 ? '' : line.slice(colon + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    if (field === 'event') eventType = value
    if (field === 'data') dataLines.push(value)
  }

  return {
    push(chunkText) {
      for (const char of chunkText) {
        if (skipLf) {
          skipLf = false
          if (char === '\n') continue
        }
        if (char === '\r' || char === '\n') {
          const line = partialLine
          partialLine = ''
          skipLf = char === '\r'
          lineReceived(line)
        } else {
          partialLine += char
        }
      }
    },
    flush() {
      // EOF does not dispatch a frame lacking its terminating blank line.
      eventType = ''
      dataLines = []
      partialLine = ''
      skipLf = false
    },
  }
}
