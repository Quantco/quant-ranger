import { useMemo, useState } from 'react'

import { useDashboardUrlState } from '../hooks/useDashboardUrlState'
import { DEFAULT_FILTER_COLUMNS, DEFAULT_TABLE_COLUMNS } from './dashboard-url-state'
import type { CopierDashboardUrlState } from './dashboard-url-state'
import { copierDashboardSearchParameters, readCopierDashboardUrlState } from './dashboard-url'
import {
  COPIER_ANSWERS,
  REPOSITORIES,
  TEMPLATE,
  VALIDATION,
  VERSION,
  answerCounts,
  countAllValues,
  countBy,
  filterRowsByTextFilters,
  filterRowsByValueFilters,
  removeValueFilter
} from './dashboard'
import type { CountedValue, DashboardRow, DashboardSnapshot, FilterValue, TextFilter, ValueFilter } from './dashboard'

export type DashboardFilter =
  | {
      column: string
      filter?: TextFilter
      kind: 'text'
      options: CountedValue[]
    }
  | {
      column: string
      filter?: ValueFilter
      kind: 'value'
      options: CountedValue[]
    }

function versionDistribution(data: CountedValue[], versions: string[]) {
  const order = new Map(versions.map((version, index) => [version, index]))
  return data.toSorted(
    (left, right) => (order.get(String(left.value)) ?? Infinity) - (order.get(String(right.value)) ?? Infinity)
  )
}

function replaceTextFilter(filters: TextFilter[], column: string, query: string) {
  const otherFilters = filters.filter((filter) => filter.column !== column)
  const existingFilter = filters.find((filter) => filter.column === column)
  return query.trim() === '' ? otherFilters : [...otherFilters, { column, inverted: existingFilter?.inverted, query }]
}

function replaceValueFilter(filters: ValueFilter[], column: string, values: FilterValue[]) {
  const otherFilters = removeValueFilter(filters, column)
  const existingFilter = filters.find((filter) => filter.column === column)
  return values.length === 0 ? otherFilters : [...otherFilters, { column, inverted: existingFilter?.inverted, values }]
}

function setFilterInverted<Filter extends TextFilter | ValueFilter>(
  filters: Filter[],
  column: string,
  inverted: boolean
) {
  return filters.map((filter) => (filter.column === column ? { ...filter, inverted: inverted || undefined } : filter))
}

export function deriveCopierDashboard(snapshot: DashboardSnapshot, state: CopierDashboardUrlState) {
  const { rows } = snapshot
  const { selectedChartColumns, selectedFilterColumns, selectedTableColumns, textFilters, valueFilters } = state
  const textFilteredRows = filterRowsByTextFilters(rows, textFilters)
  const filteredRows = filterRowsByValueFilters(textFilteredRows, valueFilters)
  const textFilterByColumn = new Map(textFilters.map((filter) => [filter.column, filter]))
  const valueFilterByColumn = new Map(valueFilters.map((filter) => [filter.column, filter]))

  const answerColumns = new Set(snapshot.answer_groups.flatMap(({ fields }) => fields))
  const valueFilterColumns = new Set([REPOSITORIES, TEMPLATE, VERSION, VALIDATION, ...answerColumns])
  const filterColumns = snapshot.columns.filter((column) => column !== COPIER_ANSWERS)
  const templateFilter = valueFilterByColumn.get(TEMPLATE)
  const selectedTemplates = templateFilter?.inverted
    ? []
    : (templateFilter?.values.filter((value): value is string => typeof value === 'string') ?? [])
  const versions = [
    ...new Set(
      snapshot.version_options
        .filter(
          ({ template }) => selectedTemplates.length === 0 || template == null || selectedTemplates.includes(template)
        )
        .flatMap(({ versions: options }) => options)
    )
  ]

  const availableTableColumns =
    selectedTemplates.length === 0 ? snapshot.columns : snapshot.columns.filter((column) => column !== COPIER_ANSWERS)
  const visibleTableColumns = availableTableColumns.filter(
    (column) => column === REPOSITORIES || selectedTableColumns.has(column)
  )

  const filters: DashboardFilter[] = [...selectedFilterColumns]
    .filter((column) => filterColumns.includes(column))
    .map((column) => {
      if (!valueFilterColumns.has(column)) {
        return {
          column,
          filter: textFilterByColumn.get(column),
          kind: 'text',
          options: countBy(
            filterRowsByValueFilters(
              filterRowsByTextFilters(
                rows,
                textFilters.filter((filter) => filter.column !== column)
              ),
              valueFilters
            ),
            column
          )
        }
      }

      const countValues = answerColumns.has(column) ? answerCounts : countBy
      const options = countValues(filterRowsByValueFilters(textFilteredRows, valueFilters, column), column)
      const selectedValues = valueFilterByColumn.get(column)?.values ?? []
      const missingOptions = selectedValues
        .filter((selectedValue) => !options.some(({ value }) => Object.is(value, selectedValue)))
        .map((value) => ({ count: 0, value }))
      const allOptions = [...missingOptions, ...options]
      return {
        column,
        filter: valueFilterByColumn.get(column),
        kind: 'value',
        options: column === VERSION ? versionDistribution(allOptions, versions) : allOptions
      }
    })

  const charts = snapshot.columns
    .filter((column) => selectedChartColumns.has(column))
    .map((column) => ({
      column,
      data: countAllValues(filteredRows, column),
      domain: countAllValues(rows, column).map(({ value }) => value)
    }))

  return { availableTableColumns, charts, filterColumns, filteredRows, filters, visibleTableColumns }
}

