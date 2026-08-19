import { dataTableValueLabel } from "../components/DataTable";
import { REPOSITORIES } from "./dashboard";
import type { CountedValue, DashboardValue } from "./dashboard";

type PieChartProps = { column: string; data: CountedValue[] };

const PIE_COLORS = ["#64748b", "#3b82f6", "#8b5cf6", "#f59e0b", "#14b8a6", "#ec4899", "#84cc16", "#f97316"];

function displayValueLabel(column: string, value: DashboardValue) {
  const label = dataTableValueLabel(value);
  return column === REPOSITORIES ? label.slice(label.lastIndexOf("/") + 1) : label;
}

function sliceColor(value: DashboardValue, index: number) {
  if (value === true) return "var(--color-success-chart)";
  if (value === false) return "var(--color-error-chart)";
  if (value == null || value === "") return "var(--color-muted-foreground)";
  return PIE_COLORS[index % PIE_COLORS.length];
}

function slicePath(start: number, end: number) {
  const radius = 46;
  const point = (angle: number) => [50 + radius * Math.cos(angle), 50 + radius * Math.sin(angle)];
  const [startX, startY] = point(start);
  const [endX, endY] = point(end);
  return `M 50 50 L ${startX} ${startY} A ${radius} ${radius} 0 ${end - start > Math.PI ? 1 : 0} 1 ${endX} ${endY} Z`;
}

export function PieChart({ column, data }: PieChartProps) {
  const total = data.reduce((sum, { count }) => sum + count, 0);
  if (total === 0) return <p className="dashboard-help">No data for the selected filters.</p>;

  let offset = 0;
  const slices = data.map(({ count, value }, index) => {
    const start = (offset / total) * Math.PI * 2 - Math.PI / 2;
    offset += count;
    return { color: sliceColor(value, index), count, end: (offset / total) * Math.PI * 2 - Math.PI / 2, label: displayValueLabel(column, value), start, value };
  });

  return (
    <div className="pie-chart">
      <svg aria-label={`${column} distribution`} role="img" viewBox="0 0 100 100">
        {slices.map(({ color, count, end, label, start, value }) =>
          count === total ? (
            <circle cx="50" cy="50" fill={color} key={`${typeof value}:${String(value)}`} r="46">
              <title>{`${label}: ${count}`}</title>
            </circle>
          ) : (
            <path d={slicePath(start, end)} fill={color} key={`${typeof value}:${String(value)}`}>
              <title>{`${label}: ${count}`}</title>
            </path>
          ),
        )}
      </svg>
      <ul className="pie-chart-legend">
        {slices.map(({ color, count, label, value }) => (
          <li key={`${typeof value}:${String(value)}`}>
            <span aria-hidden="true" className="pie-chart-swatch" style={{ background: color }} />
            <span>{label}</span>
            <strong>{count}</strong>
          </li>
        ))}
      </ul>
    </div>
  );
}
