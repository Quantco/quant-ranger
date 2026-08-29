import type { ReactNode } from 'react'

import { DashboardSidebarShell } from '../components/dashboard/DashboardSidebar'
import { FieldSelector } from '../components/dashboard/FieldSelector'
import { MultiSelect } from '../components/dashboard/MultiSelect'

interface FieldSelection {
  fields: string[]
  onChange: (fields: string[]) => void
  selected: string[]
}

interface DashboardSidebarProps {
  className: string
  filterFields: FieldSelection
  filterInputs: ReactNode
  onReset: () => void
  pieCharts: FieldSelection
  tableColumns: FieldSelection
}

export function DashboardSidebar({
  className,
  filterFields,
  filterInputs,
  onReset,
  pieCharts,
  tableColumns
}: DashboardSidebarProps) {
  return (
    <DashboardSidebarShell className={className} headingId="sidebar-heading" onReset={onReset} title="Explore data">
      <section className="m-0 grid gap-3 border-t border-border pt-3">
        <MultiSelect
          codeLabels
          id="filter-fields"
          label="Filter fields"
          onChange={filterFields.onChange}
          options={filterFields.fields.map((column) => ({ label: column, value: column }))}
          placeholder="Type to add fields…"
          selected={filterFields.selected}
        />
        <div className="grid gap-3">{filterInputs}</div>
      </section>

      <FieldSelector
        fields={tableColumns.fields}
        label="Table columns"
        onChange={tableColumns.onChange}
        selected={tableColumns.selected}
      />
      <FieldSelector
        fields={pieCharts.fields}
        label="Pie charts"
        onChange={pieCharts.onChange}
        selected={pieCharts.selected}
      />
    </DashboardSidebarShell>
  )
}
