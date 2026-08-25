import type { ReactNode } from 'react'

import { DashboardSidebarShell } from '../components/DashboardSidebar'
import { FieldSelector } from '../components/FieldSelector'
import { MultiSelect } from '../components/MultiSelect'
import { REPOSITORIES } from './dashboard'

type FieldSelection = {
  fields: string[]
  onChange: (fields: Set<string>) => void
  selected: Set<string>
}

type DashboardSidebarProps = {
  filterFields: FieldSelection
  filterInputs: ReactNode
  onReset: () => void
  pieCharts: FieldSelection
  tableColumns: FieldSelection
}

function replaceSelection(current: Set<string>, fields: string[], replacement: Set<string>) {
  const fieldSet = new Set(fields)
  return new Set([...current].filter((field) => !fieldSet.has(field)).concat([...replacement]))
}

export function DashboardSidebar({
  filterFields,
  filterInputs,
  onReset,
  pieCharts,
  tableColumns
}: DashboardSidebarProps) {
  const optionalTableColumns = tableColumns.fields.filter((column) => column !== REPOSITORIES)
  const visibleSelectedTableColumns = new Set(
    optionalTableColumns.filter((column) => tableColumns.selected.has(column))
  )

  return (
    <DashboardSidebarShell headingId="sidebar-heading" onReset={onReset} title="Explore data">
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
        fields={optionalTableColumns}
        label="Table columns"
        onChange={(columns) =>
          tableColumns.onChange(replaceSelection(tableColumns.selected, optionalTableColumns, columns))
        }
        selected={visibleSelectedTableColumns}
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
