import { DashboardHeader, PieChartsSection, RepositoriesSection } from './DashboardContent'
import { DashboardFilters } from './DashboardFilters'
import { DashboardSidebar } from './DashboardSidebar'
import type { DashboardSnapshot } from './dashboard'
import { useCopierDashboard } from './useCopierDashboard'

export default function CopierDashboard({ snapshot }: { snapshot: DashboardSnapshot }) {
  const dashboard = useCopierDashboard(snapshot)

  return (
    <main>
      <DashboardHeader generatedAt={dashboard.generatedAt} repositoryCount={dashboard.repositoryCount} />

      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-4 lg:gap-6">
        <DashboardSidebar
          className="lg:col-span-1"
          filterFields={dashboard.filterFields}
          filterInputs={<DashboardFilters filters={dashboard.filters} />}
          onReset={dashboard.onReset}
          pieCharts={dashboard.pieCharts}
          tableColumns={dashboard.tableColumns}
        />

        <div className="min-w-0 lg:col-span-3">
          <RepositoriesSection {...dashboard.repositories} />
          <PieChartsSection charts={dashboard.charts} />
        </div>
      </div>
    </main>
  )
}
