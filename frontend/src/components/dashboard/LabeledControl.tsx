import type { ReactNode } from 'react'

type LabeledControlProps = {
  action?: ReactNode
  children: ReactNode
  htmlFor: string
  label: ReactNode
}

export const LabeledControl = ({ action, children, htmlFor, label }: LabeledControlProps) => (
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
