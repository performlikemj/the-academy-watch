export const GOL_MAINTENANCE_MESSAGE = 'The assistant is under maintenance. Back soon.'

export function maintenanceRetryAt(value, now = Date.now()) {
  const seconds = Number(value)
  if (Number.isFinite(seconds)) return now + Math.max(0, seconds) * 1000
  const date = Date.parse(value)
  return Number.isFinite(date) ? Math.max(now, date) : now + 60000
}
