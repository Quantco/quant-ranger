import { ChevronIcon } from './ChevronIcon'
import { Checkbox } from './ui/checkbox'

type FieldSelectorProps = {
  codeLabels?: boolean
  emptyMessage?: string
  fields: string[]
  getFieldLabel?: (field: string) => string
  label: string
  onChange: (fields: Set<string>) => void
  selected: Set<string>
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
  const allSelected = fields.length > 0 && fields.every((field) => selected.has(field))
  const selectedCount = fields.filter((field) => selected.has(field)).length

  return (
    <details className="group m-0 grid gap-2 border-t border-border pt-3">
      <summary className="grid min-h-6 grid-cols-[1rem_minmax(0,1fr)_0.875rem] items-center gap-[0.4rem] list-none text-sm focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2 [&::-webkit-details-marker]:hidden">
        <ChevronIcon className="group-hover:text-foreground group-hover:opacity-100 group-open:rotate-90" />
        <span className="min-w-0 leading-tight">
          {label} ({selectedCount} of {fields.length})
        </span>
        <Checkbox
          aria-label={`Show all ${label.toLocaleLowerCase()}`}
          checked={allSelected}
          className="justify-self-center"
          disabled={fields.length === 0}
          onCheckedChange={(checked) => onChange(new Set(checked ? fields : []))}
          onClick={(event) => event.stopPropagation()}
          title={`Show all ${label.toLocaleLowerCase()}`}
        />
      </summary>
      {fields.length === 0 ? (
        <p className="mt-2 mb-0 text-sm text-muted-foreground">{emptyMessage}</p>
      ) : (
        <div className="mt-2 grid gap-[0.3rem]">
          {fields.map((field) => {
            const fieldLabel = getFieldLabel(field)
            return (
              <label className="flex min-w-0 items-center gap-[0.4rem] text-sm [overflow-wrap:anywhere]" key={field}>
                <Checkbox
                  checked={selected.has(field)}
                  onCheckedChange={(checked) => {
                    const next = new Set(selected)
                    if (checked) next.add(field)
                    else next.delete(field)
                    onChange(next)
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
