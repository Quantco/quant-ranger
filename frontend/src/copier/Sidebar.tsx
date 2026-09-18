import type { StateColumnVisibility } from '@/components/data-table/hooks'
import { DashboardSidebarShell } from '@/components/dashboard/DashboardSidebar'
import { FieldSelector } from '@/components/dashboard/FieldSelector'
import { MultiSelect } from '@/components/dashboard/MultiSelect'
import type { Facet } from './facets'
import { FilterControl } from './FilterControl'
import type { Charts, Filtering } from './hooks'

type SidebarProps = {
  charts: Charts
  className: string
  /** Built from the table, since the option counts are faceted over the filtered rows. */
  facets: Facet[]
  filtering: Filtering
  onClearAll: () => void
  visibility: StateColumnVisibility
}

export const Sidebar = ({ charts, className, facets, filtering, onClearAll, visibility }: SidebarProps) => (
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
        {facets.map((facet) => (
          <FilterControl {...facet} key={facet.column.id} onChange={filtering.setFilter} />
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
