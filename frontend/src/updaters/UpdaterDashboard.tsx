import { cn } from '@/lib/utils'

import { DashboardSection } from '../components/DashboardSection'
import { DataTable } from '../components/DataTable'
import { formatDateTime } from '../lib/date'
import { FailureSection } from './FailureSection'
import { PullRequestDataPanel } from './PullRequestDataPanel'
import { UpdaterSidebar } from './UpdaterSidebar'
import { PullRequestQueryProvider } from './pull-request-query'
import { useUpdaterDashboardController } from './useDashboardModel'
import type { UpdaterReportSnapshot } from './updater-report'

export default function UpdaterDashboardRoute({ report }: { report: UpdaterReportSnapshot }) {
  return (
    <PullRequestQueryProvider>
      <UpdaterDashboardPage key={`${report.feed_id}:${report.github_api_url}`} report={report} />
    </PullRequestQueryProvider>
  )
}

function UpdaterDashboardPage({ report }: { report: UpdaterReportSnapshot }) {
  const { actions, resources, view } = useUpdaterDashboardController(report)

  return (
    <main>
      <header className="mb-4">
        <h1>{report.title ?? report.feed_id}</h1>
        <p className="text-muted-foreground">
          <strong>{report.updater}</strong> · generated {formatDateTime(report.generated_at) ?? 'unknown date'}
          {report.dry_run && ' · dry run'}
          {report.workflow_url != null && (
            <>
              {' · '}
              <a href={report.workflow_url} rel="noreferrer" target="_blank">
                Workflow run
              </a>
            </>
          )}
        </p>
      </header>

      <div className="flex flex-col items-start gap-4 lg:flex-row lg:gap-6">
        <UpdaterSidebar
          filters={view.filters}
          onFilterChange={actions.setFilter}
          onReset={actions.reset}
          onSearchChange={actions.setSearch}
          onTableColumnsChange={actions.setTableColumns}
          search={view.search}
          tableColumns={view.tableColumns}
        />

        <div className="min-w-0 flex-1">
          <DashboardSection heading="Run summary">
            <div aria-label="Run summary" className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
              {view.summaryItems.map(({ error, label, value }) => (
                <div
                  className={cn(
                    'grid rounded-md border border-border bg-primary-subtle p-3',
                    error === true && 'bg-error-subtle text-error'
                  )}
                  key={label}
                >
                  <strong className="text-2xl">{value}</strong>
                  <span className={error === true ? undefined : 'text-muted-foreground'}>{label}</span>
                </div>
              ))}
            </div>
          </DashboardSection>

          <PullRequestDataPanel githubApiUrl={report.github_api_url} model={resources.pullRequests} />

          <DashboardSection heading="Results">
            <p className="text-sm text-muted-foreground">
              {view.resultCount} of {report.results.length} results
            </p>
            <DataTable model={view.table} />
          </DashboardSection>

          <FailureSection failures={view.updaterFailures} title="Updater failures" />
          <FailureSection failures={report.scan_failures} title="Scan failures" />
        </div>
      </div>
    </main>
  )
}
