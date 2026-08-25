import type { ComponentProps } from 'react'

import { cn } from '@/lib/utils'

function Table({ className, containerClassName, ...props }: ComponentProps<'table'> & { containerClassName?: string }) {
  return (
    <div
      className={cn(
        'max-h-[72vh] w-full overflow-auto rounded-small border border-solid border-border',
        containerClassName
      )}
      data-slot="table-container"
    >
      <table
        className={cn('w-max min-w-full border-separate border-spacing-0 text-sm', className)}
        data-slot="table"
        {...props}
      />
    </div>
  )
}

function TableHeader({ className, ...props }: ComponentProps<'thead'>) {
  return <thead className={className} data-slot="table-header" {...props} />
}

function TableBody({ className, ...props }: ComponentProps<'tbody'>) {
  return <tbody className={cn('[&_tr:last-child_td]:border-b-0', className)} data-slot="table-body" {...props} />
}

function TableRow({ className, ...props }: ComponentProps<'tr'>) {
  return (
    <tr
      className={cn('hover:outline-2 hover:-outline-offset-2 hover:outline-[#a1a1aa]', className)}
      data-slot="table-row"
      {...props}
    />
  )
}

function TableHead({ className, ...props }: ComponentProps<'th'>) {
  return (
    <th
      className={cn(
        'sticky top-0 z-[2] border-0 border-b border-solid border-border bg-muted px-[0.55rem] py-[0.4rem] text-left font-semibold whitespace-nowrap text-zinc-700',
        className
      )}
      data-slot="table-head"
      {...props}
    />
  )
}

function TableCell({ className, ...props }: ComponentProps<'td'>) {
  return (
    <td
      className={cn(
        'border-0 border-b border-solid border-border px-[0.55rem] py-[0.4rem] text-left whitespace-nowrap',
        className
      )}
      data-slot="table-cell"
      {...props}
    />
  )
}

export { Table, TableBody, TableCell, TableHead, TableHeader, TableRow }
