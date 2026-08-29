import { ChevronIcon } from './ChevronIcon'
import { Checkbox } from './ui/checkbox'

interface FieldSelectorProps {
  codeLabels?: boolean
  emptyMessage?: string
  fields: string[]
  getFieldLabel?: (field: string) => string
  label: string
  onChange: (fields: string[]) => void
  selected: string[]
}

export function FieldSelector({
  codeLabels = true,
  emptyMessage = 'No fields available.',
  fields,
  getFieldLabel = (field) => field,
  label,
  onChange,
  selected
}: FieldSelectorProps) {
  const allSelected = fields.length > 0 && fields.every((field) => selected.includes(field))
  const selectedCount = fields.filter((field) => selected.includes(field)).length

  return (
    <details className="group m-0 grid gap-2 border-t border-border pt-3">
      <summary className="flex min-h-6 items-center gap-1.5 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
        <ChevronIcon className="group-open:rotate-90 group-hover:text-foreground group-hover:opacity-100" />
        <span className="min-w-0 flex-1 leading-tight">
          {label} ({selectedCount} of {fields.length})
        </span>
        <Checkbox
          aria-label={`Show all ${label.toLocaleLowerCase()}`}
          checked={allSelected}
          className="justify-self-center"
          disabled={fields.length === 0}
          onCheckedChange={(checked) => onChange(checked ? fields : [])}
          onClick={(event) => event.stopPropagation()}
          title={`Show all ${label.toLocaleLowerCase()}`}
        />
      </summary>
      {fields.length === 0 ? (
        <p className="mt-2 mb-0 text-sm text-muted-foreground">{emptyMessage}</p>
      ) : (
        <div className="mt-2 grid gap-1">
          {fields.map((field) => {
            const fieldLabel = getFieldLabel(field)
            return (
              <label className="flex min-w-0 items-center gap-1.5 text-sm wrap-anywhere" key={field}>
                <Checkbox
                  checked={selected.includes(field)}
                  onCheckedChange={(checked) => {
                    onChange(
                      checked ? [...selected, field] : selected.filter((selectedField) => selectedField !== field)
                    )
                  }}
                />
                {codeLabels ? <code>{fieldLabel}</code> : fieldLabel}
              </label>
            )
          })}
        </div>
      )}
    </details>
  )
}
