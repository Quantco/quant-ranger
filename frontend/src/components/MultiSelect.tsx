import { XIcon } from 'lucide-react'
import type { ReactNode } from 'react'

import {
  Combobox,
  ComboboxChip,
  ComboboxChipRemove,
  ComboboxChips,
  ComboboxChipsInput,
  ComboboxClear,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInputGroup,
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
  onChange: (selected: string[]) => void
  options: AutocompleteOption[]
  placeholder: string
  selected: string[]
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
  const selectedOptions = options.filter(({ value }) => selected.includes(value))

  return (
    <div className="grid min-w-0 gap-1">
      <div className="flex min-w-0 items-center justify-between gap-2">
        <span className="min-w-0 wrap-anywhere text-sm leading-tight font-semibold" id={`${id}-label`}>
          {label}
        </span>
        {labelAction}
      </div>
      <Combobox
        items={options}
        multiple
        onValueChange={(nextSelected) => onChange(nextSelected.map(({ value }) => value))}
        value={selectedOptions}
      >
        <ComboboxInputGroup>
          <ComboboxChips>
            <ComboboxValue>
              {(values: AutocompleteOption[]) => (
                <>
                  {values.map(({ label: optionLabel, value }) => (
                    <ComboboxChip
                      aria-label={optionLabel}
                      className="flex max-w-full items-center gap-1 rounded-md border border-primary-light bg-primary-subtle px-1.5 py-0.5 text-xs leading-tight font-normal"
                      key={value}
                    >
                      {codeLabels ? (
                        <code className="min-w-0 overflow-hidden text-ellipsis">{optionLabel}</code>
                      ) : (
                        optionLabel
                      )}
                      <ComboboxChipRemove
                        aria-label={`Remove ${optionLabel}`}
                        className="grid size-4 flex-none place-items-center rounded-sm border-0 bg-transparent p-0 text-muted-foreground hover:bg-muted hover:text-foreground"
                      >
                        <XIcon aria-hidden="true" className="size-3" />
                      </ComboboxChipRemove>
                    </ComboboxChip>
                  ))}
                  <ComboboxChipsInput
                    aria-labelledby={`${id}-label`}
                    placeholder={values.length === 0 ? placeholder : 'Search…'}
                  />
                </>
              )}
            </ComboboxValue>
          </ComboboxChips>
          <ComboboxClear
            aria-label={`Clear ${typeof label === 'string' ? label.toLocaleLowerCase() : 'selected values'}`}
            className="grid w-10 flex-none self-stretch place-items-center rounded-r-md border-0 border-l border-solid border-l-border bg-transparent p-0 text-muted-foreground hover:bg-muted hover:text-foreground"
            title="Clear selection"
          >
            <XIcon aria-hidden="true" className="size-4" />
          </ComboboxClear>
        </ComboboxInputGroup>
        <ComboboxContent aria-labelledby={`${id}-label`}>
          <ComboboxEmpty>No matching options</ComboboxEmpty>
          <ComboboxList>
            {(option: AutocompleteOption) => (
              <ComboboxItem key={option.value} value={option}>
                <span className="min-w-0 flex-1 wrap-anywhere">
                  {codeLabels ? <code>{option.label}</code> : option.label}
                </span>
                {option.detail != null && <small className="text-xs text-muted-foreground">{option.detail}</small>}
              </ComboboxItem>
            )}
          </ComboboxList>
        </ComboboxContent>
      </Combobox>
    </div>
  )
}
