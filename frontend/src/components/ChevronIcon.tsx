import { ChevronRightIcon } from 'lucide-react'

import { cn } from '@/lib/utils'

export function ChevronIcon({ className }: { className?: string }) {
  return (
    <ChevronRightIcon
      aria-hidden="true"
      className={cn(
        'size-4 flex-none origin-center p-[0.08rem] text-primary opacity-80 transition-[color,opacity,transform] duration-[120ms]',
        className
      )}
    />
  )
}
