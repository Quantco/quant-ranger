import { useState } from 'react'

import { cn } from '@/lib/class-merge'

import { ChevronIcon } from '@/components/ui/ChevronIcon'
import { DashboardSection } from '@/components/dashboard/DashboardSection'
import { DataTable, type DataTableModel } from '@/components/data-table/DataTable'
import { Button } from '@/components/ui/Button'
import { formatDateTime } from '@/lib/date'
import { PieChart } from './Charts'
import { CopyableRepositoryList } from './CopyableRepositoryList'
import type { DashboardChart } from './dashboard-analytics'
import type { DashboardRow } from './dashboard'

function snapshotDate(value: string) {
  return formatDateTime(value, { timeZone: 'UTC' }) ?? 'Unknown snapshot date'
}

export function DashboardHeader({ generatedAt, repositoryCount }: { generatedAt: string; repositoryCount: number }) {
  return (
    <header className="mb-4">
      <h1>Copier Dashboard</h1>
      <p className="text-muted-foreground">Compare Copier templates, versions, and answers across repositories.</p>
      <p className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
        <span>
          <strong className="text-foreground">{repositoryCount}</strong> repositories
        </span>
        <span>Updated {snapshotDate(generatedAt)}</span>
      </p>
    </header>
  )
}

function RepositoryCopyPanel({
  matchingRepositoryCount,
  repositoryNames
}: {
  matchingRepositoryCount: number
  repositoryNames: string[]
}) {
  const [showRepositoryNames, setShowRepositoryNames] = useState(false)

  return (
    <>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <p aria-live="polite" className="m-0 text-sm text-muted-foreground">
          <strong>{matchingRepositoryCount}</strong> matching repositories · <strong>{repositoryNames.length}</strong>{' '}
          selected for copying
        </p>
        <Button
          aria-expanded={showRepositoryNames}
          className="group min-h-8 gap-2 p-0 text-sm text-primary hover:bg-transparent"
          onClick={() => setShowRepositoryNames((visible) => !visible)}
          type="button"
          variant="ghost"
        >
          <ChevronIcon className="group-hover:text-foreground group-hover:opacity-100 group-aria-expanded:rotate-90" />
          <span>Copy repository names ({repositoryNames.length})</span>
        </Button>
      </div>
      {showRepositoryNames && (
        <div className="mt-2">
          <p className="text-sm text-muted-foreground">These lists contain the repository rows selected below.</p>
          <div className="mt-3 grid gap-4 md:grid-cols-2">
            <div>
              <h3>Comma-separated</h3>
              <CopyableRepositoryList label="Comma-separated" value={repositoryNames.join(',')} />
            </div>
            <div>
              <h3>Newline-separated</h3>
              <CopyableRepositoryList label="Newline-separated" value={repositoryNames.join('\n')} />
            </div>
          </div>
        </div>
      )}
    </>
  )
}

export function RepositoriesSection({
  matchingRepositoryCount,
  repositoryNames,
  table
}: {
  matchingRepositoryCount: number
  repositoryNames: string[]
  table: DataTableModel<DashboardRow>
}) {
  return (
    <DashboardSection heading="Repositories">
      <RepositoryCopyPanel matchingRepositoryCount={matchingRepositoryCount} repositoryNames={repositoryNames} />
      <p className="text-sm text-muted-foreground">
        Use the filters in the sidebar to narrow the table. Select a column heading to sort.
      </p>
      <DataTable model={table} />
    </DashboardSection>
  )
}

function PieChartCard({
  chart: { column, data, domain },
  expanded,
  onToggle
}: {
  chart: DashboardChart
  expanded: boolean
  onToggle: () => void
}) {
  return (
    <div className={cn('min-w-0 rounded-lg border border-border bg-white p-3', expanded && 'col-span-full')}>
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h3 className="m-0 min-w-0 text-sm wrap-anywhere">
          {column.kind === 'answer' ? <code>{column.id}</code> : column.id}
        </h3>
        <Button aria-expanded={expanded} className="flex-none" onClick={onToggle} type="button" variant="link">
          {expanded ? 'Show smaller' : 'Show larger'}
        </Button>
      </div>
      <PieChart column={column} data={data} domain={domain} expanded={expanded} />
    </div>
  )
}

export function PieChartsSection({ charts }: { charts: DashboardChart[] }) {
  const [expandedChart, setExpandedChart] = useState<string | null>(null)
  if (charts.length === 0) return null

  return (
    <DashboardSection heading="Pie charts">
      <p className="text-sm text-muted-foreground">
        Contents of the selected fields across the currently matching repositories.
      </p>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        {charts.map((chart) => {
          const expanded = expandedChart === chart.column.id
          return (
            <PieChartCard
              chart={chart}
              expanded={expanded}
              key={chart.column.id}
              onToggle={() => setExpandedChart(expanded ? null : chart.column.id)}
            />
          )
        })}
      </div>
    </DashboardSection>
  )
}
