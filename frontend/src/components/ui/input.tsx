import type { ComponentProps } from 'react'

import { cn } from '@/lib/utils'

function Input({ className, type, ...props }: ComponentProps<'input'>) {
  return (
    <input
      className={cn(
        'h-10 w-full min-w-0 rounded-small border border-solid border-border bg-white px-2.5 py-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-45',
        className
      )}
      data-slot="input"
      type={type}
      {...props}
    />
  )
}

export { Input }
