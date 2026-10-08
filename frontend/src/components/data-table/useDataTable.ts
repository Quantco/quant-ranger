import { useTable, type RowData } from '@tanstack/react-table'
import { dataTableFeatures, type DataTableColumnDefinition, type DataTableInstance } from './model'

type UseDataTableOptions<Row extends RowData> = {
  columns: DataTableColumnDefinition<Row>[]
  getRowId: (row: Row, index: number) => string
  rows: Row[]
}

/** A table with no external state: sorting and selection stay inside the instance. */
export const useDataTable = <Row extends RowData>({
  columns,
  getRowId,
  rows
}: UseDataTableOptions<Row>): DataTableInstance<Row> =>
  useTable({
    columns,
    data: rows,
    defaultColumn: { sortUndefined: 'last' },
    enableMultiSort: false,
    enableRowSelection: false,
    features: dataTableFeatures,
    getRowId
  })
