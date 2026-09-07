import { useTable, type Cell, type Header, type RowData } from '@tanstack/react-table'
import { useRef, useState, type CSSProperties, type ReactNode } from 'react'

import { cn } from '@/lib/class-merge'

import { displayValue } from '@/lib/value'
import { dataTableFeatures, type DataTableColumnDefinition, type DataTableInstance } from './data-table-model'
import { Button } from '@/components/ui/Button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/Table'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/Tooltip'
import { Checkbox } from '@/components/ui/Checkbox'

export type DataTableColumn<Row extends RowData> = DataTableColumnDefinition<Row> & {
  id: string
}

const DATA_TABLE_INSTANCE = Symbol('data-table-instance')

export interface DataTableModel<Row extends RowData> {
  readonly [DATA_TABLE_INSTANCE]: DataTableInstance<Row>
  className?: string
  emptyMessage: string
  label: string
}

interface DataTableProps<Row extends RowData> {
  model: DataTableModel<Row>
}

interface UseDataTableOptions<Row extends RowData> {
  className?: string
  columns: readonly DataTableColumnDefinition<Row>[]
  emptyMessage: string
  getRowId: (row: Row, index: number) => string
  label: string
  rows: Row[]
}

export function useDataTable<Row extends RowData>({
  className,
  columns,
  emptyMessage,
  getRowId,
  label,
  rows
}: UseDataTableOptions<Row>): DataTableModel<Row> {
  const table = useTable({
    columns,
    data: rows,
    defaultColumn: { sortUndefined: 'last' },
    enableMultiSort: false,
    enableRowSelection: false,
    features: dataTableFeatures,
    getRowId
  })
  return createDataTableModel({ ...(className == null ? {} : { className }), emptyMessage, label, table })
}

export function createDataTableModel<Row extends RowData>({
  className,
  emptyMessage,
  label,
  table
}: {
  className?: string
  emptyMessage: string
  label: string
  table: DataTableInstance<Row>
}): DataTableModel<Row> {
  return { [DATA_TABLE_INSTANCE]: table, ...(className == null ? {} : { className }), emptyMessage, label }
}

interface OverflowValueProps {
  children: ReactNode
  maxWidth?: CSSProperties['maxWidth']
  text: string
}

export function DataTableOverflowValue({ children, maxWidth, text }: OverflowValueProps) {
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
        <span className="block truncate" ref={value}>
          {children}
        </span>
      </TooltipTrigger>
      <TooltipContent align="start" side="bottom">
        {text}
      </TooltipContent>
    </Tooltip>
  )
}

interface ColumnHeaderProps<Row extends RowData> {
  header: Header<typeof dataTableFeatures, Row>
  sticky: boolean
  table: DataTableInstance<Row>
}

function ColumnHeader<Row extends RowData>({ header, sticky, table }: ColumnHeaderProps<Row>) {
  const { column } = header
  const meta = column.columnDef.meta
  const direction = column.getIsSorted()
  const label = <table.FlexRender header={header} />
  return (
    <TableHead
      aria-sort={direction === 'asc' ? 'ascending' : direction === 'desc' ? 'descending' : undefined}
      className={cn(meta?.align === 'right' && 'text-right', sticky && 'left-10 z-30 border-r border-border bg-muted')}
      scope="col"
      title={meta?.title}
    >
      {column.getCanSort() ? (
        <Button
          className={cn(
            'w-full gap-2 rounded-none p-0 text-left font-semibold whitespace-nowrap hover:bg-transparent',
            meta?.align === 'right' && 'justify-end text-right'
          )}
          onClick={() => column.toggleSorting(direction === 'asc')}
          type="button"
          variant="ghost"
        >
          <span>{label}</span>
          <span aria-hidden="true" className="w-4 text-center text-muted-foreground">
            {direction === 'asc' ? '↑' : direction === 'desc' ? '↓' : '↕'}
          </span>
        </Button>
      ) : (
        label
      )}
    </TableHead>
  )
}

interface DataCellProps<Row extends RowData> {
  cell: Cell<typeof dataTableFeatures, Row>
  sticky: boolean
  table: DataTableInstance<Row>
}

function DataCell<Row extends RowData>({ cell, sticky, table }: DataCellProps<Row>) {
  const meta = cell.column.columnDef.meta
  const value = cell.getValue()
  const content = cell.column.columnDef.cell != null ? <table.FlexRender cell={cell} /> : displayValue(value)
  const tooltip = displayValue(value)

  return (
    <TableCell
      className={cn(
        meta?.align === 'right' && 'text-right',
        sticky && 'sticky left-10 z-10 border-r border-border bg-white',
        meta?.highlightBoolean === true &&
          typeof value === 'boolean' &&
          (value ? 'bg-success-subtle' : 'bg-error-subtle')
      )}
    >
      {(meta?.truncate === true || meta?.maxWidth != null) && tooltip !== '-' ? (
        <DataTableOverflowValue maxWidth={meta.maxWidth} text={tooltip}>
          {content}
        </DataTableOverflowValue>
      ) : (
        content
      )}
    </TableCell>
  )
}

export function DataTable<Row extends RowData>({ model }: DataTableProps<Row>) {
  const { className = '', emptyMessage, label } = model
  const table = model[DATA_TABLE_INSTANCE]
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
