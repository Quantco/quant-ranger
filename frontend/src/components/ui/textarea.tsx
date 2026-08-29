import type { ComponentProps } from 'react'

import { cn } from '@/lib/utils'

function Textarea({ className, ...props }: ComponentProps<'textarea'>) {
  return (
    <textarea
      className={cn(
        'min-h-20 w-full resize-y rounded-md border border-solid border-border bg-white px-2.5 py-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-45',
        className
      )}
      data-slot="textarea"
      {...props}
    />
  )
}

export { Textarea }
