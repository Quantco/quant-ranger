import { useCallback, useMemo } from 'react'

import { useControlledTable } from '@/components/data-table/useControlledTable'
import { useUrlState } from '@/lib/useUrlState'
import { DEFAULT_UPDATER_DASHBOARD_STATE, parseUpdaterDashboardState } from '@/lib/dashboard-url-state'
import { buildUpdaterResultRows, updaterResultColumns, UPDATER_RESULT_COLUMN_IDS } from './result-columns'
import type { UpdaterReportResult, UpdaterReportSnapshot } from '@/lib/updater-report'
import { usePullRequests } from '@/lib/github/useLivePullRequests'
import { useStateFiltering, useStateSorting, useStateSearch, useStateColumnVisibility } from './hooks'

const resultId = (result: UpdaterReportResult, index: number) => `${result.repository}-${result.target ?? ''}-${result.pull_request ?? ''}-${index}`

export const useUpdaterDashboardController = (report: UpdaterReportSnapshot) => {
  const queried = usePullRequests(report)
  const rows = useMemo(
    () => buildUpdaterResultRows(report.results, queried.pullRequests),
    [queried.pullRequests, report.results]
  )

  const parse = useCallback((value: unknown) => parseUpdaterDashboardState(value, report), [report])
  const { resetState: clearAllState, setState, state } = useUrlState({ defaultState: DEFAULT_UPDATER_DASHBOARD_STATE, parse })
  const filtering = useStateFiltering(state, setState, report)
  const sorting = useStateSorting(state, setState)
  const searching = useStateSearch(state, setState)
  const visibility = useStateColumnVisibility(state, setState)

  const table = useControlledTable({
    columnIds: UPDATER_RESULT_COLUMN_IDS,
    columns: updaterResultColumns,
    data: rows,
    getRowId: ({ result }, index) => resultId(result, index),
    onSortingChange: sorting.setSort,
    search: searching,
    state: {
      filters: filtering.filters,
      sorting: sorting.sort,
      visibleColumns: visibility.visible,
    }
  })

  const filteredResultCount = table.getFilteredRowModel().rows.length

  return {
    uses: {
      filtering,
      sorting,
      searching,
      visibility,
      table,
    },
    clearAllState,
    filteredResultCount,
    pullRequests: queried,
  }
}
