import { replaceFilter } from '@/components/data-table/hooks'
import type { UrlState } from '@/lib/useUrlState'
import type { UpdaterDashboardState } from '@/lib/dashboard-url-state'
import {
  buildUpdaterFilterDefinitions,
  updaterSearchFilter,
  UPDATER_REPOSITORY_COLUMN,
  type UpdaterResultColumnId
} from './result-columns'
import type { UpdaterReportSnapshot } from '@/lib/updater-report'

type Dashboard = UrlState<UpdaterDashboardState>

export const useStateSearch = (state: Dashboard['state'], setState: Dashboard['setState']) => {
  const setQuery = (search: string) => setState((previous) => ({ ...previous, search }))

  return {
    // Anchored to one column so the predicate runs once per row rather than once per cell; it reads the whole row regardless.
    column: UPDATER_REPOSITORY_COLUMN,
    filterFunction: updaterSearchFilter,
    query: state.search,
    setQuery
  }
}

export type StateSearch = ReturnType<typeof useStateSearch>

export const useStateFiltering = (
  state: Dashboard['state'],
  setState: Dashboard['setState'],
  report: UpdaterReportSnapshot
) => {
  const filters = state.filters
  const setFilter = (column: UpdaterResultColumnId, selected: string[]) =>
    setState((previous) => ({
      ...previous,
      filters: replaceFilter(previous.filters, column, selected.length === 0 ? null : selected)
    }))

  const options = buildUpdaterFilterDefinitions(report.results)

  return {
    options,
    filters,
    setFilter
  }
}

export type StateFiltering = ReturnType<typeof useStateFiltering>
