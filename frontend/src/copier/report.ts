import type { FromSchema } from 'json-schema-to-ts'

import { copierDashboardSchema } from '@/generated/frontend-contracts'
import { contractValidator, parseContract } from '@/lib/contract-validation'

export const COPIER_ANSWERS = '.copier-answers.yml'
export const REPOSITORIES = 'Repositories'
export const TEMPLATE = 'Template'
export const VERSION = 'Version'
export const VALIDATION = 'Validation'

export type Snapshot = FromSchema<typeof copierDashboardSchema>
export type Row = Snapshot['rows'][number]
export type ReportColumn = Snapshot['columns'][number]

/** What a cell holds when the row has one. */
export type Value = Row['values'][string]
/** What reading a cell gives you, since a row need not carry every column. */
export type CellValue = Value | undefined

export type CountedValue = {
  count: number
  value: Value
}

const validateSnapshot = contractValidator.compile<Snapshot>(copierDashboardSchema)

export const parseSnapshot = (value: unknown, path: string): Snapshot =>
  parseContract(validateSnapshot, value, `The Copier report at ${path} has an invalid data format.`)

export const repositoryName = (value: string): string => value.slice(value.lastIndexOf('/') + 1)

export const isValue = (value: unknown): value is Value =>
  value === null || ['boolean', 'number', 'string'].includes(typeof value)
