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

      <div className="grid grid-cols-1 items-start gap-4 min-[1101px]:grid-cols-[minmax(20rem,22rem)_minmax(0,1fr)] min-[1101px]:gap-6">
        <DashboardSidebar
          filterFields={dashboard.filterFields}
          filterInputs={<DashboardFilters filters={dashboard.filters} {...dashboard.filterActions} />}
          onReset={dashboard.onReset}
          pieCharts={dashboard.pieCharts}
          tableColumns={dashboard.tableColumns}
        />

        <div className="min-w-0">
          <RepositoriesSection {...dashboard.repositories} />
          <PieChartsSection charts={dashboard.charts} />
        </div>
      </div>
    </main>
  )
}
