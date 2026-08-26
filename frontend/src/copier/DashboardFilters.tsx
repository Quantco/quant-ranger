import { TextFilterInput, ValueFilterInput } from './ColumnFilterInputs'
import type { DashboardFilter } from './dashboard-analytics'
import { dashboardFilterValue } from './dashboard-state'
import { dashboardFilter, filterableDashboardColumn } from './dashboard-table'

export function DashboardFilters({ filters }: { filters: DashboardFilter[] }) {
  return filters.map(({ column: tableColumn, options }) => {
    const column = filterableDashboardColumn(tableColumn)
    const filter = dashboardFilter(tableColumn)
    const onInvert = (inverted: boolean) => {
      if (filter != null) tableColumn.setFilterValue({ ...filter, inverted })
    }

    return column.filter.kind === 'values' ? (
      <ValueFilterInput
        column={column}
        filter={filter}
        key={column.id}
        onChange={(values) => tableColumn.setFilterValue(dashboardFilterValue(values, filter?.inverted))}
        onInvert={onInvert}
        options={options}
      />
    ) : (
      <TextFilterInput
        column={column}
        filter={filter}
        key={column.id}
        onChange={(query) => tableColumn.setFilterValue(dashboardFilterValue([query], filter?.inverted))}
        onInvert={onInvert}
        options={options}
      />
    )
  })
}
