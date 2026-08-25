import { Link } from 'react-router'

export default function Overview() {
  return (
    <main className="grid content-start gap-6">
      <header className="[&>p]:text-muted-foreground">
        <h1>Overview</h1>
        <p>Explore quant-ranger activity and reports.</p>
      </header>

      <section aria-labelledby="copier-dashboard-heading">
        <div className="mb-2 flex items-baseline justify-between gap-3">
          <h2 className="m-0" id="copier-dashboard-heading">
            Copier Dashboard
          </h2>
        </div>
        <Link
          className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2 rounded-medium border border-border bg-white p-3 text-foreground no-underline hover:border-primary-light hover:bg-primary-subtle focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2 min-[801px]:gap-4 min-[801px]:px-4"
          to="/copier"
        >
          <span className="grid min-w-0 gap-1">
            <strong className="text-base font-[650] text-primary">Copier repositories</strong>
            <span className="text-sm text-muted-foreground">
              Compare template versions, validation results, and Copier answers.
            </span>
          </span>
          <span className="inline-flex items-center gap-1 text-sm font-semibold whitespace-nowrap text-primary">
            Open
            <svg
              aria-hidden="true"
              className="size-4"
              fill="none"
              stroke="currentColor"
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              viewBox="0 0 16 16"
            >
              <path d="M3 8h10M9 4l4 4-4 4" />
            </svg>
          </span>
        </Link>
      </section>
    </main>
  )
}
