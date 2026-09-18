import * as z from 'zod/mini'

export const COPIER_ANSWERS = '.copier-answers.yml'
export const REPOSITORIES = 'Repositories'
export const TEMPLATE = 'Template'
export const VERSION = 'Version'
export const VALIDATION = 'Validation'

export const valueSchema = z.union([z.string(), z.number(), z.boolean(), z.null()])
const columnSchema = z.object({
  id: z.string(),
  kind: z.enum(['answer', 'metadata', 'repository'])
})
const rowSchema = z.object({
  repository: z.string(),
  url: z.string(),
  validationFailure: z.string(),
  values: z.record(z.string(), valueSchema)
})
const snapshotSchema = z.object({
  columns: z.array(columnSchema),
  generatedAt: z.string(),
  rows: z.array(rowSchema),
  versions: z.array(z.string())
})

export type Snapshot = z.infer<typeof snapshotSchema>
export type Row = z.infer<typeof rowSchema>
export type ReportColumn = Snapshot['columns'][number]

/** What a cell holds when the row has one. */
export type Value = z.infer<typeof valueSchema>
/** What reading a cell gives you, since a row need not carry every column. */
export type CellValue = Value | undefined

export type CountedValue = {
  count: number
  value: Value
}

export const parseSnapshot = (value: unknown): Snapshot => {
  const result = z.safeParse(snapshotSchema, value)
  if (!result.success) {
    throw new Error('The Copier report has an invalid data format.', { cause: result.error })
  }
  return result.data
}

export const repositoryName = (value: string): string => value.slice(value.lastIndexOf('/') + 1)

export const isValue = (value: unknown): value is Value =>
  value === null || ['boolean', 'number', 'string'].includes(typeof value)
