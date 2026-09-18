export type ExplorerSort<ColumnId extends string> = {
  column: ColumnId
  direction: 'asc' | 'desc'
} | null

export type ExplorerState<ColumnId extends string, Filter> = {
  filters: Partial<Record<ColumnId, Filter>>
  search: string
  sort: ExplorerSort<ColumnId>
  visibleColumns: ColumnId[]
}

/** Guards column and filter lists read back from a URL, where repeats are meaningless. */
export const isUnique = (values: readonly unknown[]): boolean => new Set(values).size === values.length

export const replaceExplorerFilter = <ColumnId extends string, Filter>(
  filters: Partial<Record<ColumnId, Filter>>,
  column: ColumnId,
  value: Filter | null
): Partial<Record<ColumnId, Filter>> => {
  const next = { ...filters }
  if (value == null) Reflect.deleteProperty(next, column)
  else next[column] = value
  return next
}
