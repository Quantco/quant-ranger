import { useMemo } from 'react'

import { createDataTableModel } from '../components/DataTable'
import { replaceExplorerFilter } from '../components/explorer-state'
import { useExplorerTable } from '../components/useExplorerTable'
import { dashboardCharts, dashboardFilters } from './dashboard-analytics'
import { REPOSITORIES, type DashboardSnapshot } from './dashboard'
import { createDashboardColumns, isFilterableDashboardColumn } from './dashboard-columns'
import { parseDashboardFilterValue, useDashboardState, type DashboardFilterValue } from './dashboard-state'
import { createDashboardColumnRegistry } from './dashboard-table'

export function useCopierDashboardController(snapshot: DashboardSnapshot) {
  const columns = useMemo(() => createDashboardColumns(snapshot), [snapshot])
  const columnRegistry = useMemo(() => createDashboardColumnRegistry(columns), [columns])
  const initialRowSelection = useMemo(
    () => Object.fromEntries(snapshot.rows.map(({ repository }) => [repository, true as const])),
    [snapshot.rows]
  )
  const { dispatch, resetState, state } = useDashboardState(columns)
  const columnIds = columnRegistry.map(({ column }) => column.id)
  const filterColumns = columnRegistry
    .filter(({ column }) => isFilterableDashboardColumn(column))
    .map(({ column }) => column.id)
  const tableColumns = columnIds.filter((id) => id !== REPOSITORIES)
  const table = useExplorerTable({
    columnIds,
    columns: columnRegistry.map(({ definition }) => definition),
    data: snapshot.rows,
    dispatch,
    enableRowSelection: true,
    getRowId: (row) => row.repository,
    initialRowSelection,
    parseFilter: parseDashboardFilterValue,
    state
  })

  const reset = () => {
    table.resetRowSelection()
    resetState()
  }
  const setChartColumns = (selected: string[]) =>
    dispatch({
      columns: columnIds.filter((id) => selected.includes(id)),
      type: 'chart-columns/set'
    })
  const setFilter = (column: string, filter: DashboardFilterValue | null) =>
    dispatch({
      filters: replaceExplorerFilter(state.filters, column, filter),
      type: 'filters/replace'
    })
  const setFilterColumns = (selected: string[]) =>
    dispatch({
      columns: filterColumns.filter((id) => selected.includes(id)),
      type: 'filter-columns/set'
    })
  const setTableColumns = (selected: string[]) =>
    dispatch({
      columns: [REPOSITORIES, ...tableColumns.filter((id) => selected.includes(id))],
      type: 'visible-columns/set'
    })

  return {
    actions: {
      reset,
      setChartColumns,
      setFilter,
      setFilterColumns,
      setTableColumns
    },
    view: {
      charts: dashboardCharts(table, columnRegistry, state.chartColumns),
      filterFields: {
        fields: filterColumns,
        selected: state.filterColumns
      },
      filters: dashboardFilters(table, columnRegistry, state.filterColumns, state.filters, snapshot.versions),
      generatedAt: snapshot.generatedAt,
      pieCharts: {
        fields: columnIds,
        selected: state.chartColumns
      },
      repositories: {
        matchingRepositoryCount: table.getFilteredRowModel().rows.length,
        repositoryNames: table.getFilteredSelectedRowModel().rows.map(({ original }) => original.repository),
        table: createDataTableModel({
          emptyMessage: 'No matching repositories.',
          label: 'Repository Inventory',
          table
        })
      },
      repositoryCount: snapshot.rows.length,
      tableColumns: {
        fields: tableColumns,
        selected: tableColumns.filter((id) => state.visibleColumns.includes(id))
      }
    }
  }
}
