import type { FromSchema } from 'json-schema-to-ts'

import { updaterIndexSchema, updaterReportSchema } from '@/generated/frontend-contracts'

import { contractValidator, parseContract } from './contract-validation'

export type UpdaterReportSnapshot = FromSchema<typeof updaterReportSchema>
type UpdaterIndex = FromSchema<typeof updaterIndexSchema>
export type UpdaterFeedSummary = UpdaterIndex['feeds'][number]
export type UpdaterReportResult = UpdaterReportSnapshot['results'][number]
export type UpdaterReportFailure = UpdaterReportSnapshot['scan_failures'][number]
export type UpdateStatus = UpdaterReportResult['status']

const validateUpdaterReport = contractValidator.compile<UpdaterReportSnapshot>(updaterReportSchema)
const validateUpdaterIndex = contractValidator.compile<UpdaterIndex>(updaterIndexSchema)

export const parseUpdaterReport = (value: unknown, path: string): UpdaterReportSnapshot =>
  parseContract(validateUpdaterReport, value, `The updater report at ${path} has an invalid data format.`)

export const parseUpdaterIndex = (value: unknown, path: string): UpdaterIndex =>
  parseContract(validateUpdaterIndex, value, `The updater report index at ${path} has an invalid data format.`)
