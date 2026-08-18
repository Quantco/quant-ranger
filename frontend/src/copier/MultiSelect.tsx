import { useEffect, useRef, useState, type ReactNode } from "react";

export type AutocompleteOption = {
  detail?: string;
  label: string;
  value: string;
};

type MultiSelectProps = {
  codeLabels?: boolean;
  id: string;
  label: ReactNode;
  labelAction?: ReactNode;
  onChange: (selected: Set<string>) => void;
  options: AutocompleteOption[];
  placeholder: string;
  selected: Set<string>;
};

function matchRank(label: string, query: string) {
  const candidate = label.toLocaleLowerCase();
  const search = query.trim().toLocaleLowerCase();
  if (search === "" || candidate === search) return 0;
  if (candidate.startsWith(search)) return 1;
  if (candidate.split(/[^a-zA-Z0-9]+/).some((word) => word.startsWith(search))) return 2;
  return candidate.includes(search) ? 3 : Infinity;
}

export function matchingOptions<T extends { label: string }>(options: T[], query: string) {
  return options
    .map((option) => ({ option, rank: matchRank(option.label, query) }))
    .filter(({ rank }) => Number.isFinite(rank))
    .sort((left, right) => left.rank - right.rank)
    .map(({ option }) => option);
}

export function MultiSelect({ codeLabels = false, id, label, labelAction, onChange, options, placeholder, selected }: MultiSelectProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const root = useRef<HTMLDivElement>(null);
  const visibleOptions = matchingOptions(options, query);
  const selectedOptions = options.filter(({ value }) => selected.has(value));
  const bestMatch = query.trim() === "" ? undefined : visibleOptions.find(({ value }) => !selected.has(value));
  const allVisibleSelected = visibleOptions.length > 0 && visibleOptions.every(({ value }) => selected.has(value));

  useEffect(() => {
    if (!open) return;
    const closeOutside = (event: PointerEvent) => {
      if (event.target instanceof Node && !root.current?.contains(event.target)) {
        setOpen(false);
        setQuery("");
      }
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        setQuery("");
      }
    };
    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  const toggleOption = (value: string) => {
    const next = new Set(selected);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    onChange(next);
  };

  const toggleVisibleOptions = () => {
    const next = new Set(selected);
    for (const { value } of visibleOptions) {
      if (allVisibleSelected) next.delete(value);
      else next.add(value);
    }
    onChange(next);
  };

  return (
    <div className="multi-select" ref={root}>
      <div className="filter-control-heading">
        <span className="multi-select-label" id={`${id}-label`}>
          {label}
        </span>
        {labelAction}
      </div>
      <div className="multi-select-control">
        <div className="multi-select-values" onClick={() => input.current?.focus()}>
          {selectedOptions.map(({ label: optionLabel, value }) => (
            <button
              aria-label={`Remove ${optionLabel}`}
              className="multi-select-chip"
              key={value}
              onClick={(event) => {
                event.stopPropagation();
                toggleOption(value);
                input.current?.focus();
              }}
              type="button"
            >
              {codeLabels ? <code>{optionLabel}</code> : optionLabel}
              <span aria-hidden="true">×</span>
            </button>
          ))}
          <input
            aria-controls={open ? `${id}-options` : undefined}
            aria-expanded={open}
            aria-labelledby={`${id}-label`}
            className="multi-select-search"
            onChange={(event) => {
              setQuery(event.target.value);
              setOpen(true);
            }}
            onFocus={() => setOpen(true)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && bestMatch != null) {
                event.preventDefault();
                onChange(new Set(selected).add(bestMatch.value));
                setQuery("");
              } else if (event.key === "Backspace" && query === "" && selectedOptions.length > 0) {
                toggleOption(selectedOptions.at(-1)!.value);
              } else if (event.key === "ArrowDown") {
                setOpen(true);
              }
            }}
            placeholder={selectedOptions.length === 0 ? placeholder : "Search…"}
            ref={input}
            type="search"
            value={query}
          />
        </div>
        <button
          aria-label={`Clear ${typeof label === "string" ? label.toLocaleLowerCase() : "selected values"}`}
          className="multi-select-clear"
          disabled={selected.size === 0 && query === ""}
          onClick={() => {
            onChange(new Set());
            setOpen(false);
            setQuery("");
          }}
          title="Clear selection"
          type="button"
        >
          <span aria-hidden="true">×</span>
        </button>
      </div>
      {open && (
        <div className="multi-select-menu">
          <div className="multi-select-menu-actions">
            <button className="text-button" disabled={visibleOptions.length === 0} onClick={toggleVisibleOptions} type="button">
              {allVisibleSelected ? "Clear shown" : "Select shown"}
            </button>
            {selected.size > 0 && (
              <button className="text-button" onClick={() => onChange(new Set())} type="button">
                Clear all
              </button>
            )}
          </div>
          <div aria-labelledby={`${id}-label`} className="multi-select-options" id={`${id}-options`}>
            {visibleOptions.length === 0 ? (
              <span className="multi-select-empty">No matching options</span>
            ) : (
              visibleOptions.map(({ detail, label: optionLabel, value }) => (
                <label className={bestMatch?.value === value ? "is-best-match" : undefined} key={value}>
                  <input checked={selected.has(value)} onChange={() => toggleOption(value)} type="checkbox" />
                  <span>{codeLabels ? <code>{optionLabel}</code> : optionLabel}</span>
                  {detail != null && <small>{detail}</small>}
                </label>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
