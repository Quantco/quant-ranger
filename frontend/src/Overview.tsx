import { ArrowRightIcon } from 'lucide-react'
import { Link } from 'react-router'

export default function Overview() {
  return (
    <main className="grid content-start gap-6">
      <header>
        <h1>Overview</h1>
        <p className="text-muted-foreground">Explore quant-ranger activity and reports.</p>
      </header>

      <section aria-labelledby="copier-dashboard-heading">
        <div className="mb-2 flex items-baseline justify-between gap-3">
          <h2 className="m-0" id="copier-dashboard-heading">
            Copier Dashboard
          </h2>
        </div>
        <Link
          className="flex items-center gap-2 rounded-lg border border-border bg-white p-3 text-foreground no-underline hover:border-primary-light hover:bg-primary-subtle focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2 md:gap-4 md:px-4"
          to="/copier"
        >
          <span className="grid min-w-0 flex-1 gap-1">
            <strong className="text-base font-semibold text-primary">Copier repositories</strong>
            <span className="text-sm text-muted-foreground">
              Compare template versions, validation results, and Copier answers.
            </span>
          </span>
          <span className="inline-flex flex-none items-center gap-1 text-sm font-semibold whitespace-nowrap text-primary">
            Open
            <ArrowRightIcon aria-hidden="true" className="size-4" />
          </span>
        </Link>
      </section>
    </main>
  )
}
