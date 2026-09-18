import {
  isFilterValue,
  type CountedValue,
  type DashboardColumn,
  type DashboardValue,
  type FilterValue
} from './dashboard'
import type { DashboardFilterOptionOrder, FilterableDashboardColumn } from './dashboard-columns'
import type { DashboardFilterValue } from './dashboard-state'
import type { DashboardTable, DashboardTableColumn } from './dashboard-table'

export type DashboardFilter = {
  column: FilterableDashboardColumn
  filter: DashboardFilterValue | undefined
  options: CountedValue[]
}

export type DashboardChart = {
  column: DashboardColumn
  data: CountedValue[]
  domain: FilterValue[]
}

export const dashboardFilters = (
  filterable: FilterableDashboardColumn[],
  selectedColumnIds: string[],
  filters: Partial<Record<string, DashboardFilterValue>>,
  table: DashboardTable,
  versions: string[]
): DashboardFilter[] =>
  filterable
    .filter((column) => selectedColumnIds.includes(column.id))
    .map((column) => ({ column, filter: filters[column.id] }))
    .map(({ column, filter }) => ({
      column,
      filter,
      options: facetOptions(requireTableColumn(table, column.id), column, filter, versions)
    }))

export const dashboardCharts = (
  filterable: FilterableDashboardColumn[],
  selectedColumnIds: string[],
  table: DashboardTable
): DashboardChart[] => {
  const prefilteredRows = table.getPreFilteredRowModel().rows
  const filteredRows = table.getFilteredRowModel().rows

  return filterable
    .filter((column) => selectedColumnIds.includes(column.id))
    .map((column) => ({
      column,
      data: columnDistribution(filteredRows, column.id),
      domain: columnDistribution(prefilteredRows, column.id).map(({ value }) => value)
    }))
}

export const requireTableColumn = (table: DashboardTable, id: string): DashboardTableColumn => {
  const column = table.getColumn(id)
  if (column == null) throw new Error(`Dashboard table column ${id} is missing.`)
  return column
}

export const facetOptions = (
  tableColumn: DashboardTableColumn,
  column: FilterableDashboardColumn,
  filter: DashboardFilterValue | undefined,
  versions: string[]
): CountedValue[] => {
  const counts = new Map<FilterValue, number>()
  for (const value of filter?.values ?? []) counts.set(value, 0)

  for (const [value, count] of tableColumn.getFacetedUniqueValues()) {
    if (!isFilterValue(value)) continue
    if (value === null) continue
    if (column.filter.optionOrder !== 'answer' && value === '') continue
    counts.set(value, count)
  }

  return orderFilterOptions(
    [...counts].map(([value, count]) => ({ count, value })),
    column.filter.optionOrder,
    versions
  )
}

const columnDistribution = (
  rows: ReturnType<DashboardTable['getRowModel']>['rows'],
  column: string
): CountedValue[] => {
  const byKeys = Object.groupBy(rows, (row) => String(row.getUniqueValues<DashboardValue>(column)[0] ?? ''))
  const sortedCounts = Object.entries(byKeys)
    .map(([key, values]) => ({ value: key, count: values ? values.length : 0 }))
    .toSorted((left, right) => right.count - left.count)

  return sortedCounts
}

const orderFilterOptions = (
  options: CountedValue[],
  order: DashboardFilterOptionOrder,
  versions: string[]
): CountedValue[] => {
  if (order === 'version') return versionDistribution(options, versions)
  if (order === 'answer') return answerDistribution(options)
  return options.toSorted((left, right) => right.count - left.count)
}

const versionDistribution = (data: CountedValue[], versions: string[]): CountedValue[] => {
  const rank = ({ value }: CountedValue) => {
    const index = versions.indexOf(String(value))
    return index === -1 ? Infinity : index
  }
  return data.toSorted((left, right) => rank(left) - rank(right))
}

const answerDistribution = (data: CountedValue[]): CountedValue[] => {
  const booleanOrder: readonly FilterValue[] = [true, false]
  return data.toSorted((left, right) => {
    if (left.value === '') return right.value === '' ? 0 : 1
    if (right.value === '') return -1

    const leftBooleanOrder = booleanOrder.indexOf(left.value)
    const rightBooleanOrder = booleanOrder.indexOf(right.value)
    if (leftBooleanOrder !== -1 || rightBooleanOrder !== -1) {
      return (
        (leftBooleanOrder === -1 ? booleanOrder.length : leftBooleanOrder) -
        (rightBooleanOrder === -1 ? booleanOrder.length : rightBooleanOrder)
      )
    }
    return String(left.value).localeCompare(String(right.value), undefined, { numeric: true })
  })
}
