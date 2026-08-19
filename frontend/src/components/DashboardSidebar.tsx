import type { ReactNode } from "react";

import { CopyPageLink } from "./Clipboard";

export function DashboardSidebarShell({
  activeFilterCount,
  children,
  headingId,
  onResetFilters,
  title,
}: {
  activeFilterCount: number;
  children: ReactNode;
  headingId: string;
  onResetFilters: () => void;
  title: string;
}) {
  return (
    <aside aria-labelledby={headingId} className="dashboard-sidebar">
      <div className="dashboard-sidebar-heading">
        <h2 id={headingId}>{title}</h2>
        {activeFilterCount > 0 && <span>{activeFilterCount} active</span>}
      </div>
      <div className="dashboard-sidebar-actions">
        <CopyPageLink />
        {activeFilterCount > 0 && (
          <button className="text-button" onClick={onResetFilters} type="button">
            Reset filters
          </button>
        )}
      </div>
      {children}
    </aside>
  );
}
