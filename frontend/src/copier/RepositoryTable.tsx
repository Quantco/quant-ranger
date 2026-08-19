import { DataTable, type DataTableColumn, type DataTableSort, type DataTableValue } from "../components/DataTable";
import { rawValueLabel } from "./Charts";
import { COPIER_ANSWERS, REPOSITORIES, TEMPLATE, VALIDATION, VERSION, type DashboardRow, type DashboardValue } from "./dashboard";

const BASE_COLUMNS = new Set([REPOSITORIES, COPIER_ANSWERS, TEMPLATE, VERSION, VALIDATION]);

function renderValue(value: DataTableValue, row: DashboardRow, column: string) {
  if (column === REPOSITORIES && row.url) {
    return (
      <a href={row.url} rel="noreferrer" target="_blank">
        {rawValueLabel(value as DashboardValue)}
      </a>
    );
  }
  if (typeof value === "boolean") return <span className={`boolean-value boolean-value-${value}`}>{String(value)}</span>;
  return rawValueLabel(value as DashboardValue);
}

export function RepositoryTable({
  columns,
  onSelectionChange,
  onSortChange,
  rows,
  sort,
}: {
  columns: string[];
  onSelectionChange: (rows: DashboardRow[]) => void;
  onSortChange: (sort: DataTableSort) => void;
  rows: DashboardRow[];
  sort: DataTableSort | null;
}) {
  const tableColumns: DataTableColumn<DashboardRow>[] = columns.map((column) => ({
    id: column,
    label: BASE_COLUMNS.has(column) ? column : <code>{column}</code>,
    render: (value, row) => renderValue(value, row, column),
    title: column,
    truncate: true,
    value: (row) => row.values[column],
  }));
  return (
    <DataTable
      className="repository-table"
      columns={tableColumns}
      emptyMessage="No matching repositories."
      getRowKey={(row) => row.repository}
      label="Repository Inventory"
      onSelectionChange={onSelectionChange}
      onSortChange={onSortChange}
      rows={rows}
      sort={sort}
    />
  );
}
