import { useRef, useState, type ReactNode } from 'react'

import { filterOptions } from '../lib/filter-options'
import { Button } from './ui/button'
import {
  Combobox,
  ComboboxChips,
  ComboboxChipsInput,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxItem,
  ComboboxList,
  ComboboxValue
} from './ui/combobox'

export type AutocompleteOption = {
  detail?: string
  label: string
  value: string
}

type MultiSelectProps = {
  codeLabels?: boolean
  id: string
  label: ReactNode
  labelAction?: ReactNode
  onChange: (selected: Set<string>) => void
  options: AutocompleteOption[]
  placeholder: string
  selected: Set<string>
}

export function MultiSelect({
  codeLabels = false,
  id,
  label,
  labelAction,
  onChange,
  options,
  placeholder,
  selected
}: MultiSelectProps) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const anchor = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLInputElement>(null)
  const selectedOptions = options.filter(({ value }) => selected.has(value))
  const visibleOptions = filterOptions(options, query)
  const allVisibleSelected = visibleOptions.length > 0 && visibleOptions.every(({ value }) => selected.has(value))

  const toggleOption = (value: string) => {
    const next = new Set(selected)
    if (next.has(value)) next.delete(value)
    else next.add(value)
    onChange(next)
  }

  const toggleVisibleOptions = () => {
    const next = new Set(selected)
    for (const { value } of visibleOptions) {
      if (allVisibleSelected) next.delete(value)
      else next.add(value)
    }
    onChange(next)
  }

  return (
    <div className="grid min-w-0 gap-1">
      <div className="flex min-w-0 items-center justify-between gap-2">
        <span className="min-w-0 text-sm leading-tight font-semibold [overflow-wrap:anywhere]" id={`${id}-label`}>
          {label}
        </span>
        {labelAction}
      </div>
      <Combobox
        filteredItems={visibleOptions}
        inputValue={query}
        isItemEqualToValue={(option, value) => option.value === value.value}
        itemToStringLabel={(option) => option.label}
        itemToStringValue={(option) => option.value}
        items={options}
        multiple
        onInputValueChange={setQuery}
        onOpenChange={(nextOpen) => {
          setOpen(nextOpen)
          if (!nextOpen) setQuery('')
        }}
        onValueChange={(nextSelected, details) => {
          if (details.reason === 'item-press') details.cancel()
          onChange(new Set(nextSelected.map(({ value }) => value)))
          setQuery('')
          setOpen(true)
          requestAnimationFrame(() => input.current?.focus())
        }}
        open={open}
        value={selectedOptions}
      >
        <div
          className="flex min-h-[2.35rem] rounded-small border border-solid border-border bg-white focus-within:outline-2 focus-within:outline-ring focus-within:outline-offset-1"
          ref={anchor}
        >
          <ComboboxChips onClick={() => input.current?.focus()}>
            <ComboboxValue>
              {(values: AutocompleteOption[]) => (
                <>
                  {values.map(({ label: optionLabel, value }) => (
                    <Button
                      aria-label={`Remove ${optionLabel}`}
                      className="max-w-full gap-1 rounded-[0.3rem] border-primary-light bg-primary-subtle px-[0.4rem] py-[0.18rem] text-xs leading-[1.3] font-normal hover:border-primary hover:bg-primary-subtle"
                      key={value}
                      onClick={(event) => {
                        event.stopPropagation()
                        toggleOption(value)
                        input.current?.focus()
                      }}
                      size="sm"
                      type="button"
                      variant="outline"
                    >
                      {codeLabels ? (
                        <code className="min-w-0 overflow-hidden text-ellipsis">{optionLabel}</code>
                      ) : (
                        optionLabel
                      )}
                      <span aria-hidden="true">×</span>
                    </Button>
                  ))}
                  <ComboboxChipsInput
                    aria-labelledby={`${id}-label`}
                    onFocus={() => setOpen(true)}
                    placeholder={selectedOptions.length === 0 ? placeholder : 'Search…'}
                    ref={input}
                  />
                </>
              )}
            </ComboboxValue>
          </ComboboxChips>
          <Button
            aria-label={`Clear ${typeof label === 'string' ? label.toLocaleLowerCase() : 'selected values'}`}
            className="w-[2.35rem] flex-none rounded-l-none border-0 border-l border-solid border-l-border text-base disabled:opacity-35"
            disabled={selected.size === 0 && query === ''}
            onClick={() => {
              onChange(new Set())
              setQuery('')
              setOpen(false)
            }}
            size="icon"
            title="Clear selection"
            type="button"
            variant="ghost"
          >
            <span aria-hidden="true">×</span>
          </Button>
        </div>
        <ComboboxContent anchor={anchor} aria-labelledby={`${id}-label`}>
          <div className="flex gap-3" onMouseDown={(event) => event.preventDefault()}>
            <Button
              className="text-xs"
              disabled={visibleOptions.length === 0}
              onClick={toggleVisibleOptions}
              type="button"
              variant="link"
            >
              {allVisibleSelected ? 'Clear shown' : 'Select shown'}
            </Button>
            {selected.size > 0 && (
              <Button className="text-xs" onClick={() => onChange(new Set())} type="button" variant="link">
                Clear all
              </Button>
            )}
          </div>
          {visibleOptions.length === 0 ? (
            <ComboboxEmpty>No matching options</ComboboxEmpty>
          ) : (
            <ComboboxList>
              {visibleOptions.map((option) => (
                <ComboboxItem key={option.value} value={option}>
                  <span className="min-w-0 [overflow-wrap:anywhere]">
                    {codeLabels ? <code>{option.label}</code> : option.label}
                  </span>
                  {option.detail != null && <small className="text-xs text-muted-foreground">{option.detail}</small>}
                </ComboboxItem>
              ))}
            </ComboboxList>
          )}
        </ComboboxContent>
      </Combobox>
    </div>
  )
}
