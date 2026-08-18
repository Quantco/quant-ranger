import * as Plot from "@observablehq/plot";
import { useEffect, useRef } from "react";

import { REPOSITORIES, answerCounts } from "./dashboard";
import type { CountedValue, DashboardRow, DashboardValue } from "./dashboard";

type AnswerChartProps = { column: string; rows: DashboardRow[] };
type PieChartProps = { column: string; data: CountedValue[] };

const PIE_COLORS = ["#64748b", "#3b82f6", "#8b5cf6", "#f59e0b", "#14b8a6", "#ec4899", "#84cc16", "#f97316"];

export const rawValueLabel = (value: DashboardValue) => (value == null || value === "" ? "No value" : String(value));

const valueKey = (value: DashboardValue) => `${typeof value}:${String(value)}`;

function PlotFigure({ options }: { options: Plot.PlotOptions }) {
  const container = useRef<HTMLDivElement>(null);
  useEffect(() => {
    try {
      const plot = Plot.plot(options);
      container.current?.replaceChildren(plot);
      return () => plot.remove();
    } catch (error) {
      const fallback = document.createElement("p");
      fallback.className = "chart-error";
      fallback.textContent = `Chart unavailable: ${error instanceof Error ? error.message : String(error)}`;
      container.current?.replaceChildren(fallback);
    }
  }, [options]);
  return <div className="observable-plot" ref={container} />;
}

export function AnswerChart({ column, rows }: AnswerChartProps) {
  const values = answerCounts(rows, column).map(({ count, value }) => ({ count, key: valueKey(value), label: rawValueLabel(value), value }));
  if (values.length === 0) return <p>No data for the selected filters.</p>;
  const labels = new Map(values.map(({ count, key, label }) => [key, `${label} (${count})`]));
  const options: Plot.PlotOptions = {
    ariaLabel: `${column} distribution`,
    axis: null,
    color: {
      domain: values.map(({ key }) => key),
      legend: "swatches",
      range: values.map(({ value }) => sliceColor(value, 0)),
      tickFormat: (key) => labels.get(String(key)),
    },
    height: 32,
    margin: 0,
    style: { fontSize: "12px" },
    width: 800,
    x: { domain: [0, rows.length], nice: false },
    marks: [
      Plot.barX(
        values,
        Plot.stackX({
          ariaLabel: ({ count, label }) => `${label}: ${count}`,
          fill: "key",
          title: ({ count, label }) => `${label}: ${count}`,
          x: "count",
        }),
      ),
    ],
  };
  return <PlotFigure options={options} />;
}

function displayValueLabel(column: string, value: DashboardValue) {
  const label = rawValueLabel(value);
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
