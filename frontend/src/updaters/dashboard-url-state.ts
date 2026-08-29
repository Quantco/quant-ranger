import { useCallback } from 'react'
import * as z from 'zod/mini'

import { reduceExplorerState, type ExplorerAction, type ExplorerState } from '../components/explorer-state'
import { useCompressedUrlReducer } from '../lib/useCompressedUrlState'
import {
  buildUpdaterFilterDefinitions,
  UPDATER_REPOSITORY_COLUMN,
  UPDATER_RESULT_COLUMN_IDS,
  type UpdaterResultColumnId
} from './result-columns'
import type { UpdaterReportSnapshot } from './updater-report'

const UPDATER_STATE_VERSION = 1

export interface UpdaterDashboardUrlState extends ExplorerState<UpdaterResultColumnId, string[]> {
  version: typeof UPDATER_STATE_VERSION
}

export type UpdaterDashboardAction = ExplorerAction<UpdaterResultColumnId, string[]>

const updaterDashboardUrlStateSchema = z.object({
  filters: z.record(z.string(), z.array(z.string()).check(z.minLength(1))),
  search: z.string(),
  sort: z.nullable(z.object({ column: z.enum(UPDATER_RESULT_COLUMN_IDS), direction: z.enum(['asc', 'desc']) })),
  version: z.literal(UPDATER_STATE_VERSION),
  visibleColumns: z.array(z.enum(UPDATER_RESULT_COLUMN_IDS))
})
const DEFAULT_UPDATER_DASHBOARD_URL_STATE: UpdaterDashboardUrlState = {
  filters: {},
  search: '',
  sort: null,
  version: UPDATER_STATE_VERSION,
  visibleColumns: [...UPDATER_RESULT_COLUMN_IDS]
}

export function useUpdaterDashboardUrlState(report: UpdaterReportSnapshot) {
  const parse = useCallback(
    (value: unknown) => parseUpdaterDashboardUrlState(value, DEFAULT_UPDATER_DASHBOARD_URL_STATE, report),
    [report]
  )
  return useCompressedUrlReducer({
    defaultState: DEFAULT_UPDATER_DASHBOARD_URL_STATE,
    parse,
    reducer: updaterDashboardReducer
  })
}

function updaterDashboardReducer(
  state: UpdaterDashboardUrlState,
  action: UpdaterDashboardAction
): UpdaterDashboardUrlState {
  if (action.type !== 'visible-columns/set') return reduceExplorerState(state, action)
  return reduceExplorerState(state, {
    columns: [
      UPDATER_REPOSITORY_COLUMN,
      ...new Set(action.columns.filter((column) => column !== UPDATER_REPOSITORY_COLUMN))
    ],
    type: 'visible-columns/set'
  })
}

function parseUpdaterDashboardUrlState(
  value: unknown,
  defaults: UpdaterDashboardUrlState,
  report: UpdaterReportSnapshot
): UpdaterDashboardUrlState {
  const parsed = z.safeParse(updaterDashboardUrlStateSchema, value)
  if (!parsed.success) return defaults
  const state: UpdaterDashboardUrlState = parsed.data
  return validUpdaterDashboardState(state, report) ? state : defaults
}

function validUpdaterDashboardState(state: UpdaterDashboardUrlState, report: UpdaterReportSnapshot): boolean {
  if (!state.visibleColumns.includes(UPDATER_REPOSITORY_COLUMN) || !unique(state.visibleColumns)) return false

  const statuses = [...new Set(report.results.map(({ status }) => status))].sort()
  const filters = new Map<string, Set<string>>(
    buildUpdaterFilterDefinitions(statuses).map(({ column, options }) => [
      column,
      new Set(options.map(({ value }) => value))
    ])
  )
  return Object.entries(state.filters).every(([id, values]) => {
    const validValues = filters.get(id)
    return values.length > 0 && unique(values) && values.every((item) => validValues?.has(item) === true)
  })
}

function unique(values: readonly unknown[]): boolean {
  return new Set(values).size === values.length
}
