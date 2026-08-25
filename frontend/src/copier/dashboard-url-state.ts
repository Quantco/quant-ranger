import type { DataTableSort } from '../components/DataTable'
import { setsEqual } from '../lib/sets'
import { COPIER_ANSWERS, REPOSITORIES, TEMPLATE, VALIDATION, VERSION } from './dashboard'
import type { DashboardSnapshot, FilterValue, TextFilter, ValueFilter } from './dashboard'

export const COPIER_DASHBOARD_STATE_VERSION = 1 as const
export const DEFAULT_FILTER_COLUMNS: ReadonlySet<string> = new Set([REPOSITORIES, TEMPLATE, VERSION])
export const DEFAULT_TABLE_COLUMNS: ReadonlySet<string> = new Set([VALIDATION, TEMPLATE, VERSION])

export interface CopierDashboardUrlState {
  selectedChartColumns: Set<string>
  selectedFilterColumns: Set<string>
  selectedTableColumns: Set<string>
  sort: DataTableSort | null
  textFilters: TextFilter[]
  valueFilters: ValueFilter[]
}

/** Versioned, JSON-serializable representation stored in the URL. */
export interface StoredDashboardState {
  version: typeof COPIER_DASHBOARD_STATE_VERSION
  chartColumns?: string[]
  filterColumns?: string[]
  sort?: DataTableSort
  tableColumns?: string[]
  textFilters?: TextFilter[]
  valueFilters?: ValueFilter[]
}

export function parseStoredDashboardState(value: unknown): StoredDashboardState | null {
  if (!isRecord(value) || value.version !== COPIER_DASHBOARD_STATE_VERSION) return null

  const { chartColumns, filterColumns, sort, tableColumns, textFilters, valueFilters } = value
  if (chartColumns !== undefined && !isStringArray(chartColumns)) return null
  if (filterColumns !== undefined && !isStringArray(filterColumns)) return null
  if (tableColumns !== undefined && !isStringArray(tableColumns)) return null
  if (sort !== undefined && !isSort(sort)) return null
  if (textFilters !== undefined && (!Array.isArray(textFilters) || !textFilters.every(isTextFilter))) return null
  if (valueFilters !== undefined && (!Array.isArray(valueFilters) || !valueFilters.every(isValueFilter))) return null

  const stored: StoredDashboardState = { version: COPIER_DASHBOARD_STATE_VERSION }
  if (chartColumns !== undefined) stored.chartColumns = chartColumns
  if (filterColumns !== undefined) stored.filterColumns = filterColumns
  if (tableColumns !== undefined) stored.tableColumns = tableColumns
  if (sort !== undefined) stored.sort = sort
  if (textFilters !== undefined) stored.textFilters = textFilters
  if (valueFilters !== undefined) stored.valueFilters = valueFilters
  return stored
}

export function restoreDashboardState(
  snapshot: DashboardSnapshot,
  stored: StoredDashboardState
): CopierDashboardUrlState {
  const columns = new Set(snapshot.columns)
  const filterColumns = new Set(snapshot.columns.filter((column) => column !== COPIER_ANSWERS))
  const valueFilterColumns = new Set([
    REPOSITORIES,
    TEMPLATE,
    VERSION,
    VALIDATION,
    ...snapshot.answer_groups.flatMap(({ fields }) => fields)
  ])
  const textFilterColumns = new Set([...filterColumns].filter((column) => !valueFilterColumns.has(column)))

  const textFilters = uniqueFilters(
    (stored.textFilters ?? [])
      .filter(({ column, query }) => textFilterColumns.has(column) && query.trim() !== '')
      .map(({ column, inverted, query }) => ({ column, inverted: inverted === true || undefined, query }))
  )
  const valueFilters = uniqueFilters(
    (stored.valueFilters ?? [])
      .filter(({ column }) => valueFilterColumns.has(column))
      .map(({ column, inverted, values }) => ({ column, inverted: inverted === true || undefined, values }))
  )

  const selectedFilterColumns =
    stored.filterColumns == null
      ? new Set(DEFAULT_FILTER_COLUMNS)
      : new Set(stored.filterColumns.filter((column) => filterColumns.has(column)))
  for (const { column } of [...textFilters, ...valueFilters]) selectedFilterColumns.add(column)

  const selectedTableColumns =
    stored.tableColumns == null
      ? new Set(DEFAULT_TABLE_COLUMNS)
      : new Set(stored.tableColumns.filter((column) => column !== REPOSITORIES && columns.has(column)))
  const sort = stored.sort

  return {
    selectedChartColumns: new Set((stored.chartColumns ?? []).filter((column) => columns.has(column))),
    selectedFilterColumns,
    selectedTableColumns,
    sort: sort != null && columns.has(sort.id) ? sort : null,
    textFilters,
    valueFilters
  }
}

