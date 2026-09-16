import { createColumnHelper } from '@tanstack/react-table'
import { Link } from 'react-router'

import { DataTable, useDataTable } from '@/components/data-table/DataTable'
import type { dataTableFeatures } from '@/components/data-table/data-table-model'
import { formatDateTime } from '@/lib/format'
import { displayValue } from '@/lib/value'
import type { UpdaterFeedSummary } from '@/lib/updater-report'

const updaterOptions = (value: Record<string, unknown>) =>
  Object.entries(value)
    .filter(([, option]) => option !== null)
    .map(([name, option]) => `${name}=${JSON.stringify(option)}`)
    .join(', ') || 'No options'

const helper = createColumnHelper<typeof dataTableFeatures, UpdaterFeedSummary>()
const columns = helper.columns([
  helper.accessor((feed) => feed.title ?? feed.updater, {
    cell: ({ row }) => (
      <Link to={`/updaters/${encodeURIComponent(row.original.feed_id)}`}>
        {row.original.title ?? row.original.updater}
      </Link>
    ),
    header: 'Updater',
    id: 'updater'
  }),
  helper.accessor('updater_options', {
    header: 'Options',
    id: 'options',
    cell: ({ getValue }) => updaterOptions(getValue()),
    meta: { truncate: true }
  }),
  helper.accessor('generated_at', {
    cell: ({ getValue }) => formatDateTime(new Date(getValue())) ?? displayValue(null),
    header: 'Last generated',
    id: 'generated'
  }),
  helper.accessor('dry_run', {
    cell: ({ row }) => (row.original.dry_run ? 'Yes' : 'No'),
    header: 'Dry run',
    id: 'dry-run'
  }),
  helper.accessor('summary.total', {
    header: 'Tasks',
    id: 'tasks',
    meta: { align: 'right' }
  }),
  helper.accessor('summary.updated', {
    header: 'Updated',
    id: 'updated',
    meta: { align: 'right' }
  }),
  helper.accessor(({ summary }) => summary.failures + summary.scan_failures, {
    header: 'Failures',
    id: 'failures',
    meta: { align: 'right' }
  }),
  helper.accessor('workflow_url', {
    cell: ({ getValue }) => {
      const url = getValue()
      return url != null ? (
        <a href={url} rel="noreferrer" target="_blank">
          Open run
        </a>
      ) : (
        displayValue(url)
      )
    },
    header: 'Workflow',
    id: 'workflow'
  })
])

export const UpdaterOverviewTable = ({ feeds }: { feeds: UpdaterFeedSummary[] }) => {
  const table = useDataTable<UpdaterFeedSummary>({
    columns,
    getRowId: ({ feed_id }) => feed_id,
    rows: feeds
  })

  return (
    <DataTable
      className="max-h-none rounded-lg bg-white"
      emptyMessage="No updater reports yet."
      label="Updater runs"
      table={table}
    />
  )
}
