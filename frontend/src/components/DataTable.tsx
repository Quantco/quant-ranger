import { useEffect, useRef, useState, type Key, type ReactNode } from "react";

export type DataTableValue = boolean | Date | null | number | string | undefined;

export interface DataTableColumn<Row> {
  align?: "left" | "right";
  id: string;
  label: ReactNode;
  maxWidth?: number | string;
  render?: (value: DataTableValue, row: Row) => ReactNode;
  sortable?: boolean;
  tooltip?: (value: DataTableValue, row: Row) => string;
  title?: string;
  truncate?: boolean;
  value: (row: Row) => DataTableValue;
}

interface DataTableProps<Row> {
  className?: string;
  columns: DataTableColumn<Row>[];
  emptyMessage: string;
  getRowKey: (row: Row, index: number) => Key;
  label: string;
  onSelectionChange?: (rows: Row[]) => void;
  rows: Row[];
}

export type DataTableSort = { direction: "ascending" | "descending"; id: string };

const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });

export function dataTableValueLabel(value: DataTableValue): string {
  if (value == null || value === "") return "-";
  if (value instanceof Date) return value.toISOString();
  return String(value);
}

function compareValues(left: DataTableValue, right: DataTableValue): number {
  if (Object.is(left, right)) return 0;
  if (left == null || left === "") return 1;
  if (right == null || right === "") return -1;
  if (left instanceof Date && right instanceof Date) return left.getTime() - right.getTime();
  if (typeof left === "number" && typeof right === "number") return left - right;
  if (typeof left === "boolean" && typeof right === "boolean") return Number(left) - Number(right);
  return collator.compare(String(left), String(right));
}

function SelectAll({ checked, indeterminate, onChange }: { checked: boolean; indeterminate: boolean; onChange: (checked: boolean) => void }) {
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (input.current) input.current.indeterminate = indeterminate;
  }, [indeterminate]);
  return <input aria-label="Select all rows" checked={checked} onChange={(event) => onChange(event.target.checked)} ref={input} type="checkbox" />;
}

function positionTooltip(trigger: HTMLSpanElement) {
  const tooltip = trigger.querySelector<HTMLElement>(".data-table-tooltip");
  if (!tooltip) return;
  const rect = trigger.getBoundingClientRect();
  const below = rect.bottom + 4;
  tooltip.style.left = `${Math.max(8, Math.min(rect.left, innerWidth - tooltip.offsetWidth - 8))}px`;
  tooltip.style.top = `${below + tooltip.offsetHeight <= innerHeight - 8 ? below : Math.max(8, rect.top - tooltip.offsetHeight - 4)}px`;
}

function TableValue({ children, maxWidth, text }: { children: ReactNode; maxWidth?: number | string; text: string }) {
  const trigger = useRef<HTMLSpanElement>(null);
  const [showTooltip, setShowTooltip] = useState(false);

  useEffect(() => {
    if (showTooltip && trigger.current) positionTooltip(trigger.current);
  }, [showTooltip]);

  const checkOverflow = () => {
    const value = trigger.current?.querySelector<HTMLElement>(".data-table-value");
    setShowTooltip(value != null && value.scrollWidth > value.clientWidth);
  };

  return (
    <span
      className="data-table-truncated"
      onBlur={() => setShowTooltip(false)}
      onFocus={checkOverflow}
      onMouseEnter={checkOverflow}
      onMouseLeave={() => setShowTooltip(false)}
      ref={trigger}
      style={{ maxWidth }}
    >
      <span className="data-table-value">{children}</span>
      {showTooltip && (
        <span aria-hidden="true" className="data-table-tooltip">
          {text}
        </span>
      )}
    </span>
  );
}

