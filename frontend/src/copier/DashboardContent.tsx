import { useState } from 'react'

import { cn } from '@/lib/utils'

import type { DataTableSort } from '../components/DataTable'
import { ChevronIcon } from '../components/ChevronIcon'
import { Button } from '../components/ui/button'
import { formatDateTime } from '../lib/date'
import { PieChart } from './Charts'
import { CopyableRepositoryList } from './CopyableRepositoryList'
import { RepositoryTable } from './RepositoryTable'
import type { CountedValue, DashboardRow, FilterValue } from './dashboard'

type PieChartData = {
  column: string
  data: CountedValue[]
  domain: FilterValue[]
}

function snapshotDate(value: string) {
  return formatDateTime(value, { timeZone: 'UTC' }) ?? 'Unknown snapshot date'
}

export function DashboardHeader({ generatedAt, repositoryCount }: { generatedAt: string; repositoryCount: number }) {
  return (
    <header className="mb-4 [&>p]:text-muted-foreground">
      <h1>Copier Dashboard</h1>
      <p>Compare Copier templates, versions, and answers across repositories.</p>
      <p className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
        <span>
          <strong className="text-foreground">{repositoryCount}</strong> repositories
        </span>
        <span>Updated {snapshotDate(generatedAt)}</span>
      </p>
    </header>
  )
}

export function RepositoriesSection({
  columns,
  onSelectionChange,
  onSortChange,
  repositoryNames,
  rows,
  sort
}: {
  columns: string[]
  onSelectionChange: (rows: DashboardRow[]) => void
  onSortChange: (sort: DataTableSort | null) => void
  repositoryNames: string[]
  rows: DashboardRow[]
  sort: DataTableSort | null
}) {
  const [showRepositoryNames, setShowRepositoryNames] = useState(false)
  return (
    <section
      aria-labelledby="repositories-heading"
      className="border-t border-border py-6 first:border-t-0 first:pt-4 max-[1100px]:first:pt-0 [&>h2]:mt-0 [&>h2]:mb-2"
    >
      <h2 id="repositories-heading">Repositories</h2>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <p aria-live="polite" className="m-0 text-sm text-muted-foreground">
          <strong>{rows.length}</strong> matching repositories · <strong>{repositoryNames.length}</strong> selected for
          copying
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
          <div className="mt-3 grid gap-4 min-[801px]:grid-cols-2">
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
      <p className="text-sm text-muted-foreground">
        Use the filters in the sidebar to narrow the table. Select a column heading to sort.
      </p>
      <RepositoryTable
        columns={columns}
        onSelectionChange={onSelectionChange}
        onSortChange={onSortChange}
        rows={rows}
        sort={sort}
      />
    </section>
  )
}

export function PieChartsSection({ charts }: { charts: PieChartData[] }) {
  const [expandedChart, setExpandedChart] = useState<string | null>(null)
  if (charts.length === 0) return null

  return (
    <section
      aria-labelledby="pie-charts-heading"
      className="border-t border-border py-6 first:border-t-0 first:pt-4 max-[1100px]:first:pt-0 [&>h2]:mt-0 [&>h2]:mb-2"
    >
      <h2 id="pie-charts-heading">Pie charts</h2>
      <p className="text-sm text-muted-foreground">
        Contents of the selected fields across the currently matching repositories.
      </p>
      <div className="mt-3 grid grid-cols-[repeat(auto-fit,minmax(min(100%,20rem),1fr))] gap-3">
        {charts.map(({ column, data, domain }) => {
          const expanded = expandedChart === column
          return (
            <div
              className={cn('min-w-0 rounded-medium border border-border bg-white p-3', expanded && 'col-span-full')}
              key={column}
            >
              <div className="mb-3 flex items-baseline justify-between gap-3">
                <h3 className="m-0 min-w-0 text-sm [overflow-wrap:anywhere]">
                  <code>{column}</code>
                </h3>
                <Button
                  aria-expanded={expanded}
                  className="flex-none"
                  onClick={() => setExpandedChart(expanded ? null : column)}
                  type="button"
                  variant="link"
                >
                  {expanded ? 'Show smaller' : 'Show larger'}
                </Button>
              </div>
              <PieChart column={column} data={data} domain={domain} expanded={expanded} />
            </div>
          )
        })}
      </div>
    </section>
  )
}
