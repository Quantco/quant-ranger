import { Button as ButtonPrimitive } from '@base-ui/react/button'
import { cva, type VariantProps } from 'class-variance-authority'

import { cn } from '@/lib/class-merge'

const buttonVariants = cva(
  'inline-flex shrink-0 cursor-pointer items-center justify-center rounded-md border-solid font-semibold whitespace-nowrap focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:pointer-events-none disabled:cursor-default disabled:opacity-45',
  {
    variants: {
      variant: {
        default: 'border border-primary bg-primary px-2.5 py-1.5 text-sm text-zinc-50 hover:bg-slate-800',
        secondary:
          'border border-border bg-white px-2.5 py-1.5 text-sm text-foreground hover:border-primary-light hover:bg-primary-subtle',
        outline:
          'border border-border bg-white px-2.5 py-1.5 text-sm text-foreground hover:border-primary-light hover:bg-primary-subtle',
        ghost: 'border-0 bg-transparent text-muted-foreground hover:bg-muted hover:text-foreground',
        link: 'w-fit border-0 bg-transparent p-0 text-sm text-primary hover:underline'
      },
      size: {
        default: '',
        sm: 'px-2 py-1 text-sm',
        icon: 'size-10 p-0',
        'icon-sm': 'size-7 p-0'
      }
    },
    defaultVariants: {
      variant: 'default',
      size: 'default'
    }
  }
)

function Button({ className, size, variant, ...props }: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  return <ButtonPrimitive className={cn(buttonVariants({ className, size, variant }))} data-slot="button" {...props} />
}

export { Button }
