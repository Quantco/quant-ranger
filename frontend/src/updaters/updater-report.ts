import * as z from 'zod/mini'

const optionalString = z.pipe(
  z.optional(z.nullable(z.string())),
  z.transform((value) => (value == null || value === '' ? undefined : value))
)

const updateStatusSchema = z.enum(['failure', 'skipped', 'up-to-date', 'updated'])

const updaterReportResultSchema = z.object({
  details: optionalString,
  message: optionalString,
  pull_request: z.optional(z.nullable(z.number())),
  pull_request_url: optionalString,
  repository: z.string(),
  status: updateStatusSchema,
  target: optionalString,
  target_url: optionalString,
  url: z.string()
})

const updaterReportFailureSchema = z.object({
  details: optionalString,
  message: optionalString,
  repository: z.string(),
  url: z.string()
})

const updaterReportSummarySchema = z.object({
  failures: z.number(),
  scan_failures: z.number(),
  skipped: z.number(),
  total: z.number(),
  up_to_date: z.number(),
  updated: z.number()
})

const updaterReportHeaderShape = {
  dry_run: z.boolean(),
  feed_id: z.string(),
  generated_at: z.string(),
  github_api_url: z.string(),
  summary: updaterReportSummarySchema,
  title: optionalString,
  updater: z.string(),
  updater_options: z.record(z.string(), z.unknown()),
  workflow_url: optionalString
}

const updaterFeedSummarySchema = z.object(updaterReportHeaderShape)
const updaterReportSnapshotSchema = z.object({
  ...updaterReportHeaderShape,
  results: z.array(updaterReportResultSchema),
  scan_failures: z.array(updaterReportFailureSchema)
})
const updaterIndexSchema = z.object({ feeds: z.array(updaterFeedSummarySchema) })

export type UpdateStatus = z.infer<typeof updateStatusSchema>
export type UpdaterReportResult = z.infer<typeof updaterReportResultSchema>
export type UpdaterReportFailure = z.infer<typeof updaterReportFailureSchema>
export type UpdaterFeedSummary = z.infer<typeof updaterFeedSummarySchema>
export type UpdaterReportSnapshot = z.infer<typeof updaterReportSnapshotSchema>

export function parseUpdaterReport(value: unknown): UpdaterReportSnapshot {
  const result = z.safeParse(updaterReportSnapshotSchema, value)
  if (!result.success) throw new Error('The updater report has an invalid data format.', { cause: result.error })
  return result.data
}

export function parseUpdaterIndex(value: unknown) {
  const result = z.safeParse(updaterIndexSchema, value)
  if (!result.success) throw new Error('The updater report index has an invalid data format.', { cause: result.error })
  return result.data
}
