import { useRef, useState, type ReactNode } from "react";

import { useAutocomplete } from "./useAutocomplete";

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

export function MultiSelect({ codeLabels = false, id, label, labelAction, onChange, options, placeholder, selected }: MultiSelectProps) {
  const [query, setQuery] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const selectedOptions = options.filter(({ value }) => selected.has(value));
  const { activeIndex, close, onInputKeyDown, open, root, setActiveIndex, setOpen, visibleOptions } = useAutocomplete({
    closeOnAccept: false,
    onAccept: ({ value }) => {
      toggleOption(value);
      setQuery("");
    },
    onClose: () => setQuery(""),
    options,
    query,
  });
  const allVisibleSelected = visibleOptions.length > 0 && visibleOptions.every(({ value }) => selected.has(value));

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
            aria-activedescendant={!open || activeIndex < 0 ? undefined : `${id}-option-${activeIndex}`}
            aria-autocomplete="list"
            aria-controls={open ? `${id}-options` : undefined}
            aria-expanded={open}
            aria-haspopup="listbox"
            aria-labelledby={`${id}-label`}
            autoComplete="off"
            className="multi-select-search"
            onChange={(event) => {
              setQuery(event.target.value);
              setOpen(true);
            }}
            onFocus={() => setOpen(true)}
            onKeyDown={(event) => {
              if (!onInputKeyDown(event) && event.key === "Backspace" && query === "" && selectedOptions.length > 0) {
                toggleOption(selectedOptions.at(-1)!.value);
              }
            }}
            placeholder={selectedOptions.length === 0 ? placeholder : "Search…"}
            ref={input}
            role="combobox"
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
            close();
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
          <div aria-labelledby={`${id}-label`} aria-multiselectable="true" className="multi-select-options" id={`${id}-options`} role="listbox">
            {visibleOptions.length === 0 ? (
              <span className="multi-select-empty">No matching options</span>
            ) : (
              visibleOptions.map(({ detail, label: optionLabel, value }, index) => (
                <div
                  aria-selected={selected.has(value)}
                  className={activeIndex === index ? "is-active" : undefined}
                  id={`${id}-option-${index}`}
                  key={value}
                  onClick={() => toggleOption(value)}
                  onMouseDown={(event) => event.preventDefault()}
                  onMouseEnter={() => setActiveIndex(index)}
                  role="option"
                >
                  <span aria-hidden="true" className="multi-select-option-check">
                    {selected.has(value) ? "✓" : ""}
                  </span>
                  <span>{codeLabels ? <code>{optionLabel}</code> : optionLabel}</span>
                  {detail != null && <small>{detail}</small>}
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
