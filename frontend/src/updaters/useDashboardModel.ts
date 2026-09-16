import { useCallback, useMemo } from 'react'

import { replaceExplorerFilter, type ExplorerSort } from '@/components/data-table/explorer-state'
import { useExplorerTable } from '@/components/data-table/useExplorerTable'
import { useUrlState } from '@/lib/useUrlState'
import { DEFAULT_UPDATER_DASHBOARD_STATE, parseUpdaterDashboardState } from '@/lib/dashboard-url-state'
import { hasPullRequest, pullRequestKey } from '@/lib/github/pull-request'
import {
  buildUpdaterFilterDefinitions,
  buildUpdaterResultRows,
  updaterResultColumns,
  updaterSearchFilter,
  UPDATER_REPOSITORY_COLUMN,
  UPDATER_RESULT_COLUMN_IDS,
  type UpdaterResultColumnId
} from './result-columns'
import type { UpdaterReportSnapshot } from '@/lib/updater-report'
import { usePullRequests } from '@/lib/github/useLivePullRequests'

type UpdaterSummaryItem = {
  error?: boolean
  label: string
  value: number
}

// TODO: this is too complicated
export const useUpdaterDashboardController = (report: UpdaterReportSnapshot) => {
  const livePullRequests = usePullRequests(report)
  const rows = useMemo(
    () => buildUpdaterResultRows(report.results, livePullRequests.pullRequests),
    [livePullRequests.pullRequests, report.results]
  )
  const parse = useCallback((value: unknown) => parseUpdaterDashboardState(value, report), [report])
  const { resetState, setState, state } = useUrlState({ defaultState: DEFAULT_UPDATER_DASHBOARD_STATE, parse })

  const optionalColumns = UPDATER_RESULT_COLUMN_IDS.filter((column) => column !== UPDATER_REPOSITORY_COLUMN)

  const setFilter = (column: UpdaterResultColumnId, selected: string[]) =>
    setState((previous) => ({
      ...previous,
      filters: replaceExplorerFilter(previous.filters, column, selected.length === 0 ? null : selected)
    }))
  const setFilters = (filters: Partial<Record<UpdaterResultColumnId, string[]>>) =>
    setState((previous) => ({ ...previous, filters }))
  const setSearch = (search: string) => setState((previous) => ({ ...previous, search }))
  const setSort = (sort: ExplorerSort<UpdaterResultColumnId>) => setState((previous) => ({ ...previous, sort }))
  // The repository column is never hidden, so it is pinned back on every write.
  const setTableColumns = (selected: string[]) =>
    setState((previous) => ({
      ...previous,
      visibleColumns: [UPDATER_REPOSITORY_COLUMN, ...optionalColumns.filter((column) => selected.includes(column))]
    }))

  const table = useExplorerTable({
    columnIds: UPDATER_RESULT_COLUMN_IDS,
    columns: updaterResultColumns,
    data: rows,
    getRowId: ({ result }, index) =>
      `${result.repository}\0${result.target ?? ''}\0${result.pull_request ?? ''}\0${index}`,
    globalFilterColumn: UPDATER_REPOSITORY_COLUMN,
    globalFilterFunction: updaterSearchFilter,
    onFiltersChange: setFilters,
    onSearchChange: setSearch,
    onSortChange: setSort,
    onVisibleColumnsChange: setTableColumns,
    parseFilter: (value): string[] | undefined =>
      Array.isArray(value) && value.every((item: unknown) => typeof item === 'string') ? value : undefined,
    state
  })

  const filters = buildUpdaterFilterDefinitions(report.results).map((definition) => ({
    ...definition,
    selected: state.filters[definition.column] ?? []
  }))
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
    ...(livePullRequests.progress.completed > 0 ? [{ label: 'Open PRs', value: livePullRequests.openCount }] : [])
  ]

  return {
    actions: {
      reset: resetState,
      setFilter,
      setSearch,
      setTableColumns
    },
    resources: { pullRequests: livePullRequests },
    view: {
      filters,
      resultCount: table.getFilteredRowModel().rows.length,
      search: state.search,
      summaryItems,
      table,
      tableColumns: {
        fields: optionalColumns,
        selected: selectedColumns
      },
      updaterFailures
    }
  }
}
