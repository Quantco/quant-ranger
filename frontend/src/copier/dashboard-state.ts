import * as z from 'zod/mini'

import { isUnique, type ExplorerState } from '@/components/data-table/explorer-state'
import { dashboardValueSchema, REPOSITORIES, TEMPLATE, VALIDATION, VERSION, type FilterValue } from './dashboard'
import { isFilterableDashboardColumn, type DashboardColumnModel, type DashboardFilterKind } from './dashboard-columns'

const DASHBOARD_STATE_VERSION = 1
const DEFAULT_FILTER_COLUMNS = [REPOSITORIES, TEMPLATE, VERSION]
const DEFAULT_TABLE_COLUMNS = [VALIDATION, TEMPLATE, VERSION]
const dashboardFilterValueSchema = z.object({
  inverted: z.boolean(),
  values: z.array(dashboardValueSchema).check(z.minLength(1))
})

export type DashboardFilterValue = z.infer<typeof dashboardFilterValueSchema>

export type DashboardState = {
  chartColumns: string[]
  filterColumns: string[]
  version: typeof DASHBOARD_STATE_VERSION
} & ExplorerState<string, DashboardFilterValue>

export const dashboardFilterValue = (values: FilterValue[], inverted = false): DashboardFilterValue => ({
  inverted,
  values
})

export const hasDashboardFilterValue = (kind: DashboardFilterKind, filter: DashboardFilterValue): boolean =>
  filter.values.length > 0 && (kind === 'values' || String(filter.values[0]).trim() !== '')

export const parseDashboardFilterValue = (value: unknown): DashboardFilterValue | undefined => {
  const result = z.safeParse(dashboardFilterValueSchema, value)
  return result.success ? result.data : undefined
}

export const defaultDashboardState = (columns: DashboardColumnModel[]): DashboardState => ({
  chartColumns: [],
  filterColumns: DEFAULT_FILTER_COLUMNS.filter((id) =>
    columns.some((column) => column.id === id && isFilterableDashboardColumn(column))
  ),
  filters: {},
  search: '',
  sort: null,
  version: DASHBOARD_STATE_VERSION,
  visibleColumns: columns
    .filter(({ id }) => id === REPOSITORIES || DEFAULT_TABLE_COLUMNS.includes(id))
    .map(({ id }) => id)
})

const dashboardStateSchema = (columns: DashboardColumnModel[]) => {
  const columnId = z.enum(columns.map(({ id }) => id))
  const filterColumnId = z.enum(columns.filter(isFilterableDashboardColumn).map(({ id }) => id))

  return z.object({
    chartColumns: z.array(columnId),
    filterColumns: z.array(filterColumnId),
    filters: z.record(z.string(), dashboardFilterValueSchema),
    search: z.string(),
    sort: z.nullable(z.object({ column: columnId, direction: z.enum(['asc', 'desc']) })),
    version: z.literal(DASHBOARD_STATE_VERSION),
    visibleColumns: z.array(columnId)
  })
}

/** Rejects anything the current snapshot cannot render, so a stale or hand-edited URL falls back to the defaults. */
export const parseDashboardState = (value: unknown, columns: DashboardColumnModel[]): DashboardState | null => {
  const parsed = z.safeParse(dashboardStateSchema(columns), value)
  if (!parsed.success) return null
  if (!validDashboardState(parsed.data, columns)) return null
  return parsed.data
}

const validDashboardState = (state: DashboardState, columns: DashboardColumnModel[]): boolean => {
  const columnIds = new Set(columns.map(({ id }) => id))
  const filterColumnIds = new Set(columns.filter(isFilterableDashboardColumn).map(({ id }) => id))
  return (
    state.visibleColumns.includes(REPOSITORIES) &&
    isUnique(state.visibleColumns) &&
    isUnique(state.filterColumns) &&
    isUnique(state.chartColumns) &&
    state.visibleColumns.every((id) => columnIds.has(id)) &&
    state.chartColumns.every((id) => columnIds.has(id)) &&
    state.filterColumns.every((id) => filterColumnIds.has(id)) &&
    Object.keys(state.filters).every((id) => filterColumnIds.has(id) && state.filterColumns.includes(id))
  )
}
