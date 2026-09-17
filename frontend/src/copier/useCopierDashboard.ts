import { useCallback, useMemo } from 'react'

import { replaceFilter } from '@/components/data-table/table-state'
import { useControlledTable } from '@/components/data-table/useControlledTable'
import { useUrlState } from '@/lib/useUrlState'
import { dashboardCharts, dashboardFilters } from './dashboard-analytics'
import { REPOSITORIES, type DashboardSnapshot } from './dashboard'
import { createDashboardColumns, isFilterableDashboardColumn } from './dashboard-columns'
import { defaultDashboardState, parseDashboardState, type DashboardFilterValue } from './dashboard-state'
import { createDashboardColumnRegistry } from './dashboard-table'

// TODO: this is too complicated
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

  const columnIds = columnRegistry.map(({ column }) => column.id)
  const filterColumns = columnRegistry
    .map(({ column }) => column)
    .filter(isFilterableDashboardColumn)
    .map(({ id }) => id)

  const tableColumns = columnIds.filter((id) => id !== REPOSITORIES)

  const setChartColumns = (selected: string[]) =>
    setState((previous) => ({ ...previous, chartColumns: columnIds.filter((id) => selected.includes(id)) }))
  const setFilter = (column: string, filter: DashboardFilterValue | null) =>
    setState((previous) => ({ ...previous, filters: replaceFilter(previous.filters, column, filter) }))
  const setFilterColumns = (selected: string[]) =>
    setState((previous) => {
      const nextColumns = filterColumns.filter((id) => selected.includes(id))
      return {
        ...previous,
        filterColumns: nextColumns,
        // Filters for a field that is no longer shown would keep filtering invisibly.
        filters: Object.fromEntries(Object.entries(previous.filters).filter(([id]) => nextColumns.includes(id)))
      }
    })
  // The repository column is never hidden, so it is pinned back on every write.
  const setTableColumns = (selected: string[]) =>
    setState((previous) => ({
      ...previous,
      visibleColumns: [REPOSITORIES, ...tableColumns.filter((id) => selected.includes(id))]
    }))

  const table = useControlledTable({
    columnIds,
    columns: columnRegistry.map(({ definition }) => definition),
    data: snapshot.rows,
    enableRowSelection: true,
    getRowId: (row) => row.repository,
    initialRowSelection,
    onSortingChange: (sorting) => setState((previous) => ({ ...previous, sorting })),
    state
  })

  return {
    actions: {
      reset: () => {
        table.resetRowSelection()
        resetState()
      },
      setChartColumns,
      setFilter,
      setFilterColumns,
      setTableColumns
    },
    view: {
      charts: dashboardCharts(table, columnRegistry, state.chartColumns),
      filterFields: {
        options: filterColumns,
        selected: state.filterColumns
      },
      filters: dashboardFilters(table, columnRegistry, state.filterColumns, state.filters, snapshot.versions),
      generatedAt: snapshot.generatedAt,
      pieCharts: {
        options: columnIds,
        selected: state.chartColumns
      },
      repositories: {
        matchingRepositoryCount: table.getFilteredRowModel().rows.length,
        repositoryNames: table.getFilteredSelectedRowModel().rows.map(({ original }) => original.repository),
        table
      },
      repositoryCount: snapshot.rows.length,
      tableColumns: {
        options: tableColumns,
        selected: tableColumns.filter((id) => state.visibleColumns.includes(id))
      }
    }
  }
}
