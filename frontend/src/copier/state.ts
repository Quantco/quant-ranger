import * as z from 'zod/mini'

import { isUnique, type TableState } from '@/components/data-table/hooks'
import { valueSchema, REPOSITORIES, TEMPLATE, VALIDATION, VERSION } from './report'
import { isFilterable, type Column, type FilterKind } from './columns'

const STATE_VERSION = 1
const DEFAULT_FILTER_COLUMNS = [REPOSITORIES, TEMPLATE, VERSION]
const DEFAULT_TABLE_COLUMNS = [VALIDATION, TEMPLATE, VERSION]

const filterSchema = z.object({
  inverted: z.boolean(),
  values: z.array(valueSchema).check(z.minLength(1))
})

/** What the user has narrowed a column to. */
export type Filter = z.infer<typeof filterSchema>

export type State = {
  chartColumns: string[]
  filterColumns: string[]
  version: typeof STATE_VERSION
} & TableState<string, Filter>

/** A text filter of only whitespace matches everything, so it counts as unset. */
export const isActive = (kind: FilterKind, filter: Filter): boolean =>
  filter.values.length > 0 && (kind === 'values' || String(filter.values[0]).trim() !== '')

export const defaultState = (columns: Column[]): State => ({
  chartColumns: [],
  filterColumns: DEFAULT_FILTER_COLUMNS.filter((id) =>
    columns.some((column) => column.id === id && isFilterable(column))
  ),
  filters: {},
  sorting: [],
  version: STATE_VERSION,
  // The repository column is pinned visible and so never stored.
  visibleColumns: columns.filter(({ id }) => DEFAULT_TABLE_COLUMNS.includes(id)).map(({ id }) => id)
})

const stateSchema = (columns: Column[]) => {
  const columnId = z.enum(columns.map(({ id }) => id))
  const filterColumnId = z.enum(columns.filter(isFilterable).map(({ id }) => id))

  return z.object({
    chartColumns: z.array(columnId),
    filterColumns: z.array(filterColumnId),
    filters: z.record(z.string(), filterSchema),
    // One column at a time: the table is built with `enableMultiSort: false`.
    sorting: z.array(z.object({ desc: z.boolean(), id: columnId })).check(z.maxLength(1)),
    version: z.literal(STATE_VERSION),
    visibleColumns: z.array(columnId)
  })
}

/** Rejects anything the current snapshot cannot render, so a stale or hand-edited URL falls back to the defaults. */
export const parseState = (value: unknown, columns: Column[]): State | null => {
  const parsed = z.safeParse(stateSchema(columns), value)
  if (!parsed.success) return null
  if (!isValidState(parsed.data, columns)) return null
  return parsed.data
}

const isValidState = (state: State, columns: Column[]): boolean => {
  const columnIds = new Set(columns.map(({ id }) => id))
  const filterColumnIds = new Set(columns.filter(isFilterable).map(({ id }) => id))
  return (
    // The pinned column is added back when the table is built, so storing it
    // would show it twice.
    !state.visibleColumns.includes(REPOSITORIES) &&
    isUnique(state.visibleColumns) &&
    isUnique(state.filterColumns) &&
    isUnique(state.chartColumns) &&
    state.visibleColumns.every((id) => columnIds.has(id)) &&
    state.chartColumns.every((id) => columnIds.has(id)) &&
    state.filterColumns.every((id) => filterColumnIds.has(id)) &&
    Object.keys(state.filters).every((id) => filterColumnIds.has(id) && state.filterColumns.includes(id))
  )
}
