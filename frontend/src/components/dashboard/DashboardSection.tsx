import { useId, type ReactNode } from 'react'

export function DashboardSection({ children, heading }: { children: ReactNode; heading: ReactNode }) {
  const headingId = useId()
  return (
    <section
      aria-labelledby={headingId}
      className="border-t border-border py-6 first:border-t-0 first:pt-0 lg:first:pt-4"
    >
      <h2 className="mt-0 mb-2" id={headingId}>
        {heading}
      </h2>
      {children}
    </section>
  )
}
