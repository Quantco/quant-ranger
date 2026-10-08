import { useRef, useState, type CSSProperties, type ReactNode } from 'react'
import type { Cell, RowData } from '@tanstack/react-table'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/Tooltip'
import { cn } from '@/lib/class-merge'
import { displayValue } from '@/lib/value'
import { dataTableFeatures, type DataTableInstance } from './model'
import { TableCell } from '@/components/ui/Table'

type OverflowValueProps = {
  children: ReactNode
  maxWidth?: CSSProperties['maxWidth']
  text: string
}

export const DataTableOverflowValue = ({ children, maxWidth, text }: OverflowValueProps) => {
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

type DataCellProps<Row extends RowData> = {
  cell: Cell<typeof dataTableFeatures, Row>
  sticky: boolean
  table: DataTableInstance<Row>
}

export const DataCell = <Row extends RowData>({ cell, sticky, table }: DataCellProps<Row>) => {
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
