import type { Header, RowData } from '@tanstack/react-table'
import { cn } from '@/lib/class-merge'
import { dataTableFeatures, type DataTableInstance } from './model'
import { Button } from '@/components/ui/Button'
import { TableHead } from '@/components/ui/Table'

type ColumnHeaderProps<Row extends RowData> = {
  header: Header<typeof dataTableFeatures, Row>
  sticky: boolean
  table: DataTableInstance<Row>
}

export const ColumnHeader = <Row extends RowData>({ header, sticky, table }: ColumnHeaderProps<Row>) => {
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
