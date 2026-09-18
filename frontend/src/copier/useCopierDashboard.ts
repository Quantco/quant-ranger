import { useCallback, useMemo } from 'react'

import { useStateColumnVisibility, useStateSorting } from '@/components/data-table/hooks'
import { useControlledTable } from '@/components/data-table/useControlledTable'
import { useUrlState } from '@/lib/useUrlState'
import { buildColumns, isFilterable } from './columns'
import { chartData, facetValues, requireColumn, type Facet } from './facets'
import { useCharts, useFiltering } from './hooks'
import { REPOSITORIES, type Snapshot } from './report'
import { defaultState, parseState } from './state'
import { buildColumnDefinitions } from './table'

export const useCopierDashboard = (snapshot: Snapshot) => {
  const columns = useMemo(() => buildColumns(snapshot), [snapshot])
  const columnIds = columns.map(({ id }) => id)
  const filterable = columns.filter(isFilterable)
  // Every repository starts selected for copying. Selection lives in the table
  // rather than the URL, so a shared link never carries a stale list.
  const initialRowSelection = useMemo(
    () => Object.fromEntries(snapshot.rows.map(({ repository }) => [repository, true as const])),
    [snapshot.rows]
  )

  const parse = useCallback((value: unknown) => parseState(value, columns), [columns])
  const { resetState, setState, state } = useUrlState({
    defaultState: useMemo(() => defaultState(columns), [columns]),
    parse
  })

  const charts = useCharts(state, setState, columns)
  const filtering = useFiltering(state, setState, filterable)
  const sorting = useStateSorting(state, setState)
  const visibility = useStateColumnVisibility(state, setState, { columns: columnIds, pinned: REPOSITORIES })

  const table = useControlledTable({
    columnIds,
    columns: useMemo(() => buildColumnDefinitions(columns), [columns]),
    data: snapshot.rows,
    enableRowSelection: true,
    getRowId: (row) => row.repository,
    initialRowSelection,
    onSortingChange: sorting.setSort,
    state: { filters: filtering.filters, sorting: sorting.sort, visibleColumns: visibility.visible }
  })

  // Both are faceted over the rows the current filters leave in, so they can
  // only be read once the table exists.
  const facets: Facet[] = filtering.active.map(({ column, filter }) => ({
    column,
    filter,
    options: facetValues(requireColumn(table, column.id), column, filter, snapshot.versions)
  }))

  return {
    charts: { ...charts, data: chartData(filterable, charts.selected, table) },
    clearAll: () => {
      table.resetRowSelection()
      resetState()
    },
    facets,
    filtering,
    table,
    visibility
  }
}
