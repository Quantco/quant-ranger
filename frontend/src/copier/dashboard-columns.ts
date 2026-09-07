import {
  COPIER_ANSWERS,
  REPOSITORIES,
  TEMPLATE,
  VALIDATION,
  VERSION,
  type DashboardColumn,
  type DashboardRow,
  type DashboardSnapshot
} from './dashboard'

export type DashboardFilterKind = 'text' | 'values'
export type DashboardFilterOptionOrder = 'answer' | 'frequency' | 'version'
export interface DashboardFilterDefinition {
  kind: DashboardFilterKind
  optionOrder: DashboardFilterOptionOrder
}
export type DashboardColumnModel = DashboardColumn & { filter: DashboardFilterDefinition | null }
export type FilterableDashboardColumn = DashboardColumnModel & { filter: DashboardFilterDefinition }

const VALUE_FILTER_COLUMNS = new Set([REPOSITORIES, TEMPLATE, VERSION, VALIDATION])

export function createDashboardColumns({ columns, rows }: DashboardSnapshot): DashboardColumnModel[] {
  const categoricalAnswerColumns = findCategoricalAnswerColumns(columns, rows)
  return columns.map((column) => ({
    ...column,
    filter: filterDefinition(column, categoricalAnswerColumns)
  }))
}

export function isFilterableDashboardColumn(column: DashboardColumnModel): column is FilterableDashboardColumn {
  return column.filter != null
}

function filterDefinition(
  column: DashboardColumn,
  categoricalAnswerColumns: ReadonlySet<string>
): DashboardFilterDefinition | null {
  if (column.id === COPIER_ANSWERS) return null
  const categoricalAnswer = categoricalAnswerColumns.has(column.id)
  return {
    kind: VALUE_FILTER_COLUMNS.has(column.id) || categoricalAnswer ? 'values' : 'text',
    optionOrder: column.id === VERSION ? 'version' : categoricalAnswer ? 'answer' : 'frequency'
  }
}

function findCategoricalAnswerColumns(columns: DashboardColumn[], rows: DashboardRow[]): Set<string> {
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
      .filter(({ id }) => scopes.some((scope) => isBooleanAnswerColumn(scope, id)))
      .map(({ id }) => id)
  )
}

function isBooleanAnswerColumn(rows: DashboardRow[], columnId: string): boolean {
  const values = rows.map((row) => row.values[columnId]).filter((value) => value != null && value !== '')
  return values.length > 0 && values.every((value) => typeof value === 'boolean')
}
