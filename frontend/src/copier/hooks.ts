import { replaceFilter } from '@/components/data-table/hooks'
import type { UrlState } from '@/lib/useUrlState'
import type { Column, FilterableColumn } from './columns'
import type { Filter, State } from './state'

type Dashboard = UrlState<State>

export const useFiltering = (
  state: Dashboard['state'],
  setState: Dashboard['setState'],
  filterable: FilterableColumn[]
) => {
  const fields = state.filterColumns

  const setFilter = (column: string, filter: Filter | null) =>
    setState((previous) => ({ ...previous, filters: replaceFilter(previous.filters, column, filter) }))

  const setFields = (selected: string[]) =>
    setState((previous) => {
      const filterColumns = filterable.filter(({ id }) => selected.includes(id)).map(({ id }) => id)
      return {
        ...previous,
        filterColumns,
        // A filter left behind by a hidden field would keep narrowing the table
        // with no visible control to undo it.
        filters: Object.fromEntries(Object.entries(previous.filters).filter(([id]) => filterColumns.includes(id)))
      }
    })

  return {
    /** The shown filters and their current values. Their options come from the table. */
    active: filterable
      .filter(({ id }) => fields.includes(id))
      .map((column) => ({ column, filter: state.filters[column.id] })),
    fields: { options: filterable.map(({ id }) => id), selected: fields, setFields },
    filters: state.filters,
    setFilter
  }
}

export type Filtering = ReturnType<typeof useFiltering>

/** Which columns get a pie chart. The chart data itself is derived from the table. */
export const useCharts = (state: Dashboard['state'], setState: Dashboard['setState'], columns: Column[]) => ({
  options: columns.map(({ id }) => id),
  selected: state.chartColumns,
  setCharts: (selected: string[]) =>
    setState((previous) => ({
      ...previous,
      chartColumns: columns.flatMap(({ id }) => (selected.includes(id) ? [id] : []))
    }))
})

export type Charts = ReturnType<typeof useCharts>
