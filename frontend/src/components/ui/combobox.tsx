import { Combobox as ComboboxPrimitive } from '@base-ui/react/combobox'
import { CheckIcon } from 'lucide-react'

import { cn } from '@/lib/utils'

const Combobox = ComboboxPrimitive.Root
const ComboboxChip = ComboboxPrimitive.Chip
const ComboboxChipRemove = ComboboxPrimitive.ChipRemove
const ComboboxClear = ComboboxPrimitive.Clear

function ComboboxInputGroup({ className, ...props }: ComboboxPrimitive.InputGroup.Props) {
  return (
    <ComboboxPrimitive.InputGroup
      className={cn(
        'flex min-h-10 rounded-md border border-solid border-border bg-white focus-within:outline-2 focus-within:outline-ring focus-within:outline-offset-1',
        className
      )}
      data-slot="combobox-input-group"
      {...props}
    />
  )
}

function ComboboxValue(props: ComboboxPrimitive.Value.Props) {
  return <ComboboxPrimitive.Value data-slot="combobox-value" {...props} />
}

function ComboboxChips({ className, ...props }: ComboboxPrimitive.Chips.Props) {
  return (
    <ComboboxPrimitive.Chips
      className={cn('flex min-w-0 flex-1 flex-wrap items-center gap-1 p-1', className)}
      data-slot="combobox-chips"
      {...props}
    />
  )
}

function ComboboxChipsInput({ className, ...props }: ComboboxPrimitive.Input.Props) {
  return (
    <ComboboxPrimitive.Input
      className={cn('min-w-24 flex-1 border-0 bg-transparent px-1 py-0.5 text-sm outline-none', className)}
      data-slot="combobox-chip-input"
      type="text"
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
            'grid max-h-(--available-height) w-(--anchor-width) gap-2 overflow-hidden rounded-md border border-solid border-border bg-white p-2 text-foreground shadow-lg outline-none',
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
        'flex w-full cursor-pointer items-center gap-2 rounded-sm py-1.5 text-left text-xs outline-none select-none hover:bg-muted data-highlighted:bg-primary-subtle data-disabled:pointer-events-none data-disabled:opacity-45',
        showIndicator ? 'px-1' : 'px-2',
        className
      )}
      data-slot="combobox-item"
      {...props}
    >
      {showIndicator && (
        <span
          aria-hidden="true"
          className="grid size-3.5 flex-none place-items-center rounded-sm border border-solid border-primary-light text-primary"
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
}
