import { sortFn_alphanumeric, type FilterFn } from '@tanstack/react-table'

import type { DataTableColumn } from '@/components/data-table/DataTable'
import type { dataTableFeatures, DataTableInstance } from '@/components/data-table/model'
import { cn } from '@/lib/class-merge'
import { displayValue, type DisplayValue } from '@/lib/value'
import { REPOSITORIES, repositoryName, VALIDATION, type CellValue, type Row } from './report'
import type { Column, FilterKind } from './columns'
import type { Filter } from './state'
import { DataTableOverflowValue } from '@/components/data-table/DataCell'

export type Table = DataTableInstance<Row>
export type TableColumn = ReturnType<Table['getAllLeafColumns']>[number]

type FilterFunction = FilterFn<typeof dataTableFeatures, Row>

const filterFunction = (kind: FilterKind): FilterFunction => {
  const filter: FilterFunction = (row, columnId, value: Filter) => {
    const cell = row.getUniqueValues<CellValue>(columnId)[0]
    const matches =
      kind === 'text'
        ? cell != null &&
          String(cell)
            .toLowerCase()
            .includes(String(value.values[0] ?? ''))
        : value.values.some((candidate) => cell === candidate)
    return value.inverted ? !matches : matches
  }
  // No `autoRemove`: TanStack only consults it inside its own filter setters,
  // and nothing calls those. `FilterControl` drops empty filters instead.
  filter.resolveFilterValue = (value: Filter) => {
    if (kind === 'values') return value
    return {
      ...value,
      values: [
        String(value.values[0] ?? '')
          .trim()
          .toLowerCase()
      ]
    }
  }
  return filter
}

const FILTER_FUNCTIONS: Record<FilterKind, FilterFunction> = {
  text: filterFunction('text'),
  values: filterFunction('values')
}

export const buildColumnDefinitions = (columns: Column[]): DataTableColumn<Row>[] =>
  columns.map((column) => ({
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
  }))

const renderValue = (value: unknown, row: Row, column: Column) => {
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

const sortableValue = (value: CellValue): DisplayValue => (value == null || value === '' ? undefined : value)
