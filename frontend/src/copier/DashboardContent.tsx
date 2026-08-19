import type { DataTableSort } from "../components/DataTable";
import { AnswerChart, AnswerLegend, PieChart } from "./Charts";
import { CopyableRepositoryList } from "./ClipboardControls";
import { DisclosureIcon } from "../components/DisclosureIcon";
import { RepositoryTable } from "./RepositoryTable";
import type { CountedValue, DashboardRow } from "./dashboard";

type BooleanChartGroup = {
  charts: { column: string; rows: DashboardRow[] }[];
  id: string;
  title: string;
};

type PieChartData = {
  column: string;
  data: CountedValue[];
};

function snapshotDate(value: unknown) {
  if (typeof value !== "string" || value === "") return "Unknown snapshot date";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "Unknown snapshot date";
  return `${new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(date)} UTC`;
}

export function DashboardHeader({ generatedAt, repositoryCount }: { generatedAt: unknown; repositoryCount: number }) {
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
  return (
    <section aria-labelledby="repositories-heading" className="dashboard-section">
      <h2 id="repositories-heading">Repositories</h2>
      <p aria-live="polite" className="dashboard-summary">
        <strong>{rows.length}</strong> matching repositories · <strong>{repositoryNames.length}</strong> selected for copying
      </p>
      <p className="dashboard-help">Use the filters in the sidebar to narrow the table. Select a column heading to sort.</p>
      <RepositoryTable columns={columns} onSelectionChange={onSelectionChange} onSortChange={onSortChange} rows={rows} sort={sort} />
      <details className="repository-names">
        <summary>
          <span>Copy repository names ({repositoryNames.length})</span>
          <DisclosureIcon />
        </summary>
        <p className="dashboard-help">These lists contain the repository rows selected above.</p>
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
      </details>
    </section>
  );
}

export function PieChartsSection({ charts }: { charts: PieChartData[] }) {
  if (charts.length === 0) return null;

  return (
    <section aria-labelledby="pie-charts-heading" className="dashboard-section">
      <h2 id="pie-charts-heading">Pie charts</h2>
      <p className="dashboard-help">Contents of the selected fields across the currently matching repositories.</p>
      <div className="pie-charts">
        {charts.map(({ column, data }) => (
          <div className="pie-chart-card" key={column}>
            <h3>
              <code>{column}</code>
            </h3>
            <PieChart column={column} data={data} />
          </div>
        ))}
      </div>
    </section>
  );
}

export function BooleanChartsSections({ groups }: { groups: BooleanChartGroup[] }) {
  return groups.map(({ charts, id, title }) => (
    <section aria-labelledby={`${id}-heading`} className="dashboard-section" key={id}>
      <h2 id={`${id}-heading`}>{title}</h2>
      <p className="dashboard-help">Breakdown of the currently matching repositories.</p>
      <AnswerLegend />
      <div className="answer-plots">
        {charts.map(({ column, rows }) => (
          <div key={column}>
            <h3>
              <code>{column}</code>
            </h3>
            <AnswerChart column={column} rows={rows} />
          </div>
        ))}
      </div>
    </section>
  ));
}
