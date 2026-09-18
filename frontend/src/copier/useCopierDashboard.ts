import { useCallback, useMemo } from 'react'

import { useStateColumnVisibility, useStateSorting } from '@/components/data-table/table-state'
import { useControlledTable } from '@/components/data-table/useControlledTable'
import { useUrlState } from '@/lib/useUrlState'
import { dashboardCharts, facetOptions, requireTableColumn } from './dashboard-analytics'
import { REPOSITORIES, type DashboardSnapshot } from './dashboard'
import { createDashboardColumns, isFilterableDashboardColumn } from './dashboard-columns'
import { defaultDashboardState, parseDashboardState } from './dashboard-state'
import { createDashboardColumnRegistry } from './dashboard-table'
import { useStateCharts, useStateFiltering } from './hooks'

export const useCopierDashboardController = (snapshot: DashboardSnapshot) => {
  const columns = useMemo(() => createDashboardColumns(snapshot), [snapshot])
  const columnRegistry = useMemo(() => createDashboardColumnRegistry(columns), [columns])
  const initialRowSelection = useMemo(
    () => Object.fromEntries(snapshot.rows.map(({ repository }) => [repository, true as const])),
    [snapshot.rows]
  )

  const defaultState = useMemo(() => defaultDashboardState(columns), [columns])
  const parse = useCallback((value: unknown) => parseDashboardState(value, columns), [columns])
  const { resetState, setState, state } = useUrlState({ defaultState, parse })

  const filterable = columns.filter(isFilterableDashboardColumn)
  const charts = useStateCharts(state, setState, columns)
  const filtering = useStateFiltering(state, setState, filterable)
  const sorting = useStateSorting(state, setState)
  const visibility = useStateColumnVisibility(state, setState, {
    columns: columns.map(({ id }) => id),
    pinned: REPOSITORIES
  })

  const table = useControlledTable({
    columnIds: columns.map(({ id }) => id),
    columns: columnRegistry.map(({ definition }) => definition),
    data: snapshot.rows,
    enableRowSelection: true,
    getRowId: (row) => row.repository,
    initialRowSelection,
    onSortingChange: sorting.setSort,
    state: { filters: filtering.filters, sorting: sorting.sort, visibleColumns: visibility.visible }
  })

  const clearAllState = () => {
    table.resetRowSelection()
    resetState()
  }

  const augmentedFiltering = filtering.partialOptions.map(({ column, filter }) => ({
    column,
    filter,
    options: facetOptions(requireTableColumn(table, column.id), column, filter, snapshot.versions)
  }))

  const augmentedCharts = dashboardCharts(filterable, charts.selected, table)

  return {
    clearAllState,
    uses: {
      charts,
      augmentedCharts,
      filtering,
      augmentedFiltering,
      sorting,
      visibility,
      table
    }
  }
}
