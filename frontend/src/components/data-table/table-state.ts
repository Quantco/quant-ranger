import type { SortingState } from '@tanstack/react-table'

/**
 * The part of a table's state a dashboard owns, persists and edits from outside
 * the table.
 *
 * Filters and visible columns are in the dashboard's own vocabulary rather than
 * TanStack's: the sidebar reads and writes them, and the URL schema constrains
 * them in ways TanStack's shapes cannot express — one entry per column, values
 * drawn from the column's current options, a column that can never be hidden.
 * They flow one way into the table.
 *
 * Sorting is the exception. Only the table's own headers change it and nothing
 * outside reads it back, so it is stored exactly as TanStack reports it and
 * needs no translation in either direction.
 */
export type TableState<ColumnId extends string, Filter> = {
  filters: Partial<Record<ColumnId, Filter>>
  sorting: SortingState
  visibleColumns: ColumnId[]
}

/** Guards column and filter lists read back from a URL, where repeats are meaningless. */
export const isUnique = (values: readonly unknown[]): boolean => new Set(values).size === values.length

export const replaceFilter = <ColumnId extends string, Filter>(
  filters: Partial<Record<ColumnId, Filter>>,
  column: ColumnId,
  value: Filter | null
): Partial<Record<ColumnId, Filter>> => {
  const next = { ...filters }
  if (value == null) Reflect.deleteProperty(next, column) // TODO: NOOOOO WHAT IS THIS¿??¿?? Reflect??
  else next[column] = value
  return next
}
