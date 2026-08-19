import { useId } from "react";
import type { CSSProperties } from "react";

import { displayValue } from "../value";
import { REPOSITORIES, repositoryName } from "./dashboard";
import type { CountedValue, DashboardValue } from "./dashboard";

type PieChartProps = { column: string; data: CountedValue[] };

const CATEGORICAL_COLORS = ["#4477aa", "#ee6677", "#228833", "#ccbb44", "#66ccee", "#aa3377", "#ee7733", "#332288"] as const;

type SliceTexture = "crosshatch" | "diagonal" | "dots" | "solid";

type SliceStyle = {
  color: string;
  texture: SliceTexture;
};

function displayValueLabel(column: string, value: DashboardValue) {
  const label = displayValue(value);
  return column === REPOSITORIES ? repositoryName(label) : label;
}

function sliceStyle(value: DashboardValue, index: number): SliceStyle {
  if (value === true) return { color: "var(--color-success-chart)", texture: "solid" };
  if (value === false) return { color: "var(--color-error-chart)", texture: "solid" };
  if (value == null || value === "") return { color: "var(--color-chart-neutral)", texture: "solid" };

  const color = CATEGORICAL_COLORS[index % CATEGORICAL_COLORS.length] ?? CATEGORICAL_COLORS[0];
  const textures: SliceTexture[] = ["solid", "diagonal", "dots", "crosshatch"];
  return { color, texture: textures[Math.floor(index / CATEGORICAL_COLORS.length) % textures.length] ?? "solid" };
}

function swatchStyle({ color, texture }: SliceStyle): CSSProperties {
  const style: CSSProperties = { backgroundColor: color };
  if (texture === "diagonal") style.backgroundImage = "repeating-linear-gradient(135deg, transparent 0 3px, rgb(255 255 255 / 75%) 3px 4px)";
  if (texture === "dots") style.backgroundImage = "radial-gradient(rgb(255 255 255 / 80%) 1px, transparent 1px)";
  if (texture === "dots") style.backgroundSize = "4px 4px";
  if (texture === "crosshatch")
    style.backgroundImage =
      "linear-gradient(45deg, transparent 42%, rgb(255 255 255 / 65%) 42% 58%, transparent 58%), linear-gradient(135deg, transparent 42%, rgb(255 255 255 / 65%) 42% 58%, transparent 58%)";
  return style;
}

function slicePath(start: number, end: number) {
  const radius = 46;
  const point = (angle: number) => [50 + radius * Math.cos(angle), 50 + radius * Math.sin(angle)];
  const [startX, startY] = point(start);
  const [endX, endY] = point(end);
  return `M 50 50 L ${startX} ${startY} A ${radius} ${radius} 0 ${end - start > Math.PI ? 1 : 0} 1 ${endX} ${endY} Z`;
}

export function PieChart({ column, data }: PieChartProps) {
  const chartId = useId().replaceAll(":", "");
  const total = data.reduce((sum, { count }) => sum + count, 0);
  if (total === 0) return <p className="dashboard-help">No data for the selected filters.</p>;

  let offset = 0;
  const slices = data.map(({ count, value }, index) => {
    const start = (offset / total) * Math.PI * 2 - Math.PI / 2;
    offset += count;
    return { count, end: (offset / total) * Math.PI * 2 - Math.PI / 2, index, label: displayValueLabel(column, value), start, style: sliceStyle(value, index), value };
  });

  return (
    <div className="pie-chart">
      <svg aria-label={`${column} distribution`} role="img" viewBox="0 0 100 100">
        <defs>
          {slices.map(({ index, style }) =>
            style.texture === "solid" ? null : (
              <pattern height="6" id={`${chartId}-${index}`} key={index} patternUnits="userSpaceOnUse" width="6">
                <rect fill={style.color} height="6" width="6" />
                {style.texture === "diagonal" && <path d="M-1 1 1-1M0 6 6 0M5 7 7 5" stroke="#fff" strokeOpacity="0.75" strokeWidth="1.2" />}
                {style.texture === "dots" && <circle cx="3" cy="3" fill="#fff" fillOpacity="0.8" r="0.9" />}
                {style.texture === "crosshatch" && <path d="M0 0 6 6M6 0 0 6" stroke="#fff" strokeOpacity="0.65" strokeWidth="0.9" />}
              </pattern>
            ),
          )}
        </defs>
        {slices.map(({ count, end, index, label, start, style, value }) =>
          count === total ? (
            <circle cx="50" cy="50" fill={style.texture === "solid" ? style.color : `url(#${chartId}-${index})`} key={`${typeof value}:${String(value)}`} r="46">
              <title>{`${label}: ${count}`}</title>
            </circle>
          ) : (
            <path d={slicePath(start, end)} fill={style.texture === "solid" ? style.color : `url(#${chartId}-${index})`} key={`${typeof value}:${String(value)}`} stroke="#fff" strokeWidth="0.8">
              <title>{`${label}: ${count}`}</title>
            </path>
          ),
        )}
      </svg>
      <ul className="pie-chart-legend">
        {slices.map(({ count, label, style, value }) => (
          <li key={`${typeof value}:${String(value)}`}>
            <span aria-hidden="true" className="pie-chart-swatch" style={swatchStyle(style)} />
            <span>{label}</span>
            <strong>{count}</strong>
          </li>
        ))}
      </ul>
    </div>
  );
}
