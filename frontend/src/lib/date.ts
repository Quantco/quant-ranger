const LOCAL_DATE_TIME = new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'short' })
const UTC_DATE_TIME = new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC' })
const MILLISECONDS_PER_MINUTE = 60_000

export function formatDateTime(value: Date | string, { timeZone }: { timeZone?: 'UTC' } = {}): string | null {
  const date = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(date.valueOf())) return null
  const utc = timeZone === 'UTC'
  return `${(utc ? UTC_DATE_TIME : LOCAL_DATE_TIME).format(date)}${utc ? ' UTC' : ''}`
}

export function formatRelativeTime(value: Date | string, now = Date.now()): string | null {
  const timestamp = value instanceof Date ? value.getTime() : new Date(value).getTime()
  if (Number.isNaN(timestamp)) return null

  const minutes = Math.max(0, Math.floor((now - timestamp) / MILLISECONDS_PER_MINUTE))
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`

  const hours = Math.floor(minutes / 60)
  return hours < 24 ? `${hours}h ago` : `${Math.floor(hours / 24)}d ago`
}
