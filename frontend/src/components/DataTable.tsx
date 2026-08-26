import type { RowData } from '@tanstack/react-table'
import { useRef, useState, type CSSProperties, type ReactNode } from 'react'

import { cn } from '@/lib/utils'

import { displayValue, type DisplayValue } from '../lib/value'
import type { DataTableInstance } from './data-table-model'
import { Button } from './ui/button'
import { Checkbox } from './ui/checkbox'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table'
import { Tooltip, TooltipContent, TooltipTrigger } from './ui/tooltip'

export interface DataTableColumn<Row extends RowData> {
  align?: 'left' | 'right'
  cellClassName?: (value: DisplayValue, row: Row) => string | undefined
  id: string
  label: ReactNode
  maxWidth?: CSSProperties['maxWidth']
  render?: (value: DisplayValue, row: Row) => ReactNode
  sortable?: boolean
  tooltip?: (value: DisplayValue, row: Row) => string
  title?: string
  truncate?: boolean
  value: (row: Row) => DisplayValue
}

interface DataTableProps<Row extends RowData> {
  className?: string
  columns: DataTableColumn<Row>[]
  emptyMessage: string
  label: string
  table: DataTableInstance<Row>
}

type OverflowValueProps = { children: ReactNode; maxWidth?: CSSProperties['maxWidth']; text: string }

function OverflowValue({ children, maxWidth, text }: OverflowValueProps) {
  const value = useRef<HTMLSpanElement>(null)
  const [open, setOpen] = useState(false)

  return (
    <Tooltip
      onOpenChange={(nextOpen) => {
        const element = value.current
        setOpen(nextOpen && element != null && element.scrollWidth > element.clientWidth)
      }}
      open={open}
    >
      <TooltipTrigger className="block max-w-64" render={<span style={{ maxWidth }} />}>
        <span className="block overflow-hidden text-ellipsis whitespace-nowrap" ref={value}>
          {children}
        </span>
      </TooltipTrigger>
      <TooltipContent align="start" side="bottom">
        {text}
      </TooltipContent>
    </Tooltip>
  )
}

type ColumnHeaderProps<Row extends RowData> = {
  column: DataTableColumn<Row>
  sticky: boolean
  table: DataTableInstance<Row>
}

function ColumnHeader<Row extends RowData>({ column, sticky, table }: ColumnHeaderProps<Row>) {
  const tableColumn = table.getColumn(column.id)
  if (tableColumn == null) return null

  const direction = tableColumn.getIsSorted()
  return (
    <TableHead
      aria-sort={direction === 'asc' ? 'ascending' : direction === 'desc' ? 'descending' : undefined}
      className={cn(column.align === 'right' && 'text-right', sticky && 'left-10 z-30 border-r border-border bg-muted')}
      scope="col"
      title={column.title}
    >
      {column.sortable === false ? (
        column.label
      ) : (
        <Button
          className={cn(
            'w-full gap-2 rounded-none p-0 text-left font-semibold whitespace-nowrap hover:bg-transparent',
            column.align === 'right' && 'justify-end text-right'
          )}
          onClick={() => tableColumn.toggleSorting(direction === 'asc')}
          type="button"
          variant="ghost"
        >
          <span>{column.label}</span>
          <span aria-hidden="true" className="w-4 text-center text-muted-foreground">
            {direction === 'asc' ? '↑' : direction === 'desc' ? '↓' : '↕'}
          </span>
        </Button>
      )}
    </TableHead>
  )
}

type DataCellProps<Row extends RowData> = {
  column: DataTableColumn<Row>
  row: Row
  sticky: boolean
}

function DataCell<Row extends RowData>({ column, row, sticky }: DataCellProps<Row>) {
  const value = column.value(row)
  const content = column.render?.(value, row) ?? displayValue(value)
  const tooltip = column.tooltip?.(value, row) ?? displayValue(value)

  return (
    <TableCell
      className={cn(
        column.align === 'right' && 'text-right',
        sticky && 'sticky left-10 z-10 border-r border-border bg-white',
        column.cellClassName?.(value, row)
      )}
    >
      {(column.truncate || column.maxWidth != null) && tooltip !== '-' ? (
        <OverflowValue maxWidth={column.maxWidth} text={tooltip}>
          {content}
        </OverflowValue>
      ) : (
        content
      )}
    </TableCell>
  )
}

export function DataTable<Row extends RowData>({
  className,
  columns,
  emptyMessage,
  label,
  table
}: DataTableProps<Row>) {
  const rows = table.getRowModel().rows
  if (rows.length === 0) return <p>{emptyMessage}</p>

  const allSelected = table.getIsAllRowsSelected()

  return (
    <Table aria-label={label} containerClassName={className}>
      <TableHeader>
        <TableRow className="hover:outline-0">
          <TableHead className="left-0 z-40 w-10 min-w-10 text-center" scope="col">
            <Checkbox
              aria-label="Select all rows"
              checked={allSelected}
              indeterminate={!allSelected && table.getIsSomeRowsSelected()}
              onCheckedChange={(checked) => table.toggleAllRowsSelected(checked, { deselectAll: true })}
            />
          </TableHead>
          {columns.map((column, columnIndex) => (
            <ColumnHeader column={column} key={column.id} sticky={columnIndex === 0} table={table} />
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => (
          <TableRow key={row.id}>
            <TableCell className="sticky left-0 z-20 w-10 min-w-10 bg-white text-center">
              <Checkbox
                aria-label={`Select ${row.id}`}
                checked={row.getIsSelected()}
                onCheckedChange={(checked, { event }) => {
                  row.getToggleSelectedHandler()({ nativeEvent: event, target: { checked } })
                }}
              />
            </TableCell>
            {columns.map((column, columnIndex) => (
              <DataCell column={column} key={column.id} row={row.original} sticky={columnIndex === 0} />
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
