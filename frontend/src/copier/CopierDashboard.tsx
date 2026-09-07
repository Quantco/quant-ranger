import { DashboardHeader, PieChartsSection, RepositoriesSection } from './DashboardContent'
import { DashboardFilters } from './DashboardFilters'
import { DashboardSidebar } from './DashboardSidebar'
import type { DashboardSnapshot } from './dashboard'
import { useCopierDashboardController } from './useCopierDashboard'

export default function CopierDashboard({ snapshot }: { snapshot: DashboardSnapshot }) {
  const { actions, view } = useCopierDashboardController(snapshot)

  return (
    <main>
      <DashboardHeader generatedAt={view.generatedAt} repositoryCount={view.repositoryCount} />

      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-4 lg:gap-6">
        <DashboardSidebar
          className="lg:col-span-1"
          filterFields={{ ...view.filterFields, onChange: actions.setFilterColumns }}
          filterInputs={<DashboardFilters filters={view.filters} onChange={actions.setFilter} />}
          onReset={actions.reset}
          pieCharts={{ ...view.pieCharts, onChange: actions.setChartColumns }}
          tableColumns={{ ...view.tableColumns, onChange: actions.setTableColumns }}
        />

        <div className="min-w-0 lg:col-span-3">
          <RepositoriesSection {...view.repositories} />
          <PieChartsSection charts={view.charts} />
        </div>
      </div>
    </main>
  )
}
