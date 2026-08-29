import {
  functionalUpdate,
  useTable,
  type ColumnFiltersState,
  type ColumnVisibilityState,
  type FilterFn,
  type RowData,
  type RowSelectionState,
  type SortingState
} from '@tanstack/react-table'

import { dataTableFeatures, type DataTableColumnDefinition, type DataTableInstance } from './data-table-model'
import type { ExplorerAction, ExplorerState } from './explorer-state'

interface UseExplorerTableOptions<Row extends RowData, ColumnId extends string, Filter> {
  columns: readonly DataTableColumnDefinition<Row>[]
  columnIds: readonly ColumnId[]
  data: Row[]
  dispatch: (action: ExplorerAction<ColumnId, Filter>) => void
  enableRowSelection?: boolean
  getRowId: (row: Row, index: number) => string
  globalFilterColumn?: ColumnId
  globalFilterFunction?: FilterFn<typeof dataTableFeatures, Row>
  initialRowSelection?: RowSelectionState
  parseFilter: (value: unknown) => Filter | undefined
  state: ExplorerState<ColumnId, Filter>
}

export function useExplorerTable<Row extends RowData, ColumnId extends string, Filter>({
  columns,
  columnIds,
  data,
  dispatch,
  enableRowSelection = false,
  getRowId,
  globalFilterColumn,
  globalFilterFunction,
  initialRowSelection,
  parseFilter,
  state
}: UseExplorerTableOptions<Row, ColumnId, Filter>): DataTableInstance<Row> {
  const columnFilters: ColumnFiltersState = columnIds.flatMap((id) => {
    const value = state.filters[id]
    return value === undefined ? [] : [{ id, value }]
  })
  const columnVisibility: ColumnVisibilityState = Object.fromEntries(
    columnIds.map((id) => [id, state.visibleColumns.includes(id)])
  )
  const sorting: SortingState =
    state.sort == null ? [] : [{ desc: state.sort.direction === 'desc', id: state.sort.column }]

  return useTable({
    columns,
    data,
    enableMultiSort: false,
    enableRowSelection,
    features: dataTableFeatures,
    ...(globalFilterColumn == null ? {} : { getColumnCanGlobalFilter: (column) => column.id === globalFilterColumn }),
    getRowId,
    ...(globalFilterFunction == null ? {} : { globalFilterFn: globalFilterFunction }),
    ...(initialRowSelection == null ? {} : { initialState: { rowSelection: initialRowSelection } }),
    onColumnFiltersChange: (updater) => {
      const next = functionalUpdate(updater, columnFilters)
      const filters: Partial<Record<ColumnId, Filter>> = {}
      for (const item of next) {
        const column = columnIds.find((id) => id === item.id)
        const value: unknown = item.value
        const filter = parseFilter(value)
        if (column != null && filter !== undefined) filters[column] = filter
      }
      dispatch({
        filters,
        type: 'filters/replace'
      })
    },
    onColumnVisibilityChange: (updater) => {
      const next = functionalUpdate(updater, columnVisibility)
      dispatch({
        columns: columnIds.filter((id) => next[id] !== false),
        type: 'visible-columns/set'
      })
    },
    onGlobalFilterChange: (updater) => {
      const next: unknown = functionalUpdate(updater, state.search)
      dispatch({ search: typeof next === 'string' ? next : '', type: 'search/set' })
    },
    onSortingChange: (updater) => {
      const [next] = functionalUpdate(updater, sorting)
      const column = next == null ? undefined : columnIds.find((id) => id === next.id)
      dispatch({
        sort: next == null || column == null ? null : { column, direction: next.desc ? 'desc' : 'asc' },
        type: 'sort/set'
      })
    },
    state: {
      columnFilters,
      columnVisibility,
      globalFilter: state.search,
      sorting
    }
  })
}
