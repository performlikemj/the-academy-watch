// MyClub only: show Retry after a slow complete read, including its body.
// Keep the current attempt alive; callers ignore only superseded/viewer answers.
export const CLUB_ENTRY_DEADLINE_MS = 60000

export function watchEntryRead(read, onSlow, timeoutMs = CLUB_ENTRY_DEADLINE_MS) {
  const timer = setTimeout(onSlow, timeoutMs)
  return Promise.resolve().then(read)
    .finally(() => clearTimeout(timer))
}
