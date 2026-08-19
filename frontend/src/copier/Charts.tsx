import { dataTableValueLabel } from "../components/DataTable";
import { REPOSITORIES } from "./dashboard";
import type { CountedValue, DashboardValue } from "./dashboard";

type PieChartProps = { column: string; data: CountedValue[] };

function displayValueLabel(column: string, value: DashboardValue) {
  const label = dataTableValueLabel(value);
  return column === REPOSITORIES ? label.slice(label.lastIndexOf("/") + 1) : label;
}

function sliceColor(value: DashboardValue, index: number) {
  if (value === true) return "var(--color-success-chart)";
  if (value === false) return "var(--color-error-chart)";
  if (value == null || value === "") return "var(--color-muted-foreground)";
  return `hsl(${(220 + index * 137.5) % 360} 68% 45%)`;
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
            <path d={slicePath(start, end)} fill={color} key={`${typeof value}:${String(value)}`} stroke="#fff" strokeWidth="0.8">
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
