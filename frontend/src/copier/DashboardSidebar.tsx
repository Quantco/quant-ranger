import type { ReactNode } from 'react'

import { DashboardSidebarShell } from '@/components/dashboard/DashboardSidebar'
import { FieldSelector } from '@/components/dashboard/FieldSelector'
import { MultiSelect } from '@/components/dashboard/MultiSelect'

type FieldSelection = {
  options: string[]
  onChange: (options: string[]) => void
  selected: string[]
}

type DashboardSidebarProps = {
  className: string
  filterFields: FieldSelection
  filterInputs: ReactNode
  onReset: () => void
  pieCharts: FieldSelection
  tableColumns: FieldSelection
}

export const DashboardSidebar = ({
  className,
  filterFields,
  filterInputs,
  onReset,
  pieCharts,
  tableColumns
}: DashboardSidebarProps) => (
  <DashboardSidebarShell className={className} headingId="sidebar-heading" onReset={onReset} title="Explore data">
    <section className="m-0 grid gap-3 border-t border-border pt-3">
      <MultiSelect
        codeLabels
        id="filter-fields"
        label="Filter fields"
        onChange={filterFields.onChange}
        options={filterFields.options.map((column) => ({ label: column, value: column }))}
        placeholder="Type to add fields…"
        selected={filterFields.selected}
      />
      <div className="grid gap-3">{filterInputs}</div>
    </section>

    <FieldSelector
      fields={tableColumns.options}
      label="Table columns"
      onChange={tableColumns.onChange}
      selected={tableColumns.selected}
    />
    <FieldSelector
      fields={pieCharts.options}
      label="Pie charts"
      onChange={pieCharts.onChange}
      selected={pieCharts.selected}
    />
  </DashboardSidebarShell>
)
