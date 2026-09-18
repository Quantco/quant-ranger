import { replaceFilter } from '@/components/data-table/table-state'
import type { UrlState } from '@/lib/useUrlState'
import type { DashboardColumnModel, FilterableDashboardColumn } from './dashboard-columns'
import type { DashboardFilterValue, DashboardState } from './dashboard-state'

type Dashboard = UrlState<DashboardState>

export const useStateFiltering = (
  state: Dashboard['state'],
  setState: Dashboard['setState'],
  filterable: FilterableDashboardColumn[]
) => {
  const filters = state.filters
  const fields = state.filterColumns
  const setFilter = (column: string, filter: DashboardFilterValue | null) => {
    setState((previous) => ({ ...previous, filters: replaceFilter(previous.filters, column, filter) }))
  }

  const setFilterFields = (selected: string[]) => {
    setState((previous) => {
      const filterColumns = filterable.filter((column) => selected.includes(column.id)).map(({ id }) => id)
      const filters = Object.fromEntries(Object.entries(previous.filters).filter(([id]) => filterColumns.includes(id)))
      return {
        ...previous,
        filterColumns,
        filters
      }
    })
  }

  const partialOptions = filterable
    .filter((column) => fields.includes(column.id))
    .map((column) => ({ column, filter: filters[column.id] }))
    .map(({ column, filter }) => ({
      column,
      filter,
      options: null
    }))

  return {
    filters,
    setFilter,
    partialOptions,
    fields: {
      options: filterable.map(({ id }) => id),
      selected: fields,
      setFields: setFilterFields
    }
  }
}

export type StateFiltering = ReturnType<typeof useStateFiltering>

/** Which columns get a pie chart. The charts themselves are derived from the table. */
export const useStateCharts = (
  state: Dashboard['state'],
  setState: Dashboard['setState'],
  columns: readonly DashboardColumnModel[]
) => {
  const selected = state.chartColumns
  const options = columns.map(({ id }) => id)
  const setCharts = (selected: readonly string[]) =>
    setState((previous) => ({
      ...previous,
      chartColumns: columns.flatMap(({ id }) => (selected.includes(id) ? [id] : []))
    }))

  return {
    options,
    selected,
    setCharts
  }
}

export type StateCharts = ReturnType<typeof useStateCharts>
