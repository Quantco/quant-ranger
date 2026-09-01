export type DisplayValue = boolean | Date | null | number | string | undefined

export function displayValue(value: unknown): string {
  if (value == null || value === '') return '-'
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? '-' : value.toISOString()
  if (typeof value === 'string') return value
  if (typeof value === 'boolean' || typeof value === 'number') return String(value)
  return '-'
}
