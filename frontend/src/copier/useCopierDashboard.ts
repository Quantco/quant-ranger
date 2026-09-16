import { useCallback, useMemo } from 'react'

import { replaceExplorerFilter, type ExplorerSort } from '@/components/data-table/explorer-state'
import { useExplorerTable } from '@/components/data-table/useExplorerTable'
import { useUrlState } from '@/lib/useUrlState'
import { dashboardCharts, dashboardFilters } from './dashboard-analytics'
import { REPOSITORIES, type DashboardSnapshot } from './dashboard'
import { createDashboardColumns, isFilterableDashboardColumn } from './dashboard-columns'
import {
  defaultDashboardState,
  parseDashboardFilterValue,
  parseDashboardState,
  type DashboardFilterValue
} from './dashboard-state'
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
    setState((previous) => ({ ...previous, filters: replaceExplorerFilter(previous.filters, column, filter) }))
  const setFilters = (filters: Partial<Record<string, DashboardFilterValue>>) =>
    setState((previous) => ({ ...previous, filters }))
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
  const setSearch = (search: string) => setState((previous) => ({ ...previous, search }))
  const setSort = (sort: ExplorerSort<string>) => setState((previous) => ({ ...previous, sort }))
  // The repository column is never hidden, so it is pinned back on every write.
  const setTableColumns = (selected: string[]) =>
    setState((previous) => ({
      ...previous,
      visibleColumns: [REPOSITORIES, ...tableColumns.filter((id) => selected.includes(id))]
    }))

  const table = useExplorerTable({
    columnIds,
    columns: columnRegistry.map(({ definition }) => definition),
    data: snapshot.rows,
    enableRowSelection: true,
    getRowId: (row) => row.repository,
    initialRowSelection,
    onFiltersChange: setFilters,
    onSearchChange: setSearch,
    onSortChange: setSort,
    onVisibleColumnsChange: setTableColumns,
    parseFilter: parseDashboardFilterValue,
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
        table
      },
      repositoryCount: snapshot.rows.length,
      tableColumns: {
        fields: tableColumns,
        selected: tableColumns.filter((id) => state.visibleColumns.includes(id))
      }
    }
  }
}
