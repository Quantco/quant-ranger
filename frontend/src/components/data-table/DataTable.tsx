import type { RowData } from '@tanstack/react-table'
import type { DataTableColumnDefinition, DataTableInstance } from './model'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/Table'
import { Checkbox } from '@/components/ui/Checkbox'
import { ColumnHeader } from './ColumnHeader'
import { DataCell } from './DataCell'

export type DataTableColumn<Row extends RowData> = DataTableColumnDefinition<Row> & {
  id: string
}

type DataTableProps<Row extends RowData> = {
  className?: string
  emptyMessage: string
  label: string
  table: DataTableInstance<Row>
}

export const DataTable = <Row extends RowData>({ className = '', emptyMessage, label, table }: DataTableProps<Row>) => {
  const rows = table.getRowModel().rows
  if (rows.length === 0) return <p>{emptyMessage}</p>

  const headers = table.getLeafHeaders()
  const selectable = table.options.enableRowSelection !== false
  const allSelected = table.getIsAllRowsSelected()

  return (
    <Table aria-label={label} containerClassName={className}>
      <TableHeader>
        <TableRow className="hover:outline-0">
          {selectable && (
            <TableHead className="left-0 z-40 w-10 min-w-10 text-center" scope="col">
              <Checkbox
                aria-label="Select all rows"
                checked={allSelected}
                indeterminate={!allSelected && table.getIsSomeRowsSelected()}
                onCheckedChange={(checked) => table.toggleAllRowsSelected(checked, { deselectAll: true })}
              />
            </TableHead>
          )}
          {headers.map((header, columnIndex) => (
            <ColumnHeader header={header} key={header.id} sticky={selectable && columnIndex === 0} table={table} />
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => (
          <TableRow key={row.id}>
            {selectable && (
              <TableCell className="sticky left-0 z-20 w-10 min-w-10 bg-white text-center">
                <Checkbox
                  aria-label={`Select ${row.id}`}
                  checked={row.getIsSelected()}
                  onCheckedChange={(checked, { event }) => {
                    row.getToggleSelectedHandler()({ nativeEvent: event, target: { checked } })
                  }}
                />
              </TableCell>
            )}
            {row.getVisibleCells().map((cell, columnIndex) => (
              <DataCell cell={cell} key={cell.id} sticky={selectable && columnIndex === 0} table={table} />
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
