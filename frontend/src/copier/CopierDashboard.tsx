import { DashboardHeader, PieChartsSection, RepositoriesSection } from './DashboardContent'
import { DashboardSidebar } from './DashboardSidebar'
import type { DashboardSnapshot } from './dashboard'
import { useCopierDashboardController } from './useCopierDashboard'

const CopierDashboard = ({ snapshot }: { snapshot: DashboardSnapshot }) => {
  const { clearAllState, uses } = useCopierDashboardController(snapshot)

  const filteredRowCount = uses.table.getFilteredRowModel().rows.length
  const repos = uses.table.getFilteredSelectedRowModel().rows.map(({ original }) => original.repository)

  return (
    <main>
      <DashboardHeader generatedAt={snapshot.generatedAt} repositoryCount={snapshot.rows.length} />

      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-4 lg:gap-6">
        <DashboardSidebar
          charts={uses.charts}
          className="lg:col-span-1"
          filtering={uses.filtering}
          augmentedFiltering={uses.augmentedFiltering}
          onClearAll={clearAllState}
          visibility={uses.visibility}
        />

        <div className="min-w-0 lg:col-span-3">
          <RepositoriesSection matchingRepositoryCount={filteredRowCount} repositoryNames={repos} table={uses.table} />
          <PieChartsSection charts={uses.augmentedCharts} />
        </div>
      </div>
    </main>
  )
}

export default CopierDashboard
