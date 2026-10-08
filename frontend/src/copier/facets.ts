import { isValue, type CellValue, type CountedValue, type ReportColumn, type Value } from './report'
import type { FilterableColumn, OptionOrder } from './columns'
import type { Filter } from './state'
import type { Table, TableColumn } from './table'

/** One filter control's worth of data: the column, what it is set to, and what it could be set to. */
export type Facet = {
  column: FilterableColumn
  filter: Filter | undefined
  options: CountedValue[]
}

export type Chart = {
  column: ReportColumn
  data: CountedValue[]
  domain: Value[]
}

export const chartData = (columns: FilterableColumn[], selected: string[], table: Table): Chart[] => {
  const prefiltered = table.getPreFilteredRowModel().rows
  const filtered = table.getFilteredRowModel().rows

  return columns
    .filter((column) => selected.includes(column.id))
    .map((column) => ({
      column,
      data: distribution(filtered, column.id),
      // The unfiltered spread, so a slice keeps its colour as filters change.
      domain: distribution(prefiltered, column.id).map(({ value }) => value)
    }))
}

export const requireColumn = (table: Table, id: string): TableColumn => {
  const column = table.getColumn(id)
  if (column == null) throw new Error(`The table has no column ${id}.`)
  return column
}

/** Counts per value across the rows the other columns' filters left in. */
export const facetValues = (
  tableColumn: TableColumn,
  column: FilterableColumn,
  filter: Filter | undefined,
  versions: string[]
): CountedValue[] => {
  const counts = new Map<Value, number>()
  // Selected values stay listed at zero so a filter can always be undone.
  for (const value of filter?.values ?? []) counts.set(value, 0)

  for (const [value, count] of tableColumn.getFacetedUniqueValues()) {
    if (!isValue(value)) continue
    if (value === null) continue
    if (column.filter.optionOrder !== 'answer' && value === '') continue
    counts.set(value, count)
  }

  return sortValues(
    [...counts].map(([value, count]) => ({ count, value })),
    column.filter.optionOrder,
    versions
  )
}

const distribution = (rows: ReturnType<Table['getRowModel']>['rows'], column: string): CountedValue[] =>
  Object.entries(Object.groupBy(rows, (row) => String(row.getUniqueValues<CellValue>(column)[0] ?? '')))
    .map(([value, rowsForValue]) => ({ count: rowsForValue?.length ?? 0, value }))
    .toSorted((left, right) => right.count - left.count)

const sortValues = (options: CountedValue[], order: OptionOrder, versions: string[]): CountedValue[] => {
  if (order === 'version') return sortByVersion(options, versions)
  if (order === 'answer') return sortByAnswer(options)
  return options.toSorted((left, right) => right.count - left.count)
}

/** Newest template version first, in the order the report listed them. */
const sortByVersion = (options: CountedValue[], versions: string[]): CountedValue[] => {
  const rank = ({ value }: CountedValue) => {
    const index = versions.indexOf(String(value))
    return index === -1 ? Infinity : index
  }
  return options.toSorted((left, right) => rank(left) - rank(right))
}

/** true, then false, then everything else alphabetically, with blanks last. */
const sortByAnswer = (options: CountedValue[]): CountedValue[] => {
  const booleanOrder: Value[] = [true, false]
  return options.toSorted((left, right) => {
    if (left.value === '') return right.value === '' ? 0 : 1
    if (right.value === '') return -1

    const leftBoolean = booleanOrder.indexOf(left.value)
    const rightBoolean = booleanOrder.indexOf(right.value)
    if (leftBoolean !== -1 || rightBoolean !== -1) {
      return (
        (leftBoolean === -1 ? booleanOrder.length : leftBoolean) -
        (rightBoolean === -1 ? booleanOrder.length : rightBoolean)
      )
    }
    return String(left.value).localeCompare(String(right.value), undefined, { numeric: true })
  })
}
