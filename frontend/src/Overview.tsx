import { ArrowRightIcon } from 'lucide-react'
import { Link, useLoaderData, type LoaderFunctionArgs } from 'react-router'

import { fetchJson } from './lib/fetch-json'
import { UpdaterOverviewTable } from './updaters/UpdaterOverviewTable'
import { parseUpdaterIndex } from './updaters/updater-report'

const UPDATER_INDEX_PATH = 'data/updaters/index.json'
const DATA_MESSAGE_CLASS = 'grid gap-2 rounded-lg border border-border bg-muted p-4'

export async function loadOverview({ request }: LoaderFunctionArgs) {
  try {
    const index = await fetchJson(`./${UPDATER_INDEX_PATH}`, request.signal)
    return { error: null, feeds: index == null ? [] : parseUpdaterIndex(index).feeds }
  } catch (error) {
    request.signal.throwIfAborted()
    return { error: error instanceof Error ? error.message : String(error), feeds: [] }
  }
}

export default function Overview() {
  const { error, feeds } = useLoaderData<typeof loadOverview>()

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
          className="flex items-center gap-2 rounded-lg border border-border bg-white p-3 text-foreground no-underline hover:border-primary-light hover:bg-primary-subtle focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring md:gap-4 md:px-4"
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

      <section aria-labelledby="updater-feeds-heading">
        <div className="mb-2 flex items-baseline justify-between gap-3">
          <h2 className="m-0" id="updater-feeds-heading">
            Updater runs
          </h2>
          {error == null && (
            <span className="text-sm text-muted-foreground">
              {feeds.length === 1 ? '1 report' : `${feeds.length} reports`}
            </span>
          )}
        </div>
        {error != null ? (
          <div className={DATA_MESSAGE_CLASS} role="alert">
            <strong>Updater reports unavailable</strong>
            <p className="m-0 text-muted-foreground">{error}</p>
          </div>
        ) : feeds.length === 0 ? (
          <div className={DATA_MESSAGE_CLASS}>
            <strong>No updater reports yet</strong>
            <p className="m-0 text-muted-foreground">
              Generated reports will appear here after <code>{UPDATER_INDEX_PATH}</code> is published.
            </p>
          </div>
        ) : (
          <UpdaterOverviewTable feeds={feeds} />
        )}
      </section>
    </main>
  )
}
