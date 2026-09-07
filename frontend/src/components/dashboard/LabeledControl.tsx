import type { ReactNode } from 'react'

interface LabeledControlProps {
  action?: ReactNode
  children: ReactNode
  htmlFor: string
  label: ReactNode
}

export function LabeledControl({ action, children, htmlFor, label }: LabeledControlProps) {
  return (
    <div className="grid min-w-0 gap-1">
      <div className="flex min-w-0 items-center justify-between gap-2">
        <label className="min-w-0 text-sm/tight font-semibold wrap-anywhere" htmlFor={htmlFor} id={`${htmlFor}-label`}>
          {label}
        </label>
        {action}
      </div>
      {children}
    </div>
  )
}
