import {
  createSortedRowModel,
  rowSelectionFeature,
  rowSortingFeature,
  tableFeatures,
  useTable,
  type ColumnDef,
  type RowData,
  type SortingState
} from '@tanstack/react-table'
import { useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react'

import { cn } from '@/lib/utils'

import { displayValue, type DisplayValue } from '../lib/value'
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
  getRowKey: (row: Row, index: number) => string
  label: string
  onSelectionChange?: (rows: Row[]) => void
  onSortChange?: (sort: DataTableSort) => void
  rows: Row[]
  sort?: DataTableSort | null
}

export type DataTableSort = { direction: 'ascending' | 'descending'; id: string }

const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' })
const dataTableFeatures = tableFeatures({
  rowSelectionFeature,
  rowSortingFeature,
  sortFns: {
    display: (left, right, columnId) => {
      const leftValue = left.getValue<DisplayValue>(columnId)
      const rightValue = right.getValue<DisplayValue>(columnId)
      if (Object.is(leftValue, rightValue)) return 0
      if (leftValue instanceof Date && rightValue instanceof Date) return leftValue.valueOf() - rightValue.valueOf()
      if (typeof leftValue === 'number' && typeof rightValue === 'number') return leftValue - rightValue
      if (typeof leftValue === 'boolean' && typeof rightValue === 'boolean')
        return Number(leftValue) - Number(rightValue)
      return collator.compare(String(leftValue), String(rightValue))
    }
  },
  sortedRowModel: createSortedRowModel()
})

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
  direction?: DataTableSort['direction']
  onSort: (sort: DataTableSort) => void
  sticky: boolean
}

function ColumnHeader<Row extends RowData>({ column, direction, onSort, sticky }: ColumnHeaderProps<Row>) {
  return (
    <TableHead
      aria-sort={direction}
      className={cn(
        column.align === 'right' && 'text-right',
        sticky && 'left-10 z-[3] bg-muted shadow-[1px_0_var(--color-border)]'
      )}
      scope="col"
      title={column.title}
    >
      {column.sortable === false ? (
        column.label
      ) : (
        <Button
          className={cn(
            'w-full gap-[0.45rem] rounded-none p-0 text-left font-semibold whitespace-nowrap hover:bg-transparent',
            column.align === 'right' && 'justify-end text-right'
          )}
          onClick={() => onSort({ direction: direction === 'ascending' ? 'descending' : 'ascending', id: column.id })}
          type="button"
          variant="ghost"
        >
          <span>{column.label}</span>
          <span aria-hidden="true" className="w-[1em] text-center text-muted-foreground">
            {direction === 'ascending' ? '↑' : direction === 'descending' ? '↓' : '↕'}
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
        sticky && 'sticky left-10 z-[1] bg-white shadow-[1px_0_var(--color-border)]',
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
  getRowKey,
  label,
  onSelectionChange,
  onSortChange,
  rows,
  sort
}: DataTableProps<Row>) {
  const selectable = onSelectionChange != null
  const [uncontrolledSort, setUncontrolledSort] = useState<DataTableSort | null>(null)
  const activeSort = sort === undefined ? uncontrolledSort : sort
  const sorting: SortingState =
    activeSort == null ? [] : [{ desc: activeSort.direction === 'descending', id: activeSort.id }]
  const tableColumns = useMemo<ColumnDef<typeof dataTableFeatures, Row>[]>(
    () =>
      columns.map((column) => ({
        accessorFn: (row) => {
          const value = column.value(row)
          return value == null || value === '' || (value instanceof Date && Number.isNaN(value.valueOf()))
            ? undefined
            : value
        },
        enableSorting: column.sortable !== false,
        id: column.id,
        sortFn: 'display',
        sortUndefined: 'last'
      })),
    [columns]
  )
  const table = useTable({
    columns: tableColumns,
    data: rows,
    enableMultiSort: false,
    enableRowSelection: selectable,
    features: dataTableFeatures,
    getRowId: getRowKey,
    initialState: {
      rowSelection: selectable ? Object.fromEntries(rows.map((row, index) => [getRowKey(row, index), true])) : {}
    },
    state: { sorting }
  })
  const { getRowModel, setRowSelection } = table
  const sortedRows = getRowModel().rows

  useEffect(() => {
    if (!onSelectionChange) return
    setRowSelection(Object.fromEntries(getRowModel().rows.map(({ id }) => [id, true])))
    onSelectionChange([...rows])
  }, [getRowModel, onSelectionChange, rows, setRowSelection])

  if (rows.length === 0) return <p>{emptyMessage}</p>

  const updateSort = (next: DataTableSort) => {
    if (sort === undefined) setUncontrolledSort(next)
    onSortChange?.(next)
  }
  const notifySelectionChange = () =>
    onSelectionChange?.(sortedRows.filter((row) => row.getIsSelected()).map(({ original }) => original))
  const allSelected = table.getIsAllRowsSelected()

  return (
    <Table aria-label={label} containerClassName={className}>
      <TableHeader>
        <TableRow className="hover:outline-0">
          {onSelectionChange && (
            <TableHead className="left-0 z-[4] w-10 min-w-10 text-center" scope="col">
              <Checkbox
                aria-label="Select all rows"
                checked={allSelected}
                indeterminate={!allSelected && table.getIsSomeRowsSelected()}
                onCheckedChange={(checked) => {
                  table.toggleAllRowsSelected(checked, { deselectAll: true })
                  onSelectionChange(checked ? sortedRows.map(({ original }) => original) : [])
                }}
              />
            </TableHead>
          )}
          {columns.map((column, columnIndex) => (
            <ColumnHeader
              column={column}
              direction={activeSort?.id === column.id ? activeSort.direction : undefined}
              key={column.id}
              onSort={updateSort}
              sticky={selectable && columnIndex === 0}
            />
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {sortedRows.map((row) => (
          <TableRow key={row.id}>
            {onSelectionChange && (
              <TableCell className="sticky left-0 z-[2] w-10 min-w-10 bg-white text-center">
                <Checkbox
                  aria-label={`Select ${row.id}`}
                  checked={row.getIsSelected()}
                  onCheckedChange={(checked, { event }) => {
                    row.getToggleSelectedHandler()({ nativeEvent: event, target: { checked } })
                    notifySelectionChange()
                  }}
                />
              </TableCell>
            )}
            {columns.map((column, columnIndex) => (
              <DataCell column={column} key={column.id} row={row.original} sticky={selectable && columnIndex === 0} />
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
