import { TextFilterInput, ValueFilterInput } from './ColumnFilterInputs'
import type { DashboardFilter } from './dashboard-analytics'
import { dashboardFilterValue, hasDashboardFilterValue, type DashboardFilterValue } from './dashboard-state'

export function DashboardFilters({
  filters,
  onChange
}: {
  filters: DashboardFilter[]
  onChange: (column: string, filter: DashboardFilterValue | null) => void
}) {
  return filters.map(({ column, filter, options }) => {
    const setFilter = (next: DashboardFilterValue) =>
      onChange(column.id, hasDashboardFilterValue(column.filter.kind, next) ? next : null)
    const onInvert = (inverted: boolean) => {
      if (filter != null) setFilter({ ...filter, inverted })
    }

    return column.filter.kind === 'values' ? (
      <ValueFilterInput
        column={column}
        filter={filter}
        key={column.id}
        onChange={(values) => setFilter(dashboardFilterValue(values, filter?.inverted))}
        onInvert={onInvert}
        options={options}
      />
    ) : (
      <TextFilterInput
        column={column}
        filter={filter}
        key={column.id}
        onChange={(query) => setFilter(dashboardFilterValue([query], filter?.inverted))}
        onInvert={onInvert}
        options={options}
      />
    )
  })
}
