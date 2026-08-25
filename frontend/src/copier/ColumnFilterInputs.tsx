import { useRef, useState } from 'react'

import { filterOptions } from '../lib/filter-options'
import { MultiSelect } from '../components/MultiSelect'
import { Button } from '../components/ui/button'
import {
  Combobox,
  ComboboxChipsInput,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxItem,
  ComboboxList
} from '../components/ui/combobox'
import { displayValue } from '../lib/value'
import { REPOSITORIES, repositoryName } from './dashboard'
import type { CountedValue, DashboardValue, FilterValue, TextFilter, ValueFilter } from './dashboard'

const valueToken = (value: DashboardValue) => `${typeof value}:${String(value)}`
type TextSuggestion = { count: number; label: string; value: DashboardValue }

function controlId(column: string) {
  return encodeURIComponent(column)
}

function repositoryCount(count: number) {
  return `${count} ${count === 1 ? 'repository' : 'repositories'}`
}

function InvertToggle({
  disabled,
  inverted,
  label,
  onChange
}: {
  disabled: boolean
  inverted: boolean
  label: string
  onChange: (inverted: boolean) => void
}) {
  return (
    <Button
      aria-label={`${inverted ? 'Disable' : 'Enable'} inverted ${label} filter`}
      aria-pressed={inverted}
      className="flex-none rounded-full px-[0.4rem] py-[0.08rem] text-xs leading-[1.35] text-muted-foreground aria-pressed:border-primary aria-pressed:bg-primary aria-pressed:text-white"
      disabled={disabled}
      onClick={() => onChange(!inverted)}
      title={disabled ? 'Add a filter value before inverting' : 'Invert this filter'}
      type="button"
      variant="outline"
    >
      Invert
    </Button>
  )
}

export function ValueFilterInput({
  column,
  filter,
  onChange,
  onInvert,
  options
}: {
  column: string
  filter?: ValueFilter
  onChange: (values: FilterValue[]) => void
  onInvert: (inverted: boolean) => void
  options: CountedValue[]
}) {
  const optionByToken = new Map(options.map(({ value }) => [valueToken(value), value]))

  return (
    <MultiSelect
      id={`value-filter-${controlId(column)}`}
      label={<code>{column}</code>}
      labelAction={
        <InvertToggle
          disabled={filter == null || filter.values.length === 0}
          inverted={filter?.inverted === true}
          label={column}
          onChange={onInvert}
        />
      }
      onChange={(tokens) =>
        onChange(
          [...tokens].flatMap((token) => {
            const value = optionByToken.get(token)
            return value === undefined ? [] : [value]
          })
        )
      }
      options={options.map(({ count, value }) => {
        const label = displayValue(value)
        return {
          detail: column === REPOSITORIES ? undefined : repositoryCount(count),
          label: column === REPOSITORIES ? repositoryName(label) : label,
          value: valueToken(value)
        }
      })}
      placeholder={column === REPOSITORIES ? 'Type to add repositories…' : 'Type to add values…'}
      selected={new Set((filter?.values ?? []).map(valueToken))}
    />
  )
}

export function TextFilterInput({
  column,
  filter,
  onChange,
  onInvert,
  options
}: {
  column: string
  filter?: TextFilter
  onChange: (query: string) => void
  onInvert: (inverted: boolean) => void
  options: CountedValue[]
}) {
  const query = filter?.query ?? ''
  const id = `text-filter-${controlId(column)}`
  const [open, setOpen] = useState(false)
  const anchor = useRef<HTMLDivElement>(null)
  const suggestionOptions = options.map(({ count, value }) => ({ count, label: displayValue(value), value }))
  const suggestions = filterOptions(suggestionOptions, query, 8)

  return (
    <Combobox<TextSuggestion>
      filteredItems={suggestions}
      inputValue={query}
      isItemEqualToValue={(option, value) => valueToken(option.value) === valueToken(value.value)}
      itemToStringLabel={({ label }) => label}
      items={suggestionOptions}
      onInputValueChange={(nextQuery) => {
        onChange(nextQuery)
        setOpen(nextQuery.trim() !== '')
      }}
      onOpenChange={(nextOpen) => setOpen(nextOpen && query.trim() !== '')}
      onValueChange={(option, details) => {
        if (option != null) {
          details.cancel()
          onChange(option.label)
          setOpen(false)
        }
      }}
      open={open}
      value={null}
    >
      <div className="grid min-w-0 gap-1">
        <div className="flex min-w-0 items-center justify-between gap-2">
          <label className="min-w-0 text-sm leading-tight font-semibold [overflow-wrap:anywhere]" htmlFor={id}>
            <code>{column}</code>
          </label>
          <InvertToggle
            disabled={filter == null || query.trim() === ''}
            inverted={filter?.inverted === true}
            label={column}
            onChange={onInvert}
          />
        </div>
        <div
          className="flex min-h-[2.35rem] rounded-small border border-solid border-border bg-white focus-within:outline-2 focus-within:outline-ring focus-within:outline-offset-1"
          ref={anchor}
        >
          <ComboboxChipsInput
            id={id}
            onFocus={() => {
              if (query.trim() !== '') setOpen(true)
            }}
            placeholder="Search values…"
          />
        </div>
        <ComboboxContent anchor={anchor}>
          {suggestions.length === 0 ? (
            <ComboboxEmpty>No matching values</ComboboxEmpty>
          ) : (
            <ComboboxList>
              {suggestions.map((option) => (
                <ComboboxItem key={valueToken(option.value)} showIndicator={false} value={option}>
                  <span className="min-w-0 [overflow-wrap:anywhere]">{option.label}</span>
                  <small className="text-sm text-muted-foreground">{repositoryCount(option.count)}</small>
                </ComboboxItem>
              ))}
            </ComboboxList>
          )}
        </ComboboxContent>
      </div>
    </Combobox>
  )
}
