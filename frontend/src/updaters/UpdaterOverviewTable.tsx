import { createColumnHelper } from '@tanstack/react-table'
import { Link } from 'react-router'

import { DataTable, useDataTable } from '@/components/data-table/DataTable'
import type { dataTableFeatures } from '@/components/data-table/data-table-model'
import { formatDateTime } from '@/lib/date'
import { displayValue } from '@/lib/value'
import type { UpdaterFeedSummary } from './updater-report'

function updaterOptions(value: Record<string, unknown>) {
  return (
    Object.entries(value)
      .filter(([, option]) => option != null)
      .map(([name, option]) => `${name}=${JSON.stringify(option)}`)
      .join(', ') || 'No options'
  )
}

const updaterColumn = createColumnHelper<typeof dataTableFeatures, UpdaterFeedSummary>()
const UPDATER_COLUMNS = updaterColumn.columns([
  updaterColumn.accessor((feed) => feed.title ?? feed.updater, {
    cell: ({ row }) => (
      <Link to={`/updaters/${encodeURIComponent(row.original.feed_id)}`}>
        {row.original.title ?? row.original.updater}
      </Link>
    ),
    header: 'Updater',
    id: 'updater'
  }),
  updaterColumn.accessor(({ updater_options }) => updaterOptions(updater_options), {
    header: 'Options',
    id: 'options',
    meta: { truncate: true }
  }),
  updaterColumn.accessor(({ generated_at }) => new Date(generated_at), {
    cell: ({ getValue }) => formatDateTime(getValue()) ?? displayValue(null),
    header: 'Last generated',
    id: 'generated'
  }),
  updaterColumn.accessor(({ dry_run }) => dry_run, {
    cell: ({ row }) => (row.original.dry_run ? 'Yes' : 'No'),
    header: 'Dry run',
    id: 'dry-run'
  }),
  updaterColumn.accessor(({ summary }) => summary.total, {
    header: 'Tasks',
    id: 'tasks',
    meta: { align: 'right' }
  }),
  updaterColumn.accessor(({ summary }) => summary.updated, {
    header: 'Updated',
    id: 'updated',
    meta: { align: 'right' }
  }),
  updaterColumn.accessor(({ summary }) => summary.failures + summary.scan_failures, {
    header: 'Failures',
    id: 'failures',
    meta: { align: 'right' }
  }),
  updaterColumn.accessor(({ workflow_url }) => workflow_url, {
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

export function UpdaterOverviewTable({ feeds }: { feeds: UpdaterFeedSummary[] }) {
  const table = useDataTable<UpdaterFeedSummary>({
    className: 'max-h-none rounded-lg bg-white',
    columns: UPDATER_COLUMNS,
    emptyMessage: 'No updater reports yet.',
    getRowId: ({ feed_id }) => feed_id,
    label: 'Updater runs',
    rows: feeds
  })

  return <DataTable model={table} />
}
