export const COPIER_ANSWERS = '.copier-answers.yml'
export const REPOSITORIES = 'Repositories'
export const TEMPLATE = 'Template'
export const VERSION = 'Version'
export const VALIDATION = 'Validation'

export type DashboardValue = string | number | boolean | null | undefined
export type FilterValue = Exclude<DashboardValue, undefined>

export interface AnswerGroup {
  fields: string[]
  id: string
  template: string | null
  title: string
}

export interface VersionOptions {
  template: string | null
  versions: string[]
}

export interface DashboardRow {
  repository: string
  url: string
  validation_failure: string
  values: Record<string, DashboardValue>
}

export interface DashboardSnapshot {
  answer_groups: AnswerGroup[]
  columns: string[]
  generated_at: string
  rows: DashboardRow[]
  version_options: VersionOptions[]
}

export interface ValueFilter {
  column: string
  inverted?: boolean
  values: FilterValue[]
}

export interface TextFilter {
  column: string
  inverted?: boolean
  query: string
}

export interface CountedValue {
  value: FilterValue
  count: number
}

const BOOLEAN_ANSWER_ORDER: readonly FilterValue[] = [true, false]

export function repositoryName(value: string): string {
  return value.slice(value.lastIndexOf('/') + 1)
}

/** Apply case-insensitive substring searches across selected columns. */
export function filterRowsByTextFilters(rows: DashboardRow[], filters: TextFilter[]): DashboardRow[] {
  return rows.filter((row) =>
    filters.every(({ column, inverted, query }) => {
      const matches = String(valueForFiltering(row, column) ?? '')
        .toLocaleLowerCase()
        .includes(query.trim().toLocaleLowerCase())
      return inverted ? !matches : matches
    })
  )
}

/**
 * Apply selected values using OR within a column and AND across columns.
 *
 * A value picker can omit its own column so its available choices do not
 * disappear as values are selected.
 */
export function filterRowsByValueFilters(
  rows: DashboardRow[],
  filters: ValueFilter[],
  excludedColumn: string | null = null
): DashboardRow[] {
  return rows.filter((row) =>
    filters.every(({ column, inverted, values }) => {
      if (column === excludedColumn) return true
      const rowValue = valueForFiltering(row, column)
      const matches = values.some((value) => Object.is(rowValue, value))
      return inverted ? !matches : matches
    })
  )
}

/** Remove the value filter for one column without mutating the input. */
export function removeValueFilter(filters: ValueFilter[], column: string): ValueFilter[] {
  return filters.filter((filter) => filter.column !== column)
}

/** Count non-empty values for a distribution chart. */
export function countBy(rows: DashboardRow[], column: string): CountedValue[] {
  return countValues(rows, column, (value) => (value == null || value === '' ? undefined : value)).sort(
    (left, right) => right.count - left.count
  )
}

/** Count every value for a chart, grouping all missing values together. */
export function countAllValues(rows: DashboardRow[], column: string): CountedValue[] {
  return countValues(rows, column, (value) => (value == null ? '' : value)).sort(
    (left, right) => right.count - left.count
  )
}

/**
 * Count one Copier answer while preserving the values from the JSON.
 *
 * Booleans and values such as py310 remain untouched. Only the UI labels the
 * raw empty-string sentinel.
 */
export function answerCounts(rows: DashboardRow[], column: string): CountedValue[] {
  return countValues(rows, column, (value) => (value == null ? undefined : value)).sort((left, right) => {
    if (left.value === '') return right.value === '' ? 0 : 1
    if (right.value === '') return -1

    const leftBooleanOrder = BOOLEAN_ANSWER_ORDER.indexOf(left.value)
    const rightBooleanOrder = BOOLEAN_ANSWER_ORDER.indexOf(right.value)
    if (leftBooleanOrder !== -1 || rightBooleanOrder !== -1) {
      return (
        (leftBooleanOrder === -1 ? BOOLEAN_ANSWER_ORDER.length : leftBooleanOrder) -
        (rightBooleanOrder === -1 ? BOOLEAN_ANSWER_ORDER.length : rightBooleanOrder)
      )
    }

    return compareValues(left.value, right.value)
  })
}

function valueForFiltering(row: DashboardRow, column: string): DashboardValue {
  if (column === REPOSITORIES) return row.repository
  if (column === VALIDATION) return row.validation_failure || row.values[VALIDATION]
  return row.values[column]
}

function countValues(
  rows: DashboardRow[],
  column: string,
  normalize: (value: DashboardValue) => DashboardValue
): CountedValue[] {
  const counts = new Map<FilterValue, number>()
  for (const row of rows) {
    const value = normalize(valueForFiltering(row, column))
    if (value === undefined) continue
    counts.set(value, (counts.get(value) ?? 0) + 1)
  }
  return [...counts].map(([value, count]) => ({ count, value }))
}

function compareValues(left: DashboardValue, right: DashboardValue): number {
  if (Object.is(left, right)) return 0
  if (left == null) return 1
  if (right == null) return -1
  if (typeof left === 'number' && typeof right === 'number') return left - right

  return String(left) < String(right) ? -1 : 1
}
