import {
  functionalUpdate,
  type ColumnFiltersState,
  type ColumnVisibilityState,
  type SortingState,
  type Updater
} from '@tanstack/react-table'
import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router'
import * as z from 'zod/mini'

import { createCompressedJsonCodec } from '../lib/compressed-json-codec'
import {
  dashboardValueSchema,
  isFilterableDashboardColumn,
  REPOSITORIES,
  TEMPLATE,
  VALIDATION,
  VERSION,
  type DashboardColumn,
  type DashboardFilterKind,
  type FilterValue
} from './dashboard'

const DEFAULT_FILTER_COLUMNS = [REPOSITORIES, TEMPLATE, VERSION]
const DEFAULT_TABLE_COLUMNS = [VALIDATION, TEMPLATE, VERSION]
const STATE_PARAMETER = 'state'
const dashboardStateCodec = createCompressedJsonCodec({
  maxCompressedLength: 10_000,
  maxDecompressedLength: 100_000
})

const dashboardFilterValueSchema = z.object({
  inverted: z.boolean(),
  values: z.array(dashboardValueSchema).check(z.minLength(1))
})

export type DashboardFilterValue = z.infer<typeof dashboardFilterValueSchema>

export interface DashboardState {
  chartColumns: string[]
  columnFilters: ColumnFiltersState
  columnVisibility: ColumnVisibilityState
  filterColumns: string[]
  sorting: SortingState
}

export function useDashboardState(columns: DashboardColumn[]) {
  const [searchParameters, setSearchParameters] = useSearchParams()
  const defaults = useMemo(() => defaultDashboardState(columns), [columns])
  const schema = useMemo(() => dashboardStateSchema(columns), [columns])
  const read = useCallback(
    (parameters: URLSearchParams) => readDashboardState(parameters, schema, defaults),
    [defaults, schema]
  )
  const state = useMemo(() => read(searchParameters), [read, searchParameters])
  const setState = useCallback(
    (updater: Updater<DashboardState>) => {
      setSearchParameters((parameters) => dashboardSearchParameters(functionalUpdate(updater, read(parameters))), {
        preventScrollReset: true,
        replace: true
      })
    },
    [read, setSearchParameters]
  )
  const resetState = useCallback(
    () => setSearchParameters({}, { preventScrollReset: true, replace: true }),
    [setSearchParameters]
  )

  return [state, setState, resetState] as const
}

export function dashboardFilterValue(values: FilterValue[], inverted = false): DashboardFilterValue {
  return { inverted, values }
}

export function hasDashboardFilterValue(kind: DashboardFilterKind, filter: DashboardFilterValue): boolean {
  return filter.values.length > 0 && (kind === 'values' || String(filter.values[0]).trim() !== '')
}

function defaultDashboardState(columns: DashboardColumn[]): DashboardState {
  return {
    chartColumns: [],
    columnFilters: [],
    columnVisibility: Object.fromEntries(
      columns.map(({ id }) => [id, id === REPOSITORIES || DEFAULT_TABLE_COLUMNS.includes(id)])
    ),
    filterColumns: DEFAULT_FILTER_COLUMNS.filter((id) =>
      columns.some((column) => column.id === id && isFilterableDashboardColumn(column))
    ),
    sorting: []
  }
}

function dashboardStateSchema(columns: DashboardColumn[]) {
  const columnId = z.enum(columns.map(({ id }) => id))
  const filterableColumns = columns.filter(isFilterableDashboardColumn)
  const filterColumnId = z.enum(filterableColumns.map(({ id }) => id))

  return z.object({
    chartColumns: z.array(columnId),
    columnFilters: z.array(z.object({ id: filterColumnId, value: dashboardFilterValueSchema })),
    columnVisibility: z.record(columnId, z.boolean()),
    filterColumns: z.array(filterColumnId),
    sorting: z.array(z.object({ desc: z.boolean(), id: columnId })).check(z.maxLength(1))
  })
}

function readDashboardState(
  parameters: URLSearchParams,
  schema: ReturnType<typeof dashboardStateSchema>,
  defaults: DashboardState
): DashboardState {
  const encoded = parameters.get(STATE_PARAMETER)
  if (encoded == null) return defaults

  const parsed = z.safeParse(schema, dashboardStateCodec.decode(encoded))
  if (!parsed.success || parsed.data.columnVisibility[REPOSITORIES] === false) return defaults

  if (parsed.data.columnFilters.some(({ id }) => !parsed.data.filterColumns.includes(id))) return defaults
  return parsed.data
}

function dashboardSearchParameters(state: DashboardState): URLSearchParams {
  return new URLSearchParams([[STATE_PARAMETER, dashboardStateCodec.encode(state)]])
}
