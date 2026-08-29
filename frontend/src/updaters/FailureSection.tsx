import { useMemo, useState } from 'react'

import { DashboardSection } from '../components/dashboard/DashboardSection'
import { DataTable, useDataTable, type DataTableColumn } from '../components/data-table/DataTable'
import { Button } from '../components/ui/Button'
import { Dialog, DialogClose, DialogContent, DialogTitle } from '../components/ui/Dialog'
import { displayValue } from '../lib/value'
import type { UpdaterReportFailure, UpdaterReportResult } from './updater-report'

type ReportFailure = UpdaterReportFailure | UpdaterReportResult

interface FailureItem {
  details: string | undefined
  message: string
  repository: string
  repositoryUrl: string
  target: { label: string; url: string | undefined } | null
}

const NO_ERROR_MESSAGE = 'No error message'

function toFailureItem(failure: ReportFailure): FailureItem {
  const target =
    'target' in failure && failure.target != null ? { label: failure.target, url: failure.target_url } : null
  return {
    details: failure.details,
    message: failure.message ?? NO_ERROR_MESSAGE,
    repository: failure.repository,
    repositoryUrl: failure.url,
    target
  }
}

function TargetValue({ target }: { target: FailureItem['target'] }) {
  if (target == null) return displayValue(null)
  return target.url != null ? (
    <a href={target.url} rel="noreferrer" target="_blank">
      {target.label}
    </a>
  ) : (
    target.label
  )
}

function createFailureColumns(onSelect: (failure: FailureItem) => void): DataTableColumn<FailureItem>[] {
  return [
    {
      accessorFn: (failure) => failure.repository,
      cell: ({ row }) => (
        <a href={row.original.repositoryUrl} rel="noreferrer" target="_blank">
          {row.original.repository}
        </a>
      ),
      header: 'Repository',
      id: 'repository',
      meta: { truncate: true }
    },
    {
      accessorFn: (failure) => failure.target?.label ?? undefined,
      cell: ({ row }) => <TargetValue target={row.original.target} />,
      header: 'Target',
      id: 'target',
      meta: { truncate: true }
    },
    {
      accessorFn: (failure) => failure.message,
      header: 'Message',
      id: 'message',
      meta: { truncate: true }
    },
    {
      accessorFn: () => undefined,
      cell: ({ row }) => (
        <Button
          aria-label={`View failure details for ${row.original.repository}${row.original.target ? `, ${row.original.target.label}` : ''}`}
          onClick={() => onSelect(row.original)}
          type="button"
          variant="secondary"
        >
          Details
        </Button>
      ),
      enableSorting: false,
      header: 'Details',
      id: 'details'
    }
  ]
}

function FailureTable({
  failures,
  onSelect,
  title
}: {
  failures: FailureItem[]
  onSelect: (failure: FailureItem) => void
  title: string
}) {
  const columns = useMemo(() => createFailureColumns(onSelect), [onSelect])
  const table = useDataTable<FailureItem>({
    className: 'max-h-112',
    columns,
    emptyMessage: 'No failures.',
    getRowId: (failure, index) => `${failure.repositoryUrl}\0${failure.target?.label ?? ''}\0${index}`,
    label: title,
    rows: failures
  })

  return <DataTable model={table} />
}

function FailureTextBlock({ title, value }: { title: string; value: string }) {
  return (
    <section className="mt-4">
      <h3 className="mb-2 font-semibold">{title}</h3>
      <pre className="max-h-88 overflow-auto bg-muted p-3 wrap-anywhere whitespace-pre-wrap">{value}</pre>
    </section>
  )
}

function FailureDialog({ failure, onClose }: { failure: FailureItem | null; onClose: () => void }) {
  return (
    <Dialog
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
      open={failure != null}
    >
      <DialogContent className="max-w-4xl">
        {failure && (
          <>
            <DialogTitle>Failure details</DialogTitle>
            <p>
              <a href={failure.repositoryUrl} rel="noreferrer" target="_blank">
                {failure.repository}
              </a>
              {failure.target != null && (
                <>
                  {' · '}
                  <TargetValue target={failure.target} />
                </>
              )}
            </p>
            <FailureTextBlock title="Message" value={failure.message} />
            {failure.details != null && <FailureTextBlock title="Diagnostics" value={failure.details} />}
            <div className="mt-4 flex justify-end">
              <DialogClose render={<Button />}>Close</DialogClose>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}

export function FailureSection({ failures, title }: { failures: ReportFailure[]; title: string }) {
  const [selectedFailure, setSelectedFailure] = useState<FailureItem | null>(null)
  const failureItems = useMemo(() => failures.map(toFailureItem), [failures])

  if (failures.length === 0) return null
  return (
    <DashboardSection heading={`${title} (${failures.length})`}>
      <FailureTable failures={failureItems} onSelect={setSelectedFailure} title={title} />
      <FailureDialog failure={selectedFailure} onClose={() => setSelectedFailure(null)} />
    </DashboardSection>
  )
}
