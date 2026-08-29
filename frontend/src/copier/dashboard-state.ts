import { useCallback, useMemo } from 'react'
import * as z from 'zod/mini'

import { reduceExplorerState, type ExplorerAction, type ExplorerState } from '../components/data-table/explorer-state'
import { useCompressedUrlReducer } from '../lib/useCompressedUrlState'
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

export interface DashboardState extends ExplorerState<string, DashboardFilterValue> {
  chartColumns: string[]
  filterColumns: string[]
  version: typeof DASHBOARD_STATE_VERSION
}

export type DashboardAction =
  | ExplorerAction<string, DashboardFilterValue>
  | { columns: string[]; type: 'chart-columns/set' }
  | { columns: string[]; type: 'filter-columns/set' }

export function useDashboardState(columns: DashboardColumnModel[]) {
  const defaults = useMemo(() => defaultDashboardState(columns), [columns])
  const parse = useCallback((value: unknown) => readDashboardState(value, columns, defaults), [columns, defaults])
  return useCompressedUrlReducer({ defaultState: defaults, parse, reducer: dashboardReducer })
}

export function dashboardFilterValue(values: FilterValue[], inverted = false): DashboardFilterValue {
  return { inverted, values }
}

export function hasDashboardFilterValue(kind: DashboardFilterKind, filter: DashboardFilterValue): boolean {
  return filter.values.length > 0 && (kind === 'values' || String(filter.values[0]).trim() !== '')
}

export function parseDashboardFilterValue(value: unknown): DashboardFilterValue | undefined {
  const result = z.safeParse(dashboardFilterValueSchema, value)
  return result.success ? result.data : undefined
}

function dashboardReducer(state: DashboardState, action: DashboardAction): DashboardState {
  if (action.type === 'chart-columns/set') return { ...state, chartColumns: uniqueValues(action.columns) }
  if (action.type === 'filter-columns/set') {
    const filterColumns = uniqueValues(action.columns)
    return {
      ...state,
      filterColumns,
      filters: Object.fromEntries(Object.entries(state.filters).filter(([id]) => filterColumns.includes(id)))
    }
  }
  if (action.type === 'visible-columns/set') {
    return reduceExplorerState(state, {
      columns: [REPOSITORIES, ...uniqueValues(action.columns).filter((id) => id !== REPOSITORIES)],
      type: 'visible-columns/set'
    })
  }
  return reduceExplorerState(state, action)
}

function defaultDashboardState(columns: DashboardColumnModel[]): DashboardState {
  return {
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
  }
}

function dashboardStateSchema(columns: DashboardColumnModel[]) {
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

function readDashboardState(value: unknown, columns: DashboardColumnModel[], defaults: DashboardState): DashboardState {
  const parsed = z.safeParse(dashboardStateSchema(columns), value)
  if (!parsed.success) return defaults
  const state: DashboardState = parsed.data
  return validDashboardState(state, columns) ? state : defaults
}

function validDashboardState(state: DashboardState, columns: DashboardColumnModel[]): boolean {
  const columnIds = new Set(columns.map(({ id }) => id))
  const filterColumnIds = new Set(columns.filter(isFilterableDashboardColumn).map(({ id }) => id))
  return (
    state.visibleColumns.includes(REPOSITORIES) &&
    unique(state.visibleColumns) &&
    unique(state.filterColumns) &&
    unique(state.chartColumns) &&
    state.visibleColumns.every((id) => columnIds.has(id)) &&
    state.chartColumns.every((id) => columnIds.has(id)) &&
    state.filterColumns.every((id) => filterColumnIds.has(id)) &&
    Object.keys(state.filters).every((id) => filterColumnIds.has(id) && state.filterColumns.includes(id))
  )
}

function unique(values: string[]): boolean {
  return new Set(values).size === values.length
}

function uniqueValues(values: string[]): string[] {
  return [...new Set(values)]
}
