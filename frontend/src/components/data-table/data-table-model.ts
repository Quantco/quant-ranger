import {
  columnFacetingFeature,
  columnFilteringFeature,
  columnVisibilityFeature,
  createFacetedRowModel,
  createFacetedUniqueValues,
  createFilteredRowModel,
  createSortedRowModel,
  globalFilteringFeature,
  metaHelper,
  rowSelectionFeature,
  rowSortingFeature,
  tableFeatures,
  type ColumnDef,
  type RowData,
  type ReactTable
} from '@tanstack/react-table'
import type { CSSProperties } from 'react'

export interface DataTableColumnMeta {
  align?: 'left' | 'right'
  highlightBoolean?: boolean
  maxWidth?: CSSProperties['maxWidth']
  title?: string
  truncate?: boolean
}

export const dataTableFeatures = tableFeatures({
  columnFacetingFeature,
  columnFilteringFeature,
  columnMeta: metaHelper<DataTableColumnMeta>(),
  columnVisibilityFeature,
  facetedRowModel: createFacetedRowModel(),
  facetedUniqueValues: createFacetedUniqueValues(),
  filteredRowModel: createFilteredRowModel(),
  globalFilteringFeature,
  rowSelectionFeature,
  rowSortingFeature,
  sortedRowModel: createSortedRowModel()
})

export type DataTableColumnDefinition<Row extends RowData, Value = unknown> = ColumnDef<
  typeof dataTableFeatures,
  Row,
  Value
>
export type DataTableInstance<Row extends RowData> = ReactTable<typeof dataTableFeatures, Row>
