import { useMemo, useState } from 'react'

import { DashboardSection } from '@/components/dashboard/DashboardSection'
import { DataTable, useDataTable } from '@/components/data-table/DataTable'
import { Button } from '@/components/ui/Button'
import { Dialog, DialogClose, DialogContent, DialogTitle } from '@/components/ui/Dialog'
import { displayValue } from '@/lib/value'
import type { UpdaterReportFailure, UpdaterReportResult } from '@/lib/updater-report'
import { createColumnHelper } from '@tanstack/react-table'
import type { DataTableColumnDefinition, dataTableFeatures } from '@/components/data-table/data-table-model'

type ReportFailure = UpdaterReportFailure | UpdaterReportResult

type FailureItem = {
  details: string | undefined
  message: string
  repository: string
  repositoryUrl: string
  target: { label: string; url: string | undefined } | null
}

const toFailureItem = (failure: ReportFailure): FailureItem => {
  const target =
    'target' in failure && failure.target != null ? { label: failure.target, url: failure.target_url } : null
  return {
    details: failure.details,
    message: failure.message ?? 'No error message',
    repository: failure.repository,
    repositoryUrl: failure.url,
    target
  }
}

const TargetValue = ({ target }: { target: FailureItem['target'] }) => {
  if (target == null) return displayValue(null)
  return target.url != null ? (
    <a href={target.url} rel="noreferrer" target="_blank">
      {target.label}
    </a>
  ) : (
    target.label
  )
}

const createColumns = (onSelect: (failureId: string) => void) => {
  const helper = createColumnHelper<typeof dataTableFeatures, FailureItem>()
  const columns = [
    helper.display({
      header: 'Repository',
      id: 'repository',
      meta: { truncate: true },
      cell: ({ row }) => {
        const { repository, repositoryUrl } = row.original
        return (
          <a href={repositoryUrl} rel="noreferrer" target="_blank">
            {repository}
          </a>
        )
      }
    }),
    // TODO: figure out why `.accessor` isn't working, gives out a weird type error
    helper.display({
      header: 'Target',
      id: 'target',
      meta: { truncate: true },
      cell: ({ row }) => <TargetValue target={row.original.target} />
    }),
    helper.display({
      header: 'Message',
      id: 'message',
      meta: { truncate: true },
      cell: ({ row }) => row.original.message
    }),
    helper.display({
      enableSorting: false,
      header: 'Details',
      id: 'details',
      cell: ({ row }) => {
        const { repository, target } = row.original
        return (
          <Button
            aria-label={`View failure details for ${repository}${target ? `, ${target.label}` : ''}`}
            onClick={() => onSelect(row.id)}
            type="button"
            variant="secondary"
          >
            Details
          </Button>
        )
      }
    })
  ] satisfies DataTableColumnDefinition<FailureItem>[]

  return columns
}

type FailureTableProps = {
  failures: FailureItem[]
  onSelect: (failureId: string) => void
  title: string
}

const failureId = (failure: FailureItem, index: number) =>
  `${failure.repositoryUrl}-${failure.target?.label ?? ''}-${index}`

const FailureTable = ({ failures, onSelect, title }: FailureTableProps) => {
  const cols = useMemo(() => createColumns(onSelect), [onSelect])
  const table = useDataTable<FailureItem>({
    columns: cols,
    getRowId: failureId,
    rows: failures
  })

  return <DataTable className="max-h-112" emptyMessage="No failures." label={title} table={table} />
}

const FailureTextBlock = ({ title, value }: { title: string; value: string }) => (
  <section className="mt-4">
    <h3 className="mb-2 font-semibold">{title}</h3>
    <pre className="max-h-88 overflow-auto bg-muted p-3 wrap-anywhere whitespace-pre-wrap">{value}</pre>
  </section>
)

const FailureDialogContent = ({ failure }: { failure: FailureItem }) => (
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
)
export const FailureSection = ({ failures, title }: { failures: ReportFailure[]; title: string }) => {
  const [failureToDisplay, setFailureToDisplay] = useState<FailureItem | null>(null)
  const failureItems = useMemo(() => failures.map(toFailureItem), [failures])

  const showFailure = (id: string) => {
    setFailureToDisplay(failureItems.find((item, index) => id === failureId(item, index)) ?? null)
  }

  const onOpenChange = (open: boolean) => {
    if (!open) {
      setFailureToDisplay(null)
    }
  }

  if (failures.length === 0) return null
  return (
    <DashboardSection heading={`${title} (${failures.length})`}>
      <FailureTable failures={failureItems} onSelect={showFailure} title={title} />

      <Dialog onOpenChange={onOpenChange} open={failureToDisplay != null}>
        <DialogContent className="max-w-4xl">
          {failureToDisplay && <FailureDialogContent failure={failureToDisplay} />}
        </DialogContent>
      </Dialog>
    </DashboardSection>
  )
}
