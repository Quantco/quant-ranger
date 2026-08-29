import { sortFn_alphanumeric, type FilterFn } from '@tanstack/react-table'

import { DataTableOverflowValue, type DataTableColumn } from '../components/data-table/DataTable'
import type { dataTableFeatures, DataTableInstance } from '../components/data-table/data-table-model'
import { cn } from '../lib/utils'
import { displayValue, type DisplayValue } from '../lib/value'
import { REPOSITORIES, repositoryName, VALIDATION, type DashboardRow, type DashboardValue } from './dashboard'
import type { DashboardColumnModel, DashboardFilterKind } from './dashboard-columns'
import { hasDashboardFilterValue, type DashboardFilterValue } from './dashboard-state'

export type DashboardTable = DataTableInstance<DashboardRow>
export type DashboardTableColumn = ReturnType<DashboardTable['getAllLeafColumns']>[number]
export interface DashboardColumnDescriptor {
  column: DashboardColumnModel
  definition: DataTableColumn<DashboardRow>
}
export type DashboardColumnRegistry = DashboardColumnDescriptor[]

type DashboardFilterFunction = FilterFn<typeof dataTableFeatures, DashboardRow>

const FILTER_FUNCTIONS: Record<DashboardFilterKind, DashboardFilterFunction> = {
  text: dashboardFilterFunction('text'),
  values: dashboardFilterFunction('values')
}

export function createDashboardColumnRegistry(columns: DashboardColumnModel[]): DashboardColumnRegistry {
  return columns.map((column) => ({
    column,
    definition: {
      accessorFn: (row) => sortableValue(row.values[column.id]),
      cell: ({ getValue, row }) => {
        const value = getValue()
        const content = renderValue(value, row.original, column)
        return column.id === VALIDATION ? (
          <DataTableOverflowValue text={row.original.validationFailure || displayValue(value)}>
            {content}
          </DataTableOverflowValue>
        ) : (
          content
        )
      },
      enableColumnFilter: column.filter != null,
      enableHiding: column.id !== REPOSITORIES,
      ...(column.filter == null ? {} : { filterFn: FILTER_FUNCTIONS[column.filter.kind] }),
      getUniqueValues: (row) => [row.values[column.id]],
      header: column.kind === 'answer' ? () => <code>{column.id}</code> : column.id,
      id: column.id,
      meta: {
        highlightBoolean: true,
        title: column.id,
        truncate: column.id !== VALIDATION
      },
      sortFn: sortFn_alphanumeric,
      sortUndefined: 'last'
    }
  }))
}

function renderValue(value: unknown, row: DashboardRow, column: DashboardColumnModel) {
  if (column.kind === 'repository' && row.url) {
    return (
      <a href={row.url} rel="noreferrer" target="_blank">
        {repositoryName(displayValue(value))}
      </a>
    )
  }
  if (typeof value === 'boolean') {
    return <span className={cn('font-semibold', value ? 'text-success' : 'text-error')}>{String(value)}</span>
  }
  return displayValue(value)
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