export function DataTable<Row>({
  className = "",
  columns,
  emptyMessage,
  getRowKey,
  label,
  onSelectionChange,
  onSortChange,
  rows,
  sort,
}: DataTableProps<Row> & { onSortChange?: (sort: DataTableSort) => void; sort?: DataTableSort | null }) {
  const entries = rows.map((row, index) => ({ index, key: getRowKey(row, index), row }));
  const selectionSignature = entries.map(({ key }) => String(key)).join("\0");
  const [selected, setSelected] = useState<Set<Key>>(() => new Set(entries.map(({ key }) => key)));
  const [lastSelected, setLastSelected] = useState<Key | null>(null);
  const [uncontrolledSort, setUncontrolledSort] = useState<DataTableSort | null>(null);
  const activeSort = sort === undefined ? uncontrolledSort : sort;

  useEffect(() => {
    if (!onSelectionChange) return;
    setSelected(new Set(entries.map(({ key }) => key)));
    setLastSelected(null);
    onSelectionChange([...rows]);
  }, [onSelectionChange, rows, selectionSignature]);

  const sortColumn = columns.find(({ id }) => id === activeSort?.id);
  const direction = activeSort?.direction === "descending" ? -1 : 1;
  const sorted = sortColumn == null ? entries : [...entries].sort((left, right) => direction * compareValues(sortColumn.value(left.row), sortColumn.value(right.row)) || left.index - right.index);

  if (rows.length === 0) return <p>{emptyMessage}</p>;

  const updateSelection = (next: Set<Key>) => {
    setSelected(next);
    onSelectionChange?.(sorted.filter(({ key }) => next.has(key)).map(({ row }) => row));
  };
  const updateSort = (next: DataTableSort) => {
    if (sort === undefined) setUncontrolledSort(next);
    onSortChange?.(next);
  };
  const selectRow = (key: Key, checked: boolean, range: boolean) => {
    const next = new Set(selected);
    const currentIndex = sorted.findIndex((entry) => entry.key === key);
    const lastIndex = sorted.findIndex((entry) => entry.key === lastSelected);
    const rangeEntries = range && lastIndex >= 0 ? sorted.slice(Math.min(currentIndex, lastIndex), Math.max(currentIndex, lastIndex) + 1) : [sorted[currentIndex]];
    for (const entry of rangeEntries) {
      if (checked) next.add(entry.key);
      else next.delete(entry.key);
    }
    setLastSelected(key);
    updateSelection(next);
  };
  const allSelected = entries.length > 0 && entries.every(({ key }) => selected.has(key));
  const someSelected = entries.some(({ key }) => selected.has(key));

  return (
    <div className={`data-table-scroll ${className}`.trim()}>
      <table aria-label={label} className="data-table">
        <thead>
          <tr>
            {onSelectionChange && (
              <th className="data-table-selection" scope="col">
                <SelectAll checked={allSelected} indeterminate={!allSelected && someSelected} onChange={(checked) => updateSelection(new Set(checked ? entries.map(({ key }) => key) : []))} />
              </th>
            )}
            {columns.map((column) => {
              const direction = activeSort?.id === column.id ? activeSort.direction : undefined;
              return (
                <th aria-sort={direction} className={column.align === "right" ? "data-table-cell-right" : undefined} key={column.id} scope="col" title={column.title}>
                  {column.sortable === false ? (
                    column.label
                  ) : (
                    <button className="data-table-sort" onClick={() => updateSort({ direction: direction === "ascending" ? "descending" : "ascending", id: column.id })} type="button">
                      <span>{column.label}</span>
                      <span aria-hidden="true" className="data-table-sort-indicator">
                        {direction === "ascending" ? "↑" : direction === "descending" ? "↓" : "↕"}
                      </span>
                    </button>
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.map(({ index, key, row }) => (
            <tr key={key}>
              {onSelectionChange && (
                <td className="data-table-selection">
                  <input
                    aria-label={`Select ${String(key)}`}
                    checked={selected.has(key)}
                    onChange={(event) => selectRow(key, event.target.checked, (event.nativeEvent as MouseEvent).shiftKey)}
                    type="checkbox"
                  />
                </td>
              )}
              {columns.map((column) => {
                const value = column.value(row);
                const content = column.render?.(value, row) ?? dataTableValueLabel(value);
                const tooltip = column.tooltip?.(value, row) ?? dataTableValueLabel(value);
                return (
                  <td className={column.align === "right" ? "data-table-cell-right" : undefined} key={column.id}>
                    {(column.truncate || column.maxWidth) && tooltip !== "-" ? (
                      <TableValue maxWidth={column.maxWidth} text={tooltip}>
                        {content}
                      </TableValue>
                    ) : (
                      content
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
