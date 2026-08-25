import { Combobox as ComboboxPrimitive } from '@base-ui/react/combobox'
import { CheckIcon } from 'lucide-react'

import { cn } from '@/lib/utils'

const Combobox = ComboboxPrimitive.Root

function ComboboxValue(props: ComboboxPrimitive.Value.Props) {
  return <ComboboxPrimitive.Value data-slot="combobox-value" {...props} />
}

function ComboboxChips({ className, ...props }: ComboboxPrimitive.Chips.Props) {
  return (
    <ComboboxPrimitive.Chips
      className={cn('flex min-w-0 flex-1 flex-wrap items-center gap-1 p-[0.3rem]', className)}
      data-slot="combobox-chips"
      {...props}
    />
  )
}

function ComboboxChipsInput({ className, ...props }: ComboboxPrimitive.Input.Props) {
  return (
    <ComboboxPrimitive.Input
      className={cn(
        'min-w-[5.5rem] flex-[1_1_7rem] border-0 bg-transparent px-1 py-[0.15rem] text-sm outline-none [&::-webkit-search-cancel-button]:appearance-none',
        className
      )}
      data-slot="combobox-chip-input"
      type="search"
      {...props}
    />
  )
}

function ComboboxContent({
  align = 'start',
  alignOffset = 0,
  anchor,
  className,
  side = 'bottom',
  sideOffset = 4,
  ...props
}: ComboboxPrimitive.Popup.Props &
  Pick<ComboboxPrimitive.Positioner.Props, 'align' | 'alignOffset' | 'anchor' | 'side' | 'sideOffset'>) {
  return (
    <ComboboxPrimitive.Portal>
      <ComboboxPrimitive.Positioner
        align={align}
        alignOffset={alignOffset}
        anchor={anchor}
        className="isolate z-50"
        side={side}
        sideOffset={sideOffset}
      >
        <ComboboxPrimitive.Popup
          className={cn(
            'grid max-h-[min(22rem,var(--available-height))] w-[var(--anchor-width)] gap-2 overflow-hidden rounded-small border border-solid border-border bg-white p-2 text-foreground shadow-[0_8px_20px_rgb(15_23_42/10%)] outline-none',
            className
          )}
          data-slot="combobox-content"
          initialFocus={false}
          {...props}
        />
      </ComboboxPrimitive.Positioner>
    </ComboboxPrimitive.Portal>
  )
}

function ComboboxList({ className, ...props }: ComboboxPrimitive.List.Props) {
  return (
    <ComboboxPrimitive.List
      className={cn('grid max-h-56 overflow-auto overscroll-contain', className)}
      data-slot="combobox-list"
      {...props}
    />
  )
}

function ComboboxItem({
  children,
  className,
  showIndicator = true,
  ...props
}: ComboboxPrimitive.Item.Props & { showIndicator?: boolean }) {
  return (
    <ComboboxPrimitive.Item
      className={cn(
        'grid w-full cursor-pointer items-center gap-2 rounded-sm px-1 py-[0.35rem] text-left text-xs outline-none select-none hover:bg-muted data-highlighted:bg-primary-subtle data-disabled:pointer-events-none data-disabled:opacity-45',
        showIndicator ? 'grid-cols-[auto_minmax(0,1fr)_auto]' : 'grid-cols-[minmax(0,1fr)_auto] px-2',
        className
      )}
      data-slot="combobox-item"
      {...props}
    >
      {showIndicator && (
        <span
          aria-hidden="true"
          className="grid size-3.5 place-items-center rounded-[0.15rem] border border-solid border-primary-light text-primary"
        >
          <ComboboxPrimitive.ItemIndicator className="grid place-items-center">
            <CheckIcon className="size-3" strokeWidth={3} />
          </ComboboxPrimitive.ItemIndicator>
        </span>
      )}
      {children}
    </ComboboxPrimitive.Item>
  )
}

function ComboboxEmpty({ className, ...props }: ComboboxPrimitive.Empty.Props) {
  return (
    <ComboboxPrimitive.Empty
      className={cn('p-2 text-xs text-muted-foreground', className)}
      data-slot="combobox-empty"
      {...props}
    />
  )
}

export {
  Combobox,
  ComboboxChips,
  ComboboxChipsInput,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxItem,
  ComboboxList,
  ComboboxValue
}
