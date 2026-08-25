import { TextFilterInput, ValueFilterInput } from './ColumnFilterInputs'
import type { ValueFilter } from './dashboard'
import type { DashboardFilter } from './useCopierDashboard'

export function DashboardFilters({
  filters,
  onTextChange,
  onTextInvert,
  onValueChange,
  onValueInvert
}: {
  filters: DashboardFilter[]
  onTextChange: (column: string, query: string) => void
  onTextInvert: (column: string, inverted: boolean) => void
  onValueChange: (column: string, values: ValueFilter['values']) => void
  onValueInvert: (column: string, inverted: boolean) => void
}) {
  return filters.map((filter) =>
    filter.kind === 'value' ? (
      <ValueFilterInput
        column={filter.column}
        filter={filter.filter}
        key={filter.column}
        onChange={(values) => onValueChange(filter.column, values)}
        onInvert={(inverted) => onValueInvert(filter.column, inverted)}
        options={filter.options}
      />
    ) : (
      <TextFilterInput
        column={filter.column}
        filter={filter.filter}
        key={filter.column}
        onChange={(query) => onTextChange(filter.column, query)}
        onInvert={(inverted) => onTextInvert(filter.column, inverted)}
        options={filter.options}
      />
    )
  )
}
