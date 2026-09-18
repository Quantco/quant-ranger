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
import type { ExplorerSort, ExplorerState } from './explorer-state'

type UseExplorerTableOptions<Row extends RowData, ColumnId extends string, Filter> = {
  columns: readonly DataTableColumnDefinition<Row>[]
  columnIds: readonly ColumnId[]
  data: Row[]
  enableRowSelection?: boolean
  getRowId: (row: Row, index: number) => string
  globalFilterColumn?: ColumnId
  globalFilterFunction?: FilterFn<typeof dataTableFeatures, Row>
  initialRowSelection?: RowSelectionState
  // The same handlers back the sidebar controls, so sorting or hiding a column
  // from its header goes through exactly one code path.
  onFiltersChange: (filters: Partial<Record<ColumnId, Filter>>) => void
  onSearchChange: (search: string) => void
  onSortChange: (sort: ExplorerSort<ColumnId>) => void
  onVisibleColumnsChange: (columns: ColumnId[]) => void
  parseFilter: (value: unknown) => Filter | undefined
  state: ExplorerState<ColumnId, Filter>
}

export const useExplorerTable = <Row extends RowData, ColumnId extends string, Filter>({
  columns,
  columnIds,
  data,
  enableRowSelection = false,
  getRowId,
  globalFilterColumn,
  globalFilterFunction,
  initialRowSelection,
  onFiltersChange,
  onSearchChange,
  onSortChange,
  onVisibleColumnsChange,
  parseFilter,
  state
}: UseExplorerTableOptions<Row, ColumnId, Filter>): DataTableInstance<Row> => {
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
      const filters: Partial<Record<ColumnId, Filter>> = {}
      for (const item of functionalUpdate(updater, columnFilters)) {
        const column = columnIds.find((id) => id === item.id)
        const value: unknown = item.value
        const filter = parseFilter(value)
        if (column != null && filter !== undefined) filters[column] = filter
      }
      onFiltersChange(filters)
    },
    onColumnVisibilityChange: (updater) => {
      const next = functionalUpdate(updater, columnVisibility)
      onVisibleColumnsChange(columnIds.filter((id) => next[id] !== false))
    },
    onGlobalFilterChange: (updater) => {
      const next: unknown = functionalUpdate(updater, state.search)
      onSearchChange(typeof next === 'string' ? next : '')
    },
    onSortingChange: (updater) => {
      const [next] = functionalUpdate(updater, sorting)
      const column = next == null ? undefined : columnIds.find((id) => id === next.id)
      onSortChange(next == null || column == null ? null : { column, direction: next.desc ? 'desc' : 'asc' })
    },
    state: {
      columnFilters,
      columnVisibility,
      globalFilter: state.search,
      sorting
    }
  })
}
