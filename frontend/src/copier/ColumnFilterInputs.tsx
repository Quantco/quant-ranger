import { useState } from 'react'

import { LabeledControl } from '../components/dashboard/LabeledControl'
import { MultiSelect } from '../components/dashboard/MultiSelect'
import { Button } from '../components/ui/Button'
import {
  Combobox,
  ComboboxChipsInput,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInputGroup,
  ComboboxItem,
  ComboboxList
} from '../components/ui/Combobox'
import { filterOptions } from '../lib/filter-options'
import { displayValue } from '../lib/value'
import { repositoryName } from './dashboard'
import type { CountedValue, DashboardValue, FilterValue } from './dashboard'
import type { FilterableDashboardColumn } from './dashboard-columns'
import type { DashboardFilterValue } from './dashboard-state'

const valueToken = (value: DashboardValue) => `${typeof value}:${String(value)}`
interface TextSuggestion {
  count: number
  label: string
  value: DashboardValue
}

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
      className="flex-none rounded-full px-1.5 py-0.5 text-xs/tight text-muted-foreground aria-pressed:border-primary aria-pressed:bg-primary aria-pressed:text-white"
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
  column: FilterableDashboardColumn
  filter: DashboardFilterValue | undefined
  onChange: (values: FilterValue[]) => void
  onInvert: (inverted: boolean) => void
  options: CountedValue[]
}) {
  const optionByToken = new Map(options.map(({ value }) => [valueToken(value), value]))
  const selectedValues = filter?.values ?? []
  const repository = column.kind === 'repository'

  return (
    <MultiSelect
      id={`value-filter-${controlId(column.id)}`}
      label={<code>{column.id}</code>}
      labelAction={
        <InvertToggle
          disabled={selectedValues.length === 0}
          inverted={filter?.inverted === true}
          label={column.id}
          onChange={onInvert}
        />
      }
      onChange={(tokens) =>
        onChange(
          tokens.flatMap((token) => {
            const value = optionByToken.get(token)
            return value === undefined ? [] : [value]
          })
        )
      }
      options={options.map(({ count, value }) => {
        const label = displayValue(value)
        const token = valueToken(value)
        if (repository) return { label: repositoryName(label), value: token }
        return { detail: repositoryCount(count), label, value: token }
      })}
      placeholder={repository ? 'Type to add repositories…' : 'Type to add values…'}
      selected={selectedValues.map(valueToken)}
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
  column: FilterableDashboardColumn
  filter: DashboardFilterValue | undefined
  onChange: (query: string) => void
  onInvert: (inverted: boolean) => void
  options: CountedValue[]
}) {
  const query = String(filter?.values[0] ?? '')
  const id = `text-filter-${controlId(column.id)}`
  const [open, setOpen] = useState(false)
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
      <LabeledControl
        action={
          <InvertToggle
            disabled={filter == null || query.trim() === ''}
            inverted={filter?.inverted === true}
            label={column.id}
            onChange={onInvert}
          />
        }
        htmlFor={id}
        label={<code>{column.id}</code>}
      >
        <ComboboxInputGroup>
          <ComboboxChipsInput
            id={id}
            onFocus={() => {
              if (query.trim() !== '') setOpen(true)
            }}
            placeholder="Search values…"
          />
        </ComboboxInputGroup>
        <ComboboxContent>
          {suggestions.length === 0 ? (
            <ComboboxEmpty>No matching values</ComboboxEmpty>
          ) : (
            <ComboboxList>
              {suggestions.map((option) => (
                <ComboboxItem key={valueToken(option.value)} showIndicator={false} value={option}>
                  <span className="min-w-0 flex-1 wrap-anywhere">{option.label}</span>
                  <small className="text-sm text-muted-foreground">{repositoryCount(option.count)}</small>
                </ComboboxItem>
              ))}
            </ComboboxList>
          )}
        </ComboboxContent>
      </LabeledControl>
    </Combobox>
  )
}
