import { Checkbox as CheckboxPrimitive } from '@base-ui/react/checkbox'
import { CheckIcon, MinusIcon } from 'lucide-react'

import { cn } from '@/lib/utils'

function Checkbox({ className, indeterminate = false, ...props }: CheckboxPrimitive.Root.Props) {
  return (
    <CheckboxPrimitive.Root
      className={cn(
        'relative inline-grid size-3.5 shrink-0 cursor-pointer place-items-center rounded-[0.15rem] border border-solid border-primary-light bg-white text-white outline-none data-checked:border-primary data-checked:bg-primary data-indeterminate:border-primary data-indeterminate:bg-primary disabled:cursor-default disabled:opacity-45 focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2',
        className
      )}
      data-slot="checkbox"
      indeterminate={indeterminate}
      {...props}
    >
      <CheckboxPrimitive.Indicator className="grid place-items-center" data-slot="checkbox-indicator">
        {indeterminate ? (
          <MinusIcon aria-hidden="true" className="size-3" strokeWidth={3} />
        ) : (
          <CheckIcon aria-hidden="true" className="size-3" strokeWidth={3} />
        )}
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  )
}

export { Checkbox }
