import type { ReactNode } from 'react'

import { cn } from '@/lib/class-merge'
import { Button } from '@/components/ui/Button'

export function DashboardSidebarShell({
  children,
  className,
  headingId,
  onReset,
  title
}: {
  children: ReactNode
  className: string
  headingId: string
  onReset: () => void
  title: string
}) {
  return (
    <aside
      aria-labelledby={headingId}
      className={cn('grid gap-3 rounded-lg border border-border bg-muted p-4 lg:sticky lg:top-4', className)}
    >
      <h2 className="m-0" id={headingId}>
        {title}
      </h2>
      <Button className="justify-self-start" onClick={onReset} type="button" variant="link">
        Reset filters
      </Button>
      {children}
    </aside>
  )
}
