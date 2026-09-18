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

import { dataTableFeatures, type DataTableColumnDefinition, type DataTableInstance } from './model'
import type { TableState } from './hooks'

type Search<Row extends RowData, ColumnId extends string> = {
  /** Anchors the predicate to one column so it runs once per row rather than once per cell. */
  column: ColumnId
  filterFunction: FilterFn<typeof dataTableFeatures, Row>
  query: string
}

type Options<Row extends RowData, ColumnId extends string, Filter> = {
  columnIds: ColumnId[]
  columns: DataTableColumnDefinition<Row>[]
  data: Row[]
  enableRowSelection?: boolean
  getRowId: (row: Row, index: number) => string
  initialRowSelection?: RowSelectionState
  onSortingChange: (sorting: SortingState) => void
  search?: Search<Row, ColumnId>
  state: TableState<ColumnId, Filter>
}

/**
 * A table whose filters, sorting and visible columns live outside it.
 *
 * Filters, search and visibility flow one way in: the dashboard owns them and
 * the sidebar edits them, so the table only ever reads them. Sorting is the one
 * slice the table changes itself, from the headers it renders, and so the one
 * with a handler back out.
 *
 * Adding a control inside the table that writes one of the one-way slices — a
 * filter menu on a header, say — means adding its `onChange` handler here too.
 * TanStack installs a default handler that writes to state we never read, so a
 * missing one looks like a control that silently does nothing.
 */
export const useControlledTable = <Row extends RowData, ColumnId extends string, Filter>({
  columnIds,
  columns,
  data,
  enableRowSelection = false,
  getRowId,
  initialRowSelection,
  onSortingChange,
  search,
  state
}: Options<Row, ColumnId, Filter>): DataTableInstance<Row> => {
  const columnFilters: ColumnFiltersState = columnIds.flatMap((id) => {
    const value = state.filters[id]
    return value === undefined ? [] : [{ id, value }]
  })
  // A column missing from `visibleColumns` is hidden, so every column needs an entry
  const columnVisibility: ColumnVisibilityState = Object.fromEntries(
    columnIds.map((id) => [id, state.visibleColumns.includes(id)])
  )

  return useTable({
    columns,
    data,
    enableMultiSort: false,
    enableRowSelection,
    features: dataTableFeatures,
    getRowId,
    ...(initialRowSelection == null ? {} : { initialState: { rowSelection: initialRowSelection } }),
    ...(search == null
      ? {}
      : { getColumnCanGlobalFilter: (column) => column.id === search.column, globalFilterFn: search.filterFunction }),
    onSortingChange: (updater) => onSortingChange(functionalUpdate(updater, state.sorting)),
    state: {
      columnFilters,
      columnVisibility,
      globalFilter: search?.query ?? '',
      sorting: state.sorting
    }
  })
}
