import { rawValueLabel } from "./Charts";
import { MultiSelect } from "./MultiSelect";
import { REPOSITORIES } from "./dashboard";
import type { CountedValue, DashboardValue, TextFilter, ValueFilter } from "./dashboard";
import { useAutocomplete } from "./useAutocomplete";

const valueToken = (value: DashboardValue) => `${typeof value}:${String(value)}`;

function controlId(column: string) {
  return column.replace(/[^a-zA-Z0-9_-]/g, "-");
}

function repositoryName(value: string) {
  return value.slice(value.lastIndexOf("/") + 1);
}

function repositoryCount(count: number) {
  return `${count} ${count === 1 ? "repository" : "repositories"}`;
}

function InvertToggle({ disabled, inverted, label, onChange }: { disabled: boolean; inverted: boolean; label: string; onChange: (inverted: boolean) => void }) {
  return (
    <button
      aria-label={`${inverted ? "Disable" : "Enable"} inverted ${label} filter`}
      aria-pressed={inverted}
      className="filter-invert-toggle"
      disabled={disabled}
      onClick={() => onChange(!inverted)}
      title={disabled ? "Add a filter value before inverting" : "Invert this filter"}
      type="button"
    >
      Invert
    </button>
  );
}

export function ValueFilterControl({
  column,
  filter,
  onChange,
  onInvert,
  options,
}: {
  column: string;
  filter?: ValueFilter;
  onChange: (values: DashboardValue[]) => void;
  onInvert: (inverted: boolean) => void;
  options: CountedValue[];
}) {
  const optionByToken = new Map(options.map(({ value }) => [valueToken(value), value]));

  return (
    <MultiSelect
      id={`value-filter-${controlId(column)}`}
      label={<code>{column}</code>}
      labelAction={<InvertToggle disabled={filter == null || filter.values.length === 0} inverted={filter?.inverted === true} label={column} onChange={onInvert} />}
      onChange={(tokens) => onChange([...tokens].flatMap((token) => (optionByToken.has(token) ? [optionByToken.get(token)] : [])) as DashboardValue[])}
      options={options.map(({ count, value }) => {
        const label = rawValueLabel(value);
        return {
          detail: column === REPOSITORIES ? undefined : repositoryCount(count),
          label: column === REPOSITORIES ? repositoryName(label) : label,
          value: valueToken(value),
        };
      })}
      placeholder={column === REPOSITORIES ? "Type to add repositories…" : "Type to add values…"}
      selected={new Set((filter?.values ?? []).map(valueToken))}
    />
  );
}

export function TextFilterControl({
  column,
  filter,
  onChange,
  onInvert,
  options,
}: {
  column: string;
  filter?: TextFilter;
  onChange: (query: string) => void;
  onInvert: (inverted: boolean) => void;
  options: CountedValue[];
}) {
  const query = filter?.query ?? "";
  const id = `text-filter-${controlId(column)}`;
  const {
    accept,
    activeIndex,
    activeOptionRef,
    onInputKeyDown,
    open,
    root,
    setActiveIndex,
    setOpen,
    visibleOptions: suggestions,
  } = useAutocomplete({
    limit: 8,
    onAccept: ({ label }) => onChange(label),
    options: options.map(({ count, value }) => ({ count, label: rawValueLabel(value), value })),
    query,
  });

  return (
    <div className="text-filter-control" ref={root}>
      <div className="filter-control-heading">
        <label htmlFor={id}>
          <code>{column}</code>
        </label>
        <InvertToggle disabled={filter == null || query.trim() === ""} inverted={filter?.inverted === true} label={column} onChange={onInvert} />
      </div>
      <div className="text-filter-search-control">
        <input
          aria-activedescendant={!open || activeIndex < 0 ? undefined : `${id}-suggestion-${activeIndex}`}
          aria-autocomplete="list"
          aria-controls={open ? `${id}-suggestions` : undefined}
          aria-expanded={open}
          aria-haspopup="listbox"
          autoComplete="off"
          id={id}
          onChange={(event) => {
            onChange(event.target.value);
            setOpen(event.target.value.trim() !== "");
          }}
          onFocus={() => {
            if (query.trim() !== "") setOpen(true);
          }}
          onKeyDown={onInputKeyDown}
          placeholder="Search values…"
          role="combobox"
          type="search"
          value={query}
        />
      </div>
      {open && (
        <div className="text-filter-suggestions" id={`${id}-suggestions`} role="listbox">
          {suggestions.length === 0 ? (
            <span className="multi-select-empty">No matching values</span>
          ) : (
            suggestions.map(({ count, label, value }, index) => (
              <button
                aria-selected={index === activeIndex}
                className={index === activeIndex ? "is-active" : undefined}
                id={`${id}-suggestion-${index}`}
                key={valueToken(value)}
                onClick={() => accept({ count, label, value })}
                onMouseDown={(event) => event.preventDefault()}
                onMouseEnter={() => setActiveIndex(index)}
                ref={index === activeIndex ? activeOptionRef : undefined}
                role="option"
                tabIndex={-1}
                type="button"
              >
                <span>{label}</span>
                <small>{repositoryCount(count)}</small>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
