import * as z from 'zod/mini'

import { isUnique, type TableState } from '@/components/data-table/table-state'
import {
  buildUpdaterFilterDefinitions,
  UPDATER_REPOSITORY_COLUMN,
  UPDATER_RESULT_COLUMN_IDS,
  type UpdaterResultColumnId
} from '../updaters/result-columns'
import type { UpdaterReportSnapshot } from './updater-report'

const UPDATER_STATE_VERSION = 1

export type UpdaterDashboardState = {
  search: string
  version: typeof UPDATER_STATE_VERSION
} & TableState<UpdaterResultColumnId, string[]>

const updaterDashboardStateSchema = z.object({
  filters: z.record(z.string(), z.array(z.string()).check(z.minLength(1))),
  search: z.string(),
  // One column at a time: the table is built with `enableMultiSort: false`.
  sorting: z.array(z.object({ desc: z.boolean(), id: z.enum(UPDATER_RESULT_COLUMN_IDS) })).check(z.maxLength(1)),
  version: z.literal(UPDATER_STATE_VERSION),
  visibleColumns: z.array(z.enum(UPDATER_RESULT_COLUMN_IDS))
})

export const DEFAULT_UPDATER_DASHBOARD_STATE: UpdaterDashboardState = {
  filters: {},
  search: '',
  sorting: [],
  version: UPDATER_STATE_VERSION,
  visibleColumns: [...UPDATER_RESULT_COLUMN_IDS]
}

/** Rejects anything this report cannot render, so a stale or hand-edited URL falls back to the defaults. */
export const parseUpdaterDashboardState = (
  value: unknown,
  report: UpdaterReportSnapshot
): UpdaterDashboardState | null => {
  const parsed = z.safeParse(updaterDashboardStateSchema, value)
  if (!parsed.success) return null
  const state: UpdaterDashboardState = parsed.data
  return validUpdaterDashboardState(state, report) ? state : null
}

const validUpdaterDashboardState = (state: UpdaterDashboardState, report: UpdaterReportSnapshot): boolean => {
  if (!state.visibleColumns.includes(UPDATER_REPOSITORY_COLUMN) || !isUnique(state.visibleColumns)) return false

  const filters = new Map<string, Set<string>>(
    buildUpdaterFilterDefinitions(report.results).map(({ column, options }) => [
      column,
      new Set(options.map(({ value }) => value))
    ])
  )
  return Object.entries(state.filters).every(([id, values]) => {
    const validValues = filters.get(id)
    return values.length > 0 && isUnique(values) && values.every((item) => validValues?.has(item) === true)
  })
}
