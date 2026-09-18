import type { Facet } from './facets'
import { TextFilter, ValueFilter } from './FilterInputs'
import { isActive, type Filter } from './state'

type FilterControlProps = Facet & {
  onChange: (column: string, filter: Filter | null) => void
}

export const FilterControl = ({ column, filter, options, onChange }: FilterControlProps) => {
  // An emptied filter is removed rather than stored blank, so it stops narrowing
  // the table and drops out of the URL.
  const set = (next: Filter) => onChange(column.id, isActive(column.filter.kind, next) ? next : null)
  const inverted = filter?.inverted ?? false

  const shared = {
    column,
    filter,
    onInvert: (next: boolean) => {
      if (filter != null) set({ ...filter, inverted: next })
    },
    options
  }

  return column.filter.kind === 'values' ? (
    <ValueFilter {...shared} onChange={(values) => set({ inverted, values })} />
  ) : (
    <TextFilter {...shared} onChange={(query) => set({ inverted, values: [query] })} />
  )
}
