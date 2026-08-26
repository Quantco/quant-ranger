import type {
  CountedValue,
  DashboardColumn,
  DashboardFilterOptionOrder,
  DashboardValue,
  FilterableDashboardColumn,
  FilterValue
} from './dashboard'
import type { DashboardFilterValue } from './dashboard-state'
import {
  dashboardColumn,
  dashboardFilter,
  filterableDashboardColumn,
  selectDashboardTableColumns,
  type DashboardTable,
  type DashboardTableColumn
} from './dashboard-table'

export interface DashboardFilter {
  column: DashboardTableColumn
  options: CountedValue[]
}

export interface DashboardChart {
  column: DashboardColumn
  data: CountedValue[]
  domain: FilterValue[]
}

export function dashboardFilters(table: DashboardTable, columnIds: string[], versions: string[]): DashboardFilter[] {
  return selectDashboardTableColumns(table, columnIds).map((column) => {
    const definition = filterableDashboardColumn(column)
    const filter = dashboardFilter(column)
    return { column, options: facetOptions(column, definition, filter, versions) }
  })
}

export function dashboardCharts(table: DashboardTable, columnIds: string[]): DashboardChart[] {
  const filteredRows = table.getFilteredRowModel().rows
  return selectDashboardTableColumns(table, columnIds).map((column) => {
    const { id } = column
    return {
      column: dashboardColumn(column),
      data: columnDistribution(filteredRows, id),
      domain: columnDistribution(table.getPreFilteredRowModel().rows, id).map(({ value }) => value)
    }
  })
}

function facetOptions(
  tableColumn: DashboardTableColumn,
  column: FilterableDashboardColumn,
  filter: DashboardFilterValue | undefined,
  versions: string[]
): CountedValue[] {
  const counts = new Map<FilterValue, number>()
  for (const value of filter?.values ?? []) counts.set(value, 0)

  for (const [value, count] of tableColumn.getFacetedUniqueValues()) {
    if (value == null || (column.filter.optionOrder !== 'answer' && value === '')) continue
    counts.set(value as FilterValue, count)
  }

  return orderFilterOptions(
    [...counts].map(([value, count]) => ({ count, value })),
    column.filter.optionOrder,
    versions
  )
}

function columnDistribution(rows: ReturnType<DashboardTable['getRowModel']>['rows'], column: string): CountedValue[] {
  const counts = new Map<FilterValue, number>()
  for (const row of rows) {
    const value = (row.getUniqueValues<DashboardValue>(column)[0] ?? '') as FilterValue
    counts.set(value, (counts.get(value) ?? 0) + 1)
  }
  return [...counts].map(([value, count]) => ({ count, value })).sort((left, right) => right.count - left.count)
}

function orderFilterOptions(
  options: CountedValue[],
  order: DashboardFilterOptionOrder,
  versions: string[]
): CountedValue[] {
  if (order === 'version') return versionDistribution(options, versions)
  if (order === 'answer') return answerDistribution(options)
  return options.toSorted((left, right) => right.count - left.count)
}

function versionDistribution(data: CountedValue[], versions: string[]): CountedValue[] {
  const rank = ({ value }: CountedValue) => {
    const index = versions.indexOf(String(value))
    return index === -1 ? Infinity : index
  }
  return data.toSorted((left, right) => rank(left) - rank(right))
}

function answerDistribution(data: CountedValue[]): CountedValue[] {
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
