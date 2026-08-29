import { DashboardSidebarShell } from '../components/DashboardSidebar'
import { FieldSelector } from '../components/FieldSelector'
import { MultiSelect } from '../components/MultiSelect'
import { Input } from '../components/ui/input'
import { updaterResultColumnLabel, type UpdaterFilterDefinition, type UpdaterResultColumnId } from './result-columns'

interface UpdaterSidebarProps {
  filters: (UpdaterFilterDefinition & { selected: string[] })[]
  onFilterChange: (column: UpdaterResultColumnId, selected: string[]) => void
  onReset: () => void
  onSearchChange: (value: string) => void
  onTableColumnsChange: (columns: string[]) => void
  search: string
  tableColumns: { fields: string[]; selected: string[] }
}

export function UpdaterSidebar({
  filters,
  onFilterChange,
  onReset,
  onSearchChange,
  onTableColumnsChange,
  search,
  tableColumns
}: UpdaterSidebarProps) {
  return (
    <DashboardSidebarShell
      className="w-full lg:w-80 lg:flex-none"
      headingId="updater-sidebar-heading"
      onReset={onReset}
      title="Explore results"
    >
      <section aria-label="Result filters" className="m-0 grid gap-3 border-t border-border pt-3">
        <label className="grid gap-1 text-sm/tight font-semibold">
          Search
          <Input
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="Repository, target, pull request…"
            type="search"
            value={search}
          />
        </label>
        {filters.map(({ column, label, options, placeholder, selected }) => (
          <MultiSelect
            id={`updater-filter-${column}`}
            key={column}
            label={label}
            onChange={(next) => onFilterChange(column, next)}
            options={options}
            placeholder={placeholder}
            selected={selected}
          />
        ))}
      </section>

      <FieldSelector
        codeLabels={false}
        fields={tableColumns.fields}
        getFieldLabel={updaterResultColumnLabel}
        label="Table columns"
        onChange={onTableColumnsChange}
        selected={tableColumns.selected}
      />
    </DashboardSidebarShell>
  )
}
