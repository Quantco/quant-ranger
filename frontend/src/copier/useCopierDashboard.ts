import { functionalUpdate, useTable } from '@tanstack/react-table'
import { useMemo } from 'react'

import { dataTableFeatures } from '../components/data-table-model'
import { dashboardCharts, dashboardFilters } from './dashboard-analytics'
import type { DashboardSnapshot } from './dashboard'
import { useDashboardState } from './dashboard-state'
import { createDashboardTableColumns } from './dashboard-table'

export function useCopierDashboard(snapshot: DashboardSnapshot) {
  const columns = useMemo(() => createDashboardTableColumns(snapshot.columns), [snapshot.columns])
  const initialRowSelection = useMemo(
    () => Object.fromEntries(snapshot.rows.map(({ repository }) => [repository, true as const])),
    [snapshot.rows]
  )
  const [state, setState, resetState] = useDashboardState(snapshot.columns)
  const table = useTable({
    columns,
    data: snapshot.rows,
    enableMultiSort: false,
    enableRowSelection: true,
    features: dataTableFeatures,
    getRowId: (row) => row.repository,
    initialState: { rowSelection: initialRowSelection },
    onColumnFiltersChange: (updater) =>
      setState((current) => ({
        ...current,
        columnFilters: functionalUpdate(updater, current.columnFilters)
      })),
    onColumnVisibilityChange: (updater) =>
      setState((current) => ({
        ...current,
        columnVisibility: functionalUpdate(updater, current.columnVisibility)
      })),
    onSortingChange: (updater) =>
      setState((current) => ({
        ...current,
        sorting: functionalUpdate(updater, current.sorting)
      })),
    state: {
      columnFilters: state.columnFilters,
      columnVisibility: state.columnVisibility,
      sorting: state.sorting
    }
  })
  const filterColumns = table.getAllLeafColumns().filter((column) => column.getCanFilter())
  const tableColumns = table.getAllLeafColumns().filter((column) => column.getCanHide())

  const updateFilterColumns = (columnIds: string[]) => {
    setState((current) => ({
      ...current,
      columnFilters: current.columnFilters.filter(({ id }) => columnIds.includes(id)),
      filterColumns: columnIds
    }))
  }

  return {
    charts: dashboardCharts(table, state.chartColumns),
    filterFields: {
      fields: filterColumns.map(({ id }) => id),
      onChange: updateFilterColumns,
      selected: state.filterColumns
    },
    filters: dashboardFilters(table, state.filterColumns, snapshot.versions),
    generatedAt: snapshot.generatedAt,
    onReset: () => {
      table.resetRowSelection()
      resetState()
    },
    pieCharts: {
      fields: table.getAllLeafColumns().map(({ id }) => id),
      onChange: (chartColumns: string[]) => setState((current) => ({ ...current, chartColumns })),
      selected: state.chartColumns
    },
    repositories: {
      matchingRepositoryCount: table.getFilteredRowModel().rows.length,
      repositoryNames: table.getFilteredSelectedRowModel().rows.map(({ original }) => original.repository),
      table
    },
    repositoryCount: snapshot.rows.length,
    tableColumns: {
      fields: tableColumns.map(({ id }) => id),
      onChange: (columnIds: string[]) =>
        table.setColumnVisibility(Object.fromEntries(tableColumns.map(({ id }) => [id, columnIds.includes(id)]))),
      selected: tableColumns.filter((column) => column.getIsVisible()).map(({ id }) => id)
    }
  }
}
