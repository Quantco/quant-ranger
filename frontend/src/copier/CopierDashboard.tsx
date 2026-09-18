import type { Snapshot } from './report'
import { Header, PieCharts, Repositories } from './sections'
import { Sidebar } from './Sidebar'
import { useCopierDashboard } from './useCopierDashboard'

const CopierDashboard = ({ snapshot }: { snapshot: Snapshot }) => {
  const { charts, clearAll, facets, filtering, table, visibility } = useCopierDashboard(snapshot)

  const matching = table.getFilteredRowModel().rows.length
  const selected = table.getFilteredSelectedRowModel().rows.map(({ original }) => original.repository)

  return (
    <main>
      <Header generatedAt={snapshot.generatedAt} repositoryCount={snapshot.rows.length} />

      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-4 lg:gap-6">
        <Sidebar
          charts={charts}
          className="lg:col-span-1"
          facets={facets}
          filtering={filtering}
          onClearAll={clearAll}
          visibility={visibility}
        />

        <div className="min-w-0 lg:col-span-3">
          <Repositories matchingRepositoryCount={matching} repositoryNames={selected} table={table} />
          <PieCharts charts={charts.data} />
        </div>
      </div>
    </main>
  )
}

export default CopierDashboard
