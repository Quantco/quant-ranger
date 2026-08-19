import type { ReactNode } from "react";

import { DashboardSidebarShell } from "../components/DashboardSidebar";
import { FieldSelector } from "../components/FieldSelector";
import { MultiSelect } from "./MultiSelect";
import { REPOSITORIES } from "./dashboard";

type FieldSelection = {
  fields: string[];
  onChange: (fields: Set<string>) => void;
  selected: Set<string>;
};

type DashboardSidebarProps = {
  activeFilterCount: number;
  booleanOptions: FieldSelection;
  filters: FieldSelection & { controls: ReactNode };
  onResetFilters: () => void;
  pieCharts: FieldSelection;
  tableColumns: FieldSelection & { visibleCount: number };
};

function replaceSelection(current: Set<string>, fields: string[], replacement: Set<string>) {
  const fieldSet = new Set(fields);
  return new Set([...current].filter((field) => !fieldSet.has(field)).concat([...replacement]));
}

export function DashboardSidebar({ activeFilterCount, booleanOptions, filters, onResetFilters, pieCharts, tableColumns }: DashboardSidebarProps) {
  const optionalTableColumns = tableColumns.fields.filter((column) => column !== REPOSITORIES);
  const visibleSelectedTableColumns = new Set(optionalTableColumns.filter((column) => tableColumns.selected.has(column)));

  return (
    <DashboardSidebarShell activeFilterCount={activeFilterCount} headingId="sidebar-heading" onResetFilters={onResetFilters} title="Explore data">
      <section className="dashboard-sidebar-section filter-builder">
        <MultiSelect
          codeLabels
          id="filter-fields"
          label="Filter fields"
          onChange={filters.onChange}
          options={filters.fields.map((column) => ({ label: column, value: column }))}
          placeholder="Type to add fields…"
          selected={filters.selected}
        />
        <div className="dynamic-filter-controls">{filters.controls}</div>
      </section>

      <FieldSelector
        fields={optionalTableColumns}
        label="Table columns"
        onChange={(columns) => tableColumns.onChange(replaceSelection(tableColumns.selected, optionalTableColumns, columns))}
        selected={visibleSelectedTableColumns}
        summary={`${tableColumns.visibleCount} of ${tableColumns.fields.length}`}
      />
      <FieldSelector fields={pieCharts.fields} label="Pie charts" onChange={pieCharts.onChange} selected={pieCharts.selected} />
      <FieldSelector
        emptyMessage="Select one template to choose Boolean options."
        fields={booleanOptions.fields}
        label="Boolean Template Options"
        onChange={booleanOptions.onChange}
        selected={booleanOptions.selected}
      />
    </DashboardSidebarShell>
  );
}
