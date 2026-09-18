import { DashboardSidebarShell } from '@/components/dashboard/DashboardSidebar'
import { FieldSelector } from '@/components/dashboard/FieldSelector'
import { MultiSelect } from '@/components/dashboard/MultiSelect'
import { Input } from '@/components/ui/Input'
import { updaterResultColumnLabel } from './result-columns'
import type { StateColumnVisibility } from '@/components/data-table/hooks'
import type { StateFiltering, StateSearch } from './hooks'

type UpdaterSidebarProps = {
  filtering: StateFiltering
  searching: StateSearch
  visibility: StateColumnVisibility
  onClearAll: () => void
}

export const UpdaterSidebar = ({ filtering, searching, visibility, onClearAll }: UpdaterSidebarProps) => (
  <DashboardSidebarShell
    className="w-full lg:w-80 lg:flex-none"
    headingId="updater-sidebar-heading"
    onReset={onClearAll}
    title="Explore results"
  >
    <section aria-label="Result filters" className="m-0 grid gap-3 border-t border-border pt-3">
      <label className="grid gap-1 text-sm/tight font-semibold">
        Search
        <Input
          onChange={(event) => searching.setQuery(event.target.value)}
          placeholder="Repository, target, pull request…"
          type="search"
          value={searching.query}
        />
      </label>
      {filtering.options.map(({ column, label, options, placeholder }) => (
        <MultiSelect
          id={`updater-filter-${column}`}
          key={column}
          label={label}
          onChange={(next) => filtering.setFilter(column, next)}
          options={options}
          placeholder={placeholder}
          selected={filtering.filters[column] ?? []}
        />
      ))}
    </section>

    <FieldSelector
      codeLabels={false}
      fields={visibility.options}
      getFieldLabel={updaterResultColumnLabel}
      label="Table columns"
      onChange={visibility.setVisibleColumns}
      selected={visibility.selected}
    />
  </DashboardSidebarShell>
)
