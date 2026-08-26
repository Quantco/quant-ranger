import { sortFn_alphanumeric, type FilterFn } from '@tanstack/react-table'

import type { dataTableFeatures, DataTableColumnDefinition, DataTableInstance } from '../components/data-table-model'
import type { DisplayValue } from '../lib/value'
import {
  REPOSITORIES,
  type DashboardColumn,
  type DashboardFilterKind,
  type DashboardRow,
  type DashboardValue,
  type FilterableDashboardColumn
} from './dashboard'
import { hasDashboardFilterValue, type DashboardFilterValue } from './dashboard-state'

export type DashboardTable = DataTableInstance<DashboardRow>
export type DashboardTableColumn = ReturnType<DashboardTable['getAllLeafColumns']>[number]

export type DashboardColumnDefinition = DataTableColumnDefinition<DashboardRow> & {
  id: string
  meta: { column: DashboardColumn }
}

type DashboardFilterFunction = FilterFn<typeof dataTableFeatures, DashboardRow>

const FILTER_FUNCTIONS: Record<DashboardFilterKind, DashboardFilterFunction> = {
  text: dashboardFilterFunction('text'),
  values: dashboardFilterFunction('values')
}

export function createDashboardTableColumns(columns: DashboardColumn[]): DashboardColumnDefinition[] {
  return columns.map((column) => ({
    accessorFn: (row) => sortableValue(row.values[column.id]),
    enableColumnFilter: column.filter != null,
    enableHiding: column.id !== REPOSITORIES,
    filterFn: column.filter == null ? undefined : FILTER_FUNCTIONS[column.filter.kind],
    getUniqueValues: (row) => [row.values[column.id]],
    id: column.id,
    meta: { column },
    sortFn: sortFn_alphanumeric,
    sortUndefined: 'last'
  }))
}

export function dashboardColumn(column: DashboardTableColumn): DashboardColumn {
  return (column.columnDef as DashboardColumnDefinition).meta.column
}

export function dashboardFilter(column: DashboardTableColumn): DashboardFilterValue | undefined {
  return column.getFilterValue() as DashboardFilterValue | undefined
}

export function filterableDashboardColumn(column: DashboardTableColumn): FilterableDashboardColumn {
  return dashboardColumn(column) as FilterableDashboardColumn
}

export function selectDashboardTableColumns(table: DashboardTable, columnIds: string[]): DashboardTableColumn[] {
  return table.getAllLeafColumns().filter(({ id }) => columnIds.includes(id))
}

function dashboardFilterFunction(kind: DashboardFilterKind): DashboardFilterFunction {
  const filter: DashboardFilterFunction = (row, columnId, filterValue: DashboardFilterValue) => {
    const dataValue = row.getUniqueValues<DashboardValue>(columnId)[0]
    const matches =
      kind === 'text'
        ? dataValue != null &&
          String(dataValue)
            .toLowerCase()
            .includes(String(filterValue.values[0] ?? ''))
        : filterValue.values.some((value) => dataValue === value)
    return filterValue.inverted ? !matches : matches
  }
  filter.autoRemove = (filterValue: DashboardFilterValue) => !hasDashboardFilterValue(kind, filterValue)
  filter.resolveFilterValue = (filterValue: DashboardFilterValue) => {
    if (kind === 'values') return filterValue
    return {
      ...filterValue,
      values: [
        String(filterValue.values[0] ?? '')
          .trim()
          .toLowerCase()
      ]
    }
  }
  return filter
}

function sortableValue(value: DashboardValue): DisplayValue {
  return value == null || value === '' ? undefined : value
}
