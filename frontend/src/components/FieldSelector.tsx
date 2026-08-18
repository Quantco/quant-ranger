import { useEffect, useRef } from "react";

import { DisclosureIcon } from "./DisclosureIcon";

type FieldSelectorProps = {
  codeLabels?: boolean;
  emptyMessage?: string;
  fields: string[];
  getFieldLabel?: (field: string) => string;
  label: string;
  onChange: (fields: Set<string>) => void;
  selected: Set<string>;
  summary?: string;
};

export function FieldSelector({ codeLabels = true, emptyMessage = "No fields available.", fields, getFieldLabel = (field) => field, label, onChange, selected, summary }: FieldSelectorProps) {
  const allSelected = fields.length > 0 && fields.every((field) => selected.has(field));
  const selectedCount = fields.filter((field) => selected.has(field)).length;
  const summaryCheckbox = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (summaryCheckbox.current != null) summaryCheckbox.current.indeterminate = selectedCount > 0 && !allSelected;
  }, [allSelected, selectedCount]);

  const selectAll = () => onChange(new Set(fields));
  const clearAll = () => onChange(new Set());

  return (
    <details className="dashboard-sidebar-section column-selector">
      <summary>
        <DisclosureIcon />
        <span>
          {label} ({summary ?? `${selectedCount} of ${fields.length}`})
        </span>
        <input
          aria-label={`${allSelected ? "Clear" : "Select"} all ${label.toLocaleLowerCase()}`}
          checked={allSelected}
          className="selector-summary-checkbox"
          disabled={fields.length === 0}
          onChange={allSelected ? clearAll : selectAll}
          onClick={(event) => event.stopPropagation()}
          ref={summaryCheckbox}
          title={allSelected ? `Clear all ${label.toLocaleLowerCase()}` : `Select all ${label.toLocaleLowerCase()}`}
          type="checkbox"
        />
      </summary>
      <div className="column-selector-actions">
        <button className="text-button" disabled={allSelected || fields.length === 0} onClick={selectAll} type="button">
          Select all
        </button>
        <button className="text-button" disabled={selectedCount === 0} onClick={clearAll} type="button">
          Clear all
        </button>
      </div>
      {fields.length === 0 ? (
        <p className="selector-empty">{emptyMessage}</p>
      ) : (
        <div className="column-selector-options">
          {fields.map((field) => {
            const fieldLabel = getFieldLabel(field);
            return (
              <label key={field}>
                <input
                  checked={selected.has(field)}
                  onChange={(event) => {
                    const next = new Set(selected);
                    if (event.target.checked) next.add(field);
                    else next.delete(field);
                    onChange(next);
                  }}
                  type="checkbox"
                />
                {codeLabels ? <code>{fieldLabel}</code> : fieldLabel}
              </label>
            );
          })}
        </div>
      )}
    </details>
  );
}
