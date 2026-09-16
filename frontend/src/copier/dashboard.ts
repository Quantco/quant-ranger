import * as z from 'zod/mini'

export const COPIER_ANSWERS = '.copier-answers.yml'
export const REPOSITORIES = 'Repositories'
export const TEMPLATE = 'Template'
export const VERSION = 'Version'
export const VALIDATION = 'Validation'

export const dashboardValueSchema = z.union([z.string(), z.number(), z.boolean(), z.null()])
const dashboardColumnSchema = z.object({
  id: z.string(),
  kind: z.enum(['answer', 'metadata', 'repository'])
})
const dashboardRowSchema = z.object({
  repository: z.string(),
  url: z.string(),
  validationFailure: z.string(),
  values: z.record(z.string(), dashboardValueSchema)
})
const dashboardSnapshotSchema = z.object({
  columns: z.array(dashboardColumnSchema),
  generatedAt: z.string(),
  rows: z.array(dashboardRowSchema),
  versions: z.array(z.string())
})

export type DashboardSnapshot = z.infer<typeof dashboardSnapshotSchema>
export type DashboardRow = z.infer<typeof dashboardRowSchema>
export type DashboardValue = z.infer<typeof dashboardValueSchema> | undefined
export type FilterValue = Exclude<DashboardValue, undefined>
export type DashboardColumn = DashboardSnapshot['columns'][number]

export type CountedValue = {
  count: number
  value: FilterValue
}

export const parseDashboardSnapshot = (value: unknown): DashboardSnapshot => {
  const result = z.safeParse(dashboardSnapshotSchema, value)
  if (!result.success) {
    throw new Error('The Copier report has an invalid data format.', { cause: result.error })
  }
  return result.data
}

export const repositoryName = (value: string): string => value.slice(value.lastIndexOf('/') + 1)

export const isDashboardColumn = (value: unknown): value is DashboardColumn =>
  z.safeParse(dashboardColumnSchema, value).success

export const isFilterValue = (value: unknown): value is FilterValue =>
  value === null || ['boolean', 'number', 'string'].includes(typeof value)
