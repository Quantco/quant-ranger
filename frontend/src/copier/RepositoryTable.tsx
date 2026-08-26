import { DataTable, type DataTableColumn } from '../components/DataTable'
import { cn } from '../lib/utils'
import { displayValue, type DisplayValue } from '../lib/value'
import { repositoryName, VALIDATION, type DashboardColumn, type DashboardRow } from './dashboard'
import { dashboardColumn, type DashboardTable } from './dashboard-table'

function renderValue(value: DisplayValue, row: DashboardRow, column: DashboardColumn) {
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

export function RepositoryTable({ table }: { table: DashboardTable }) {
  const columns: DataTableColumn<DashboardRow>[] = table.getVisibleLeafColumns().map((tableColumn) => {
    const { id } = tableColumn
    const column = dashboardColumn(tableColumn)
    return {
      cellClassName: (value) =>
        typeof value === 'boolean' ? (value ? 'bg-success-subtle' : 'bg-error-subtle') : undefined,
      id,
      label: column.kind === 'answer' ? <code>{id}</code> : id,
      render: (value, row) => renderValue(value, row, column),
      title: id,
      tooltip: (value, row) =>
        id === VALIDATION && row.validationFailure ? row.validationFailure : displayValue(value),
      truncate: true,
      value: (row) => row.values[id]
    }
  })
  return (
    <DataTable columns={columns} emptyMessage="No matching repositories." label="Repository Inventory" table={table} />
  )
}
