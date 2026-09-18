import { TextFilterInput, ValueFilterInput } from './ColumnFilterInputs'
import type { DashboardFilter as DashboardFilterT } from './dashboard-analytics'
import { hasDashboardFilterValue, type DashboardFilterValue } from './dashboard-state'

type DashboardFilterProps = DashboardFilterT & {
  onChange: (column: string, filter: DashboardFilterValue | null) => void
}

export const DashboardFilter = ({ column, filter, options, onChange }: DashboardFilterProps) => {
  const setFilter = (next: DashboardFilterValue) =>
    onChange(column.id, hasDashboardFilterValue(column.filter.kind, next) ? next : null)
  const onInvert = (inverted: boolean) => {
    if (filter != null) setFilter({ ...filter, inverted })
  }

  const props = {
    column,
    filter,
    key: column.id,
    onInvert: onInvert,
    options: options
  }

  const inverted = filter?.inverted ?? false

  return column.filter.kind === 'values' ? (
    <ValueFilterInput {...props} onChange={(values) => setFilter({ values: values, inverted })} />
  ) : (
    <TextFilterInput {...props} onChange={(query) => setFilter({ values: [query], inverted })} />
  )
}
