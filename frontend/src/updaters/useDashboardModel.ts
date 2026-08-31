import { useMemo } from 'react'

import { createDataTableModel } from '@/components/data-table/DataTable'
import { replaceExplorerFilter } from '@/components/data-table/explorer-state'
import { useExplorerTable } from '@/components/data-table/useExplorerTable'
import { useUpdaterDashboardUrlState } from './dashboard-url-state'
import { hasPullRequest, pullRequestKey } from './pull-request'
import {
  buildUpdaterFilterDefinitions,
  buildUpdaterResultRows,
  updaterResultColumns,
  updaterSearchFilter,
  UPDATER_REPOSITORY_COLUMN,
  UPDATER_RESULT_COLUMN_IDS,
  type UpdaterResultColumnId
} from './result-columns'
import type { UpdaterReportSnapshot } from './updater-report'
import { useLivePullRequests } from './useLivePullRequests'

interface UpdaterSummaryItem {
  error?: boolean
  label: string
  value: number
}

export function useUpdaterDashboardController(report: UpdaterReportSnapshot) {
  const livePullRequests = useLivePullRequests(report)
  const rows = useMemo(
    () => buildUpdaterResultRows(report.results, livePullRequests.pullRequests),
    [livePullRequests.pullRequests, report.results]
  )
  const { dispatch, resetState, state } = useUpdaterDashboardUrlState(report)
  const table = useExplorerTable({
    columnIds: UPDATER_RESULT_COLUMN_IDS,
    columns: updaterResultColumns,
    data: rows,
    dispatch,
    getRowId: ({ result }, index) =>
      `${result.repository}\0${result.target ?? ''}\0${result.pull_request ?? ''}\0${index}`,
    globalFilterColumn: UPDATER_REPOSITORY_COLUMN,
    globalFilterFunction: updaterSearchFilter,
    parseFilter: (value): string[] | undefined =>
      Array.isArray(value) && value.every((item: unknown) => typeof item === 'string') ? value : undefined,
    state
  })

  const statuses = [...new Set(report.results.map(({ status }) => status))].sort()
  const filters = buildUpdaterFilterDefinitions(statuses).map((definition) => ({
    ...definition,
    selected: state.filters[definition.column] ?? []
  }))
  const optionalColumns = UPDATER_RESULT_COLUMN_IDS.filter((column) => column !== UPDATER_REPOSITORY_COLUMN)
  const selectedColumns = optionalColumns.filter((column) => state.visibleColumns.includes(column))
  const updaterFailures = report.results.filter(({ status }) => status === 'failure')
  const failureCount = report.summary.failures + report.summary.scan_failures
  const uniquePullRequests = new Set(report.results.filter(hasPullRequest).map(pullRequestKey)).size
  const summaryItems: UpdaterSummaryItem[] = [
    { label: 'Tasks', value: report.summary.total },
    { label: 'Updated', value: report.summary.updated },
    { label: 'Up to date', value: report.summary.up_to_date },
    { label: 'Skipped', value: report.summary.skipped },
    { error: failureCount > 0, label: 'Failures', value: failureCount },
    { label: 'Pull requests', value: uniquePullRequests },
    ...(livePullRequests.loadedCount > 0 ? [{ label: 'Open PRs', value: livePullRequests.openCount }] : [])
  ]

  const setFilter = (column: UpdaterResultColumnId, selected: string[]) =>
    dispatch({
      filters: replaceExplorerFilter(state.filters, column, selected.length === 0 ? null : selected),
      type: 'filters/replace'
    })
  const setTableColumns = (selected: string[]) =>
    dispatch({
      columns: [UPDATER_REPOSITORY_COLUMN, ...optionalColumns.filter((column) => selected.includes(column))],
      type: 'visible-columns/set'
    })

  return {
    actions: {
      reset: resetState,
      setFilter,
      setSearch: (value: string) => dispatch({ search: value, type: 'search/set' }),
      setTableColumns
    },
    resources: { pullRequests: livePullRequests },
    view: {
      filters,
      resultCount: table.getFilteredRowModel().rows.length,
      search: state.search,
      summaryItems,
      table: createDataTableModel({ emptyMessage: 'No matching results.', label: 'Updater results', table }),
      tableColumns: {
        fields: optionalColumns,
        selected: selectedColumns
      },
      updaterFailures
    }
  }
}