export function useCopierDashboard(snapshot: DashboardSnapshot) {
  const [state, updateState] = useDashboardUrlState({
    context: snapshot,
    read: readCopierDashboardUrlState,
    write: copierDashboardSearchParameters
  })
  const [selectedRows, setSelectedRows] = useState<DashboardRow[] | null>(null)
  const model = useMemo(() => deriveCopierDashboard(snapshot, state), [snapshot, state])

  const filteredRowSet = new Set(model.filteredRows)
  const repositoryNames = (selectedRows ?? model.filteredRows)
    .filter((row) => filteredRowSet.has(row))
    .map((row) => row.repository)

  const updateFilterColumns = (selectedFilterColumns: Set<string>) => {
    const removedColumns = new Set(
      [...state.selectedFilterColumns].filter((column) => !selectedFilterColumns.has(column))
    )
    updateState({
      selectedFilterColumns,
      textFilters: state.textFilters.filter(({ column }) => !removedColumns.has(column)),
      valueFilters: state.valueFilters.filter(({ column }) => !removedColumns.has(column))
    })
  }

  return {
    charts: model.charts,
    filterActions: {
      onTextChange: (column: string, query: string) =>
        updateState({ textFilters: replaceTextFilter(state.textFilters, column, query) }),
      onTextInvert: (column: string, inverted: boolean) =>
        updateState({ textFilters: setFilterInverted(state.textFilters, column, inverted) }),
      onValueChange: (column: string, values: FilterValue[]) =>
        updateState({ valueFilters: replaceValueFilter(state.valueFilters, column, values) }),
      onValueInvert: (column: string, inverted: boolean) =>
        updateState({ valueFilters: setFilterInverted(state.valueFilters, column, inverted) })
    },
    filterFields: {
      fields: model.filterColumns,
      onChange: updateFilterColumns,
      selected: state.selectedFilterColumns
    },
    filters: model.filters,
    generatedAt: snapshot.generated_at,
    onReset: () =>
      updateState({
        selectedChartColumns: new Set(),
        selectedFilterColumns: new Set(DEFAULT_FILTER_COLUMNS),
        selectedTableColumns: new Set(DEFAULT_TABLE_COLUMNS),
        textFilters: [],
        valueFilters: []
      }),
    pieCharts: {
      fields: snapshot.columns,
      onChange: (selectedChartColumns: Set<string>) => updateState({ selectedChartColumns }),
      selected: state.selectedChartColumns
    },
    repositories: {
      columns: model.visibleTableColumns,
      onSelectionChange: setSelectedRows,
      onSortChange: (sort: CopierDashboardUrlState['sort']) => updateState({ sort }),
      repositoryNames,
      rows: model.filteredRows,
      sort: state.sort
    },
    repositoryCount: snapshot.rows.length,
    tableColumns: {
      fields: model.availableTableColumns,
      onChange: (selectedTableColumns: Set<string>) => updateState({ selectedTableColumns }),
      selected: state.selectedTableColumns
    }
  }
}
