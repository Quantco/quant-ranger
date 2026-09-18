import type { StateColumnVisibility } from '@/components/data-table/table-state'
import { DashboardSidebarShell } from '@/components/dashboard/DashboardSidebar'
import { FieldSelector } from '@/components/dashboard/FieldSelector'
import { MultiSelect } from '@/components/dashboard/MultiSelect'
import { DashboardFilter } from './DashboardFilter'
import type { DashboardFilter as DashboardFilterT } from './dashboard-analytics'
import type { StateCharts, StateFiltering } from './hooks'

type DashboardSidebarProps = {
  charts: StateCharts
  className: string
  /** `options` are faceted counts, so they come from the table rather than the hook. */
  filtering: StateFiltering
  augmentedFiltering: DashboardFilterT[]
  onClearAll: () => void
  visibility: StateColumnVisibility
}

export const DashboardSidebar = ({
  charts,
  className,
  filtering,
  augmentedFiltering,
  onClearAll,
  visibility
}: DashboardSidebarProps) => (
  <DashboardSidebarShell className={className} headingId="sidebar-heading" onReset={onClearAll} title="Explore data">
    <section className="m-0 grid gap-3 border-t border-border pt-3">
      <MultiSelect
        codeLabels
        id="filter-fields"
        label="Filter fields"
        onChange={filtering.fields.setFields}
        options={filtering.fields.options.map((column) => ({ label: column, value: column }))}
        placeholder="Type to add fields…"
        selected={filtering.fields.selected}
      />
      <div className="grid gap-3">
        {augmentedFiltering.map((filter) => (
          <DashboardFilter {...filter} onChange={filtering.setFilter} />
        ))}
      </div>
    </section>

    <FieldSelector
      fields={visibility.options}
      label="Table columns"
      onChange={visibility.setVisibleColumns}
      selected={visibility.selected}
    />
    <FieldSelector fields={charts.options} label="Pie charts" onChange={charts.setCharts} selected={charts.selected} />
  </DashboardSidebarShell>
)
