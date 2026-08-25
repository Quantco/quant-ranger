import type { ReactNode } from 'react'

import { Button } from './ui/button'

export function DashboardSidebarShell({
  children,
  headingId,
  onReset,
  title
}: {
  children: ReactNode
  headingId: string
  onReset: () => void
  title: string
}) {
  return (
    <aside
      aria-labelledby={headingId}
      className="grid gap-3 rounded-medium border border-border bg-muted p-4 min-[1101px]:sticky min-[1101px]:top-4 min-[1101px]:max-h-[calc(100vh-2rem)] min-[1101px]:overflow-auto"
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