export function storeDashboardState(state: CopierDashboardUrlState): StoredDashboardState {
  const stored: StoredDashboardState = { version: COPIER_DASHBOARD_STATE_VERSION }

  if (state.selectedChartColumns.size > 0) stored.chartColumns = [...state.selectedChartColumns].sort()
  if (!setsEqual(state.selectedFilterColumns, DEFAULT_FILTER_COLUMNS))
    stored.filterColumns = [...state.selectedFilterColumns].sort()
  if (!setsEqual(state.selectedTableColumns, DEFAULT_TABLE_COLUMNS))
    stored.tableColumns = [...state.selectedTableColumns].sort()
  if (state.sort != null) stored.sort = { ...state.sort }
  if (state.textFilters.length > 0)
    stored.textFilters = [...state.textFilters]
      .sort(compareFilterColumns)
      .map(({ column, inverted, query }) => ({ column, inverted: inverted === true || undefined, query }))
  if (state.valueFilters.length > 0)
    stored.valueFilters = [...state.valueFilters].sort(compareFilterColumns).map(({ column, inverted, values }) => ({
      column,
      inverted: inverted === true || undefined,
      values: [...values].sort(compareFilterValues)
    }))

  return stored
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value != null && !Array.isArray(value)
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string')
}

function isFilterValue(value: unknown): value is FilterValue {
  return value === null || typeof value === 'boolean' || typeof value === 'number' || typeof value === 'string'
}

function hasValidInversion(value: Record<string, unknown>): boolean {
  return value.inverted == null || typeof value.inverted === 'boolean'
}

function isTextFilter(value: unknown): value is TextFilter {
  return (
    isRecord(value) && typeof value.column === 'string' && typeof value.query === 'string' && hasValidInversion(value)
  )
}

function isValueFilter(value: unknown): value is ValueFilter {
  return (
    isRecord(value) &&
    typeof value.column === 'string' &&
    Array.isArray(value.values) &&
    value.values.length > 0 &&
    value.values.every(isFilterValue) &&
    hasValidInversion(value)
  )
}

function isSort(value: unknown): value is NonNullable<CopierDashboardUrlState['sort']> {
  return (
    isRecord(value) &&
    typeof value.id === 'string' &&
    (value.direction === 'ascending' || value.direction === 'descending')
  )
}

function uniqueFilters<Filter extends { column: string }>(filters: Filter[]): Filter[] {
  return [...new Map(filters.map((filter) => [filter.column, filter])).values()]
}

function compareFilterColumns(left: { column: string }, right: { column: string }): number {
  return left.column < right.column ? -1 : left.column > right.column ? 1 : 0
}

function compareFilterValues(left: FilterValue, right: FilterValue): number {
  const leftKey = `${typeof left}:${JSON.stringify(left) ?? ''}`
  const rightKey = `${typeof right}:${JSON.stringify(right) ?? ''}`
  return leftKey < rightKey ? -1 : leftKey > rightKey ? 1 : 0
}
