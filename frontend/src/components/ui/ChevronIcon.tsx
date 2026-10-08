import { ChevronRightIcon } from 'lucide-react'

import { cn } from '@/lib/class-merge'

export const ChevronIcon = ({ className }: { className?: string }) => (
  <ChevronRightIcon
    aria-hidden="true"
    className={cn('size-4 flex-none origin-center text-primary opacity-80 transition duration-150', className)}
  />
)
