// MyClub only: bound the complete read, including body consumption. The race also protects
// callers when a transport ignores AbortSignal: late answers never escape it.
export const CLUB_ENTRY_DEADLINE_MS = 60000

export function readWithDeadline(read, timeoutMs = CLUB_ENTRY_DEADLINE_MS) {
  const controller = new AbortController()
  let timer
  const expiry = new Promise((_, reject) => {
    timer = setTimeout(() => {
      const error = new Error('The request timed out. Please try again.')
      error.name = 'TimeoutError'
      reject(error)
      controller.abort()
    }, timeoutMs)
  })
  return Promise.race([Promise.resolve().then(() => read(controller.signal)), expiry])
    .finally(() => clearTimeout(timer))
}
