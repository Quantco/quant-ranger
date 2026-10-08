import type { ComponentProps } from 'react'

import { cn } from '@/lib/class-merge'

const Table = ({
  className,
  containerClassName,
  ...props
}: ComponentProps<'table'> & { containerClassName?: string }) => (
  <div
    className={cn('max-h-screen w-full overflow-auto rounded-md border border-solid border-border', containerClassName)}
    data-slot="table-container"
  >
    <table
      className={cn('w-max min-w-full border-separate border-spacing-0 text-sm', className)}
      data-slot="table"
      {...props}
    />
  </div>
)

const TableHeader = ({ className, ...props }: ComponentProps<'thead'>) => (
  <thead className={className} data-slot="table-header" {...props} />
)

const TableBody = ({ className, ...props }: ComponentProps<'tbody'>) => (
  <tbody className={cn('divide-y divide-border', className)} data-slot="table-body" {...props} />
)

const TableRow = ({ className, ...props }: ComponentProps<'tr'>) => (
  <tr
    className={cn('hover:outline-2 hover:-outline-offset-2 hover:outline-zinc-400', className)}
    data-slot="table-row"
    {...props}
  />
)

const TableHead = ({ className, ...props }: ComponentProps<'th'>) => (
  <th
    className={cn(
      'sticky top-0 z-20 border-0 border-b border-solid border-border bg-muted px-2 py-1.5 text-left font-semibold whitespace-nowrap text-zinc-700',
      className
    )}
    data-slot="table-head"
    {...props}
  />
)

const TableCell = ({ className, ...props }: ComponentProps<'td'>) => (
  <td className={cn('border-0 px-2 py-1.5 text-left whitespace-nowrap', className)} data-slot="table-cell" {...props} />
)

export { Table, TableBody, TableCell, TableHead, TableHeader, TableRow }
