import * as z from 'zod/mini'

export const COPIER_ANSWERS = '.copier-answers.yml'
export const REPOSITORIES = 'Repositories'
export const TEMPLATE = 'Template'
export const VERSION = 'Version'
export const VALIDATION = 'Validation'

export const dashboardValueSchema = z.union([z.string(), z.number(), z.boolean(), z.null()])
const dashboardColumnSchema = z.object({
  filter: z.nullable(
    z.object({
      kind: z.enum(['text', 'values']),
      optionOrder: z.enum(['answer', 'frequency', 'version'])
    })
  ),
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
export type DashboardFilterDefinition = NonNullable<DashboardColumn['filter']>
export type DashboardFilterKind = DashboardFilterDefinition['kind']
export type DashboardFilterOptionOrder = DashboardFilterDefinition['optionOrder']
export type FilterableDashboardColumn = DashboardColumn & { filter: DashboardFilterDefinition }

export interface CountedValue {
  count: number
  value: FilterValue
}

export function parseDashboardSnapshot(value: unknown): DashboardSnapshot {
  const result = z.safeParse(dashboardSnapshotSchema, value)
  if (!result.success) {
    throw new Error('The Copier report has an invalid data format.', { cause: result.error })
  }
  return result.data
}

export function repositoryName(value: string): string {
  return value.slice(value.lastIndexOf('/') + 1)
}

export function isFilterableDashboardColumn(column: DashboardColumn): column is FilterableDashboardColumn {
  return column.filter != null
}
