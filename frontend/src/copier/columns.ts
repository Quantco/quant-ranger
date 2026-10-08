import {
  COPIER_ANSWERS,
  REPOSITORIES,
  TEMPLATE,
  VALIDATION,
  VERSION,
  type ReportColumn,
  type Row,
  type Snapshot
} from './report'

export type FilterKind = 'text' | 'values'
export type OptionOrder = 'answer' | 'frequency' | 'version'

/** How a column can be filtered, and how its options are ordered. */
export type ColumnFilter = {
  kind: FilterKind
  optionOrder: OptionOrder
}

/** A reported column plus how it filters. The working shape everything else uses. */
export type Column = ReportColumn & { filter: ColumnFilter | null }
export type FilterableColumn = Column & { filter: ColumnFilter }

const VALUE_FILTER_COLUMNS = new Set([REPOSITORIES, TEMPLATE, VERSION, VALIDATION])

export const buildColumns = ({ columns, rows }: Snapshot): Column[] => {
  const categorical = categoricalAnswers(columns, rows)
  return columns.map((column) => ({ ...column, filter: columnFilter(column, categorical) }))
}

export const isFilterable = (column: Column): column is FilterableColumn => column.filter != null

const columnFilter = (column: ReportColumn, categorical: ReadonlySet<string>): ColumnFilter | null => {
  if (column.id === COPIER_ANSWERS) return null
  const categoricalAnswer = categorical.has(column.id)
  return {
    kind: VALUE_FILTER_COLUMNS.has(column.id) || categoricalAnswer ? 'values' : 'text',
    optionOrder: column.id === VERSION ? 'version' : categoricalAnswer ? 'answer' : 'frequency'
  }
}

/**
 * Answer columns that are boolean across the whole fleet or within any single
 * template. Those get a value picker rather than a text box.
 */
const categoricalAnswers = (columns: ReportColumn[], rows: Row[]): Set<string> => {
  const templates = [
    ...new Set(
      rows.flatMap((row) => {
        const template = row.values[TEMPLATE]
        return typeof template === 'string' && template !== '' ? [template] : []
      })
    )
  ]
  const scopes = [rows, ...templates.map((template) => rows.filter((row) => row.values[TEMPLATE] === template))]
  return new Set(
    columns
      .filter(({ kind }) => kind === 'answer')
      .filter(({ id }) => scopes.some((scope) => isBooleanColumn(scope, id)))
      .map(({ id }) => id)
  )
}

const isBooleanColumn = (rows: Row[], columnId: string): boolean => {
  const values = rows.map((row) => row.values[columnId]).filter((value) => value != null && value !== '')
  return values.length > 0 && values.every((value) => typeof value === 'boolean')
}
