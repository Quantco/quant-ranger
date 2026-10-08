const LOCAL_DATE_TIME = new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'short' })
const UTC_DATE_TIME = new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC' })
const MILLISECONDS_PER_MINUTE = 60_000
const DAYS_IN_AGE_COLOR_SCALE = 90
const MILLISECONDS_PER_DAY = 86_400_000

export const formatDateTime = (value: Date | string, { timeZone }: { timeZone?: 'UTC' } = {}): string | null => {
  const date = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(date.valueOf())) return null
  const utc = timeZone === 'UTC'
  return `${(utc ? UTC_DATE_TIME : LOCAL_DATE_TIME).format(date)}${utc ? ' UTC' : ''}`
}

export const formatRelativeTime = (value: Date | string, now = Date.now()): string | null => {
  const timestamp = value instanceof Date ? value.getTime() : new Date(value).getTime()
  if (Number.isNaN(timestamp)) return null

  const minutes = Math.max(0, Math.floor((now - timestamp) / MILLISECONDS_PER_MINUTE))
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`

  const hours = Math.floor(minutes / 60)
  return hours < 24 ? `${hours}h ago` : `${Math.floor(hours / 24)}d ago`
}

export const ageInDays = (value: string | Date, now = Date.now()): number | null => {
  const timestamp = new Date(value).getTime()
  return Number.isNaN(timestamp) ? null : Math.max(0, (now - timestamp) / MILLISECONDS_PER_DAY)
}

export const formatAge = (value: string | Date): string => {
  const daysSinceUpdate = ageInDays(value)
  if (daysSinceUpdate == null) return '-'
  const hours = daysSinceUpdate * 24
  if (hours < 24) return `${Math.floor(hours)}h`
  const days = Math.floor(hours / 24)
  if (days < 365) return `${days}d`
  return `${(days / 365).toFixed(1)}y`
}

export const ageColor = (value: string | Date): string | undefined => {
  const daysSinceUpdate = ageInDays(value)
  if (daysSinceUpdate == null) return undefined
  const hue = 120 * (1 - Math.min(daysSinceUpdate / DAYS_IN_AGE_COLOR_SCALE, 1))
  return `oklch(90% 0.1 ${hue})`
}
