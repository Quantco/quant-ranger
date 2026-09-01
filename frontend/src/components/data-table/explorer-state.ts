export type ExplorerSort<ColumnId extends string> = {
  column: ColumnId
  direction: 'asc' | 'desc'
} | null

export interface ExplorerState<ColumnId extends string, Filter> {
  filters: Partial<Record<ColumnId, Filter>>
  search: string
  sort: ExplorerSort<ColumnId>
  visibleColumns: ColumnId[]
}

export type ExplorerAction<ColumnId extends string, Filter> =
  | { filters: Partial<Record<ColumnId, Filter>>; type: 'filters/replace' }
  | { search: string; type: 'search/set' }
  | { sort: ExplorerSort<ColumnId>; type: 'sort/set' }
  | { columns: ColumnId[]; type: 'visible-columns/set' }

export function reduceExplorerState<ColumnId extends string, Filter, State extends ExplorerState<ColumnId, Filter>>(
  state: State,
  action: ExplorerAction<ColumnId, Filter>
): State {
  switch (action.type) {
    case 'filters/replace':
      return { ...state, filters: action.filters }
    case 'search/set':
      return { ...state, search: action.search }
    case 'sort/set':
      return { ...state, sort: action.sort }
    case 'visible-columns/set':
      return { ...state, visibleColumns: action.columns }
  }
}

export function replaceExplorerFilter<ColumnId extends string, Filter>(
  filters: Partial<Record<ColumnId, Filter>>,
  column: ColumnId,
  value: Filter | null
): Partial<Record<ColumnId, Filter>> {
  const next = { ...filters }
  if (value == null) Reflect.deleteProperty(next, column)
  else next[column] = value
  return next
}

export function uniqueValues<Value>(values: Value[]): Value[] {
  return [...new Set(values)]
}
