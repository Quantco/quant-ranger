const DAYS_IN_AGE_COLOR_SCALE = 90
const MILLISECONDS_PER_DAY = 86_400_000

export function ageInDays(value: string | Date, now = Date.now()): number | null {
  const timestamp = new Date(value).getTime()
  return Number.isNaN(timestamp) ? null : Math.max(0, (now - timestamp) / MILLISECONDS_PER_DAY)
}

export function formatAge(value: string | Date): string {
  const daysSinceUpdate = ageInDays(value)
  if (daysSinceUpdate == null) return '-'
  const hours = daysSinceUpdate * 24
  if (hours < 24) return `${Math.floor(hours)}h`
  const days = Math.floor(hours / 24)
  if (days < 365) return `${days}d`
  return `${(days / 365).toFixed(1)}y`
}

export function ageColor(value: string | Date): string | undefined {
  const daysSinceUpdate = ageInDays(value)
  if (daysSinceUpdate == null) return undefined
  const hue = 120 * (1 - Math.min(daysSinceUpdate / DAYS_IN_AGE_COLOR_SCALE, 1))
  return `oklch(90% 0.1 ${hue})`
}
