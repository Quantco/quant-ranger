import { replaceFilter } from '@/components/data-table/table-state'
import type { UrlState } from '@/lib/useUrlState'
import type { UpdaterDashboardState } from '@/lib/dashboard-url-state'
import {
  buildUpdaterFilterDefinitions,
  updaterSearchFilter,
  UPDATER_REPOSITORY_COLUMN,
  UPDATER_RESULT_COLUMN_IDS,
  type UpdaterResultColumnId
} from './result-columns'
import type { UpdaterReportSnapshot } from '@/lib/updater-report'
import type { SortingState } from '@tanstack/react-table'

type Blub = UrlState<UpdaterDashboardState>


const optionalColumns = UPDATER_RESULT_COLUMN_IDS.filter((column) => column !== UPDATER_REPOSITORY_COLUMN)

export const useStateColumnVisibility = (state: Blub['state'], setState: Blub['setState']) => {
  const selected = state.visibleColumns

  const setVisibleColumns = (selected: string[]) =>
    setState((previous) => ({
      ...previous,
      visibleColumns: optionalColumns.filter((column) => selected.includes(column))
    }))
  
  return {
    options: optionalColumns,
    // The repository column is never hidden, so it is always added here
    // This in turn allows not saving it with the rest of the columns
    selected: selected,
    visible: [UPDATER_REPOSITORY_COLUMN, ...selected],
    setVisibleColumns
  }
}

export type StateColumnVisibility = ReturnType<typeof useStateColumnVisibility>

export const useStateSearch = (state: Blub['state'], setState: Blub['setState']) => {
  const setQuery = (search: string) => setState((previous) => ({ ...previous, search }))
  
  return {
    column: UPDATER_REPOSITORY_COLUMN,
    filterFunction: updaterSearchFilter,
    query: state.search,
    setQuery
  }
}

export type StateSearch = ReturnType<typeof useStateSearch>

export const useStateSorting = (state: Blub['state'], setState: Blub['setState']) => {
  const sort = state.sorting
  const setSort = (sorting: SortingState) => setState((previous) => ({ ...previous, sorting }))

  return {
    sort,
    setSort
  }
}

export type StateSorting = ReturnType<typeof useStateSorting>

export const useStateFiltering = (state: Blub['state'], setState: Blub['setState'], report: UpdaterReportSnapshot) => {
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