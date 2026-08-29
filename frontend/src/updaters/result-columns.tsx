import type { FilterFn } from '@tanstack/react-table'
import { GitMerge, GitPullRequest, GitPullRequestClosed, type LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

import type { DataTableColumn } from '../components/DataTable'
import type { dataTableFeatures } from '../components/data-table-model'
import { cn } from '../lib/utils'
import { displayValue, type DisplayValue } from '../lib/value'
import { ageColor, ageInDays, formatAge } from './pull-request-age'
import {
  getLoadedPullRequest,
  hasPullRequest,
  pullRequestKey,
  type CiStatus,
  type LivePullRequest,
  type PullRequests,
  type PullRequestState,
  type ReviewStatus
} from './pull-request'
import type { UpdaterReportResult, UpdateStatus } from './updater-report'

export interface UpdaterResultRow {
  pullRequest: LivePullRequest | undefined
  result: UpdaterReportResult
  searchText: string
}

interface FilterOption {
  label: string
  value: string
}
type UpdaterFilterFunction = FilterFn<typeof dataTableFeatures, UpdaterResultRow>
interface UpdaterFilterConfig {
  filterFunction: UpdaterFilterFunction
  label?: string
  options: (statuses: UpdateStatus[]) => FilterOption[]
  placeholder: string
}
interface UpdaterColumnDescriptor<Id extends string = string> {
  filter?: UpdaterFilterConfig
  id: Id
  label: string
  render?: (value: unknown, row: UpdaterResultRow) => ReactNode
  truncate?: boolean
  value: (row: UpdaterResultRow) => DisplayValue
}

const selectionFilter: UpdaterFilterFunction = (row, columnId, selected: string[]) =>
  selected.includes(String(row.getValue(columnId)))
selectionFilter.autoRemove = (selected: string[]) => selected.length === 0

const pullRequestStateFilter: UpdaterFilterFunction = (row, columnId, selected: string[]) => {
  if (!hasPullRequest(row.original.result)) return selected.includes('none')
  return selected.includes(String(row.getValue(columnId) ?? 'unknown'))
}
pullRequestStateFilter.autoRemove = selectionFilter.autoRemove

const liveSelectionFilter: UpdaterFilterFunction = (row, columnId, selected: string[]) => {
  if (!hasPullRequest(row.original.result)) return false
  const value = row.getValue<DisplayValue>(columnId)
  return selected.includes(
    value == null ? 'unknown' : typeof value === 'boolean' ? (value ? 'yes' : 'no') : String(value)
  )
}
liveSelectionFilter.autoRemove = selectionFilter.autoRemove

const ageFilter: UpdaterFilterFunction = (row, columnId, selected: string[]) => {
  const value = row.getValue<DisplayValue>(columnId)
  if (!(value instanceof Date)) return false
  const days = ageInDays(value)
  if (days == null) return false
  const age = days < 7 ? 'week' : days < 30 ? 'month' : days < 90 ? 'quarter' : 'older'
  return selected.includes(age)
}
ageFilter.autoRemove = selectionFilter.autoRemove

const updaterResultColumnDefinitions = [
  {
    filter: {
      filterFunction: pullRequestStateFilter,
      label: 'PR status',
      options: () => [
        option('open', 'Open'),
        option('merged', 'Merged'),
        option('closed', 'Closed'),
        option('unknown', 'Not loaded'),
        option('none', 'No pull request')
      ],
      placeholder: 'All statuses'
    },
    id: 'pr-status',
    label: 'Pull request',
    render: (value: unknown, { result }: UpdaterResultRow) => (
      <PullRequestStatus number={result.pull_request} state={pullRequestState(value)} url={result.pull_request_url} />
    ),
    value: ({ pullRequest, result }: UpdaterResultRow) =>
      pullRequest?.state ?? (result.pull_request == null ? null : 'unknown')
  },
  {
    filter: {
      filterFunction: ageFilter,
      options: () => [
        option('week', 'Less than 7 days'),
        option('month', '7–29 days'),
        option('quarter', '30–89 days'),
        option('older', '90 days or more')
      ],
      placeholder: 'Any age'
    },
    id: 'created',
    label: 'Created',
    render: (value: unknown) => <DateBadge value={value} variant="age" />,
    value: ({ pullRequest }: UpdaterResultRow) => (pullRequest ? new Date(pullRequest.createdAt) : null)
  },
  {
    id: 'last-update',
    label: 'Last update',
    render: (value: unknown) => <DateBadge value={value} variant="timestamp" />,
    value: ({ pullRequest }: UpdaterResultRow) => (pullRequest ? new Date(pullRequest.updatedAt) : null)
  },
  {
    id: 'repository',
    label: 'Repository',
    render: (_: unknown, { result }: UpdaterResultRow) => (
      <a href={result.url} rel="noreferrer" target="_blank">
        {result.repository}
      </a>
    ),
    truncate: true,
    value: ({ result }: UpdaterResultRow) => result.repository
  },
  {
    id: 'target',
    label: 'Target',
    render: (value: unknown, { result }: UpdaterResultRow) =>
      result.target_url != null && typeof value === 'string' ? (
        <a href={result.target_url} rel="noreferrer" target="_blank">
          {value}
        </a>
      ) : (
        displayValue(value)
      ),
    truncate: true,
    value: ({ result }: UpdaterResultRow) => result.target
  },
  {
    filter: {
      filterFunction: selectionFilter,
      options: (statuses: UpdateStatus[]) => statuses.map((status) => option(status, status)),
      placeholder: 'All results'
    },
    id: 'result',
    label: 'Result',
    value: ({ result }: UpdaterResultRow) => result.status
  },
  {
    filter: {
      filterFunction: liveSelectionFilter,
      options: () => yesNoOptions('Not loaded / not applicable'),
      placeholder: 'All'
    },
    id: 'merge-conflicts',
    label: 'Merge conflicts',
    render: (value: unknown) => <ProblemFlagBadge value={value} />,
    value: ({ pullRequest }: UpdaterResultRow) => pullRequest?.hasMergeConflicts
  },
  {
    filter: {
      filterFunction: liveSelectionFilter,
      options: () => [
        option('success', 'Success'),
        option('failure', 'Failure'),
        option('pending', 'Pending'),
        option('none', 'No checks'),
        option('unknown', 'Not loaded / not applicable')
      ],
      placeholder: 'All statuses'
    },
    id: 'ci-status',
    label: 'CI',
    render: (value: unknown) => <StatusBadge value={value} />,
    value: ({ pullRequest }: UpdaterResultRow) => pullRequest?.ciStatus
  },
  {
    filter: {
      filterFunction: liveSelectionFilter,
      options: () => [
        option('approved', 'Approved'),
        option('changes-requested', 'Changes requested'),
        option('pending', 'Review requested'),
        option('none', 'No approval decision'),
        option('unknown', 'Not loaded / not applicable')
      ],
      placeholder: 'All statuses'
    },
    id: 'review-status',
    label: 'Approval',
    render: (value: unknown) => <StatusBadge value={value} />,
    value: ({ pullRequest }: UpdaterResultRow) => pullRequest?.reviewStatus
  },
  {
    id: 'comments',
    label: 'Comments',
    value: ({ pullRequest }: UpdaterResultRow) => pullRequest?.comments
  },
  {
    filter: {
      filterFunction: liveSelectionFilter,
      options: () => yesNoOptions('Not loaded'),
      placeholder: 'All'
    },
    id: 'manual-commits',
    label: 'Non-quant-ranger commits',
    render: (value: unknown) => <ProblemFlagBadge value={value} />,
    value: ({ pullRequest }: UpdaterResultRow) => pullRequest?.hasNonQuantRangerCommits
  },
  {
    id: 'reviewers',
    label: 'Reviewers',
    render: (_: unknown, { pullRequest }: UpdaterResultRow) => {
      const reviewers = pullRequest?.reviewers ?? []
      return reviewers.length ? (
        <>
          {reviewers.slice(0, 3).map(({ label, url }, index) => (
            <a className={index > 0 ? 'ml-2' : undefined} href={url} key={url} rel="noreferrer" target="_blank">
              {label}
            </a>
          ))}
          {reviewers.length > 3 && ` +${reviewers.length - 3}`}
        </>
      ) : (
        displayValue(null)
      )
    },
    truncate: true,
    value: ({ pullRequest }: UpdaterResultRow) => pullRequest?.reviewers.map(({ label }) => label).join(', ')
  }
] as const satisfies readonly UpdaterColumnDescriptor[]

export type UpdaterResultColumnId = (typeof updaterResultColumnDefinitions)[number]['id']

const updaterResultColumnRegistry: readonly UpdaterColumnDescriptor<UpdaterResultColumnId>[] =
  updaterResultColumnDefinitions
export const UPDATER_REPOSITORY_COLUMN: UpdaterResultColumnId = 'repository'
export const UPDATER_RESULT_COLUMN_IDS: UpdaterResultColumnId[] = updaterResultColumnDefinitions.map(({ id }) => id)

export interface UpdaterFilterDefinition {
  column: UpdaterResultColumnId
  label: string
  options: FilterOption[]
  placeholder: string
}

export const updaterSearchFilter: UpdaterFilterFunction = (row, _columnId, query: string) =>
  row.original.searchText.includes(query.trim().toLocaleLowerCase())
updaterSearchFilter.autoRemove = (query: string) => query.trim() === ''

export const updaterResultColumns: DataTableColumn<UpdaterResultRow>[] = updaterResultColumnRegistry.map(
  ({ filter, id, label, render, truncate, value }) => ({
    accessorFn: (row) => normalizeValue(value(row)),
    ...(render == null ? {} : { cell: ({ getValue, row }) => render(getValue(), row.original) }),
    enableColumnFilter: filter != null,
    enableGlobalFilter: id === UPDATER_REPOSITORY_COLUMN,
    enableHiding: id !== UPDATER_REPOSITORY_COLUMN,
    ...(filter == null ? {} : { filterFn: filter.filterFunction }),
    header: label,
    id,
    meta: truncate == null ? {} : { truncate },
    sortUndefined: 'last'
  })
)

export function buildUpdaterFilterDefinitions(statuses: UpdateStatus[]): UpdaterFilterDefinition[] {
  return updaterResultColumnRegistry.flatMap(({ filter, id, label }) =>
    filter == null
      ? []
      : [
          {
            column: id,
            label: filter.label ?? label,
            options: filter.options(statuses),
            placeholder: filter.placeholder
          }
        ]
  )
}

export function buildUpdaterResultRows(results: UpdaterReportResult[], pullRequests: PullRequests): UpdaterResultRow[] {
  return results.map((result) => {
    const pullRequest = hasPullRequest(result) ? getLoadedPullRequest(pullRequests[pullRequestKey(result)]) : undefined
    return { pullRequest, result, searchText: buildSearchText(result, pullRequest) }
  })
}

export function updaterResultColumnLabel(columnId: string): string {
  return updaterResultColumnRegistry.find(({ id }) => id === columnId)?.label ?? columnId
}

function buildSearchText(result: UpdaterReportResult, pullRequest: LivePullRequest | undefined): string {
  return [
    result.repository,
    result.target,
    result.message,
    result.pull_request,
    pullRequest?.title,
    pullRequest?.reviewers.map(({ label }) => label).join(' ')
  ]
    .filter((value) => value != null)
    .join('\n')
    .toLocaleLowerCase()
}

function normalizeValue(value: DisplayValue): DisplayValue {
  return value == null || value === '' || (value instanceof Date && Number.isNaN(value.valueOf())) ? undefined : value
}

function yesNoOptions(unknownLabel: string): FilterOption[] {
  return [option('yes', 'Yes'), option('no', 'No'), option('unknown', unknownLabel)]
}

function option(value: string, label: string): FilterOption {
  return { label, value }
}

function pullRequestState(value: unknown): PullRequestState | 'unknown' | null {
  return value === 'closed' || value === 'merged' || value === 'open' || value === 'unknown' ? value : null
}

type ReportState = CiStatus | ReviewStatus
const PULL_REQUEST_ICONS = {
  closed: GitPullRequestClosed,
  merged: GitMerge,
  open: GitPullRequest
} satisfies Record<PullRequestState, LucideIcon>
const PULL_REQUEST_STATE_CLASSES = {
  closed: 'text-pr-closed',
  merged: 'text-pr-merged',
  open: 'text-pr-open',
  unknown: 'text-muted-foreground'
} satisfies Record<PullRequestState | 'unknown', string>
const REPORT_STATE_CLASSES = {
  approved: 'bg-success-subtle text-success',
  'changes-requested': 'bg-error-subtle text-error',
  failure: 'bg-error-subtle text-error',
  none: undefined,
  pending: 'bg-warning-subtle text-warning',
  success: 'bg-success-subtle text-success'
} satisfies Record<ReportState, string | undefined>
const REPORT_VALUE_CLASS = 'inline-block min-w-10 rounded-sm px-1.5 py-0.5 text-center'

function PullRequestStatus({
  number,
  state,
  url
}: {
  number: number | null | undefined
  state: PullRequestState | 'unknown' | null
  url: string | undefined
}) {
  if (number == null) return displayValue(number)
  const displayState = state ?? 'unknown'
  const label =
    displayState === 'unknown'
      ? 'Pull request status not loaded'
      : `${displayState.charAt(0).toUpperCase()}${displayState.slice(1)} pull request`
  const className = cn(
    'inline-flex items-center gap-1 font-semibold whitespace-nowrap',
    PULL_REQUEST_STATE_CLASSES[displayState]
  )
  const Icon = displayState === 'unknown' ? GitPullRequest : PULL_REQUEST_ICONS[displayState]
  const content = (
    <>
      <Icon aria-hidden className="size-4 shrink-0" />#{number}
    </>
  )
  return url != null ? (
    <a
      aria-label={`${label} #${number}`}
      className={className}
      href={url}
      rel="noreferrer"
      target="_blank"
      title={label}
    >
      {content}
    </a>
  ) : (
    <span className={className} title={label}>
      {content}
    </span>
  )
}

function DateBadge({ value, variant }: { value: unknown; variant: 'age' | 'timestamp' }) {
  if (!(value instanceof Date) || Number.isNaN(value.getTime())) return displayValue(value)
  return (
    <span className={REPORT_VALUE_CLASS} style={{ background: ageColor(value) }} title={value.toISOString()}>
      {variant === 'timestamp' ? `${value.toISOString().slice(0, 16).replace('T', ' ')} UTC` : formatAge(value)}
    </span>
  )
}

function ProblemFlagBadge({ value }: { value: unknown }) {
  if (typeof value !== 'boolean') return displayValue(value)
  return (
    <span className={cn(REPORT_VALUE_CLASS, value ? 'bg-error-subtle text-error' : 'bg-success-subtle text-success')}>
      {value ? 'Yes' : 'No'}
    </span>
  )
}

function StatusBadge({ value }: { value: unknown }) {
  if (typeof value !== 'string') return displayValue(value)
  return (
    <span
      className={cn(
        REPORT_VALUE_CLASS,
        'bg-muted whitespace-nowrap text-muted-foreground capitalize',
        isReportState(value) && REPORT_STATE_CLASSES[value]
      )}
    >
      {value.replaceAll('-', ' ')}
    </span>
  )
}

function isReportState(value: string): value is ReportState {
  return Object.hasOwn(REPORT_STATE_CLASSES, value)
}
