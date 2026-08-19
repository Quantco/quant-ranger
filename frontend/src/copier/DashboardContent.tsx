import { useState } from "react";

import type { DataTableSort } from "../components/DataTable";
import { formatDateTime } from "../date";
import { PieChart } from "./Charts";
import { CopyableRepositoryList } from "./ClipboardControls";
import { DisclosureIcon } from "../components/DisclosureIcon";
import { RepositoryTable } from "./RepositoryTable";
import type { CountedValue, DashboardRow } from "./dashboard";

type PieChartData = {
  column: string;
  data: CountedValue[];
};

function snapshotDate(value: string) {
  return formatDateTime(value, true) ?? "Unknown snapshot date";
}

export function DashboardHeader({ generatedAt, repositoryCount }: { generatedAt: string; repositoryCount: number }) {
  return (
    <header className="dashboard-header">
      <h1>Copier Dashboard</h1>
      <p>Compare Copier templates, versions, and answers across repositories.</p>
      <p className="dashboard-meta">
        <span>
          <strong>{repositoryCount}</strong> repositories
        </span>
        <span>Updated {snapshotDate(generatedAt)}</span>
      </p>
    </header>
  );
}

export function RepositoriesSection({
  columns,
  onSelectionChange,
  onSortChange,
  repositoryNames,
  rows,
  sort,
}: {
  columns: string[];
  onSelectionChange: (rows: DashboardRow[]) => void;
  onSortChange: (sort: DataTableSort | null) => void;
  repositoryNames: string[];
  rows: DashboardRow[];
  sort: DataTableSort | null;
}) {
  const [showRepositoryNames, setShowRepositoryNames] = useState(false);
  return (
    <section aria-labelledby="repositories-heading" className="dashboard-section">
      <h2 id="repositories-heading">Repositories</h2>
      <div className="repository-toolbar">
        <p aria-live="polite" className="dashboard-summary">
          <strong>{rows.length}</strong> matching repositories · <strong>{repositoryNames.length}</strong> selected for copying
        </p>
        <button aria-expanded={showRepositoryNames} className="repository-copy-toggle" onClick={() => setShowRepositoryNames((visible) => !visible)} type="button">
          <DisclosureIcon />
          <span>Copy repository names ({repositoryNames.length})</span>
        </button>
      </div>
      {showRepositoryNames && (
        <div className="repository-names">
          <p className="dashboard-help">These lists contain the repository rows selected below.</p>
          <div className="repository-lists">
            <div>
              <h3>Comma-separated</h3>
              <CopyableRepositoryList label="Comma-separated" value={repositoryNames.join(",")} />
            </div>
            <div>
              <h3>Newline-separated</h3>
              <CopyableRepositoryList label="Newline-separated" value={repositoryNames.join("\n")} />
            </div>
          </div>
        </div>
      )}
      <p className="dashboard-help">Use the filters in the sidebar to narrow the table. Select a column heading to sort.</p>
      <RepositoryTable columns={columns} onSelectionChange={onSelectionChange} onSortChange={onSortChange} rows={rows} sort={sort} />
    </section>
  );
}

export function PieChartsSection({ charts }: { charts: PieChartData[] }) {
  const [expandedChart, setExpandedChart] = useState<string | null>(null);
  if (charts.length === 0) return null;

  return (
    <section aria-labelledby="pie-charts-heading" className="dashboard-section">
      <h2 id="pie-charts-heading">Pie charts</h2>
      <p className="dashboard-help">Contents of the selected fields across the currently matching repositories.</p>
      <div className="pie-charts">
        {charts.map(({ column, data }) => {
          const expanded = expandedChart === column;
          return (
            <div className={`pie-chart-card${expanded ? " pie-chart-card-expanded" : ""}`} key={column}>
              <div className="pie-chart-card-heading">
                <h3>
                  <code>{column}</code>
                </h3>
                <button aria-expanded={expanded} className="text-button" onClick={() => setExpandedChart(expanded ? null : column)} type="button">
                  {expanded ? "Show smaller" : "Show larger"}
                </button>
              </div>
              <PieChart column={column} data={data} />
            </div>
          );
        })}
      </div>
    </section>
  );
}
