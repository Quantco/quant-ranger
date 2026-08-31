import {
  Link,
  createHashRouter,
  isRouteErrorResponse,
  useLoaderData,
  useParams,
  useRouteError,
  type LoaderFunctionArgs,
  type ShouldRevalidateFunctionArgs,
  type UIMatch
} from 'react-router'

import Overview, { loadOverview } from '@/Overview'
import { parseDashboardSnapshot, type DashboardSnapshot } from '@/copier/dashboard'
import { fetchJson } from '@/lib/fetch-json'
import { parseUpdaterReport, type UpdaterReportSnapshot } from '@/updaters/updater-report'
import { AppLayout, LoadingPage, type RouteTitleResolver } from './AppLayout'

const COPIER_TITLE = 'Copier Dashboard'
const COPIER_DATA_PATH = 'data/copier/latest.json'

interface ReportErrorConfig {
  dataPath: (feedId: string) => string
  returnLabel: string
  title: string
}

function updaterDataPath(feedId: string) {
  return `data/updaters/${encodeURIComponent(feedId)}/latest.json`
}

function updaterTitle(match: UIMatch<UpdaterReportSnapshot>): string {
  const report = match.loaderData
  return report?.title ?? report?.feed_id ?? match.params['feedId'] ?? ''
}

const REPORT_ERRORS = {
  copier: {
    dataPath: () => COPIER_DATA_PATH,
    returnLabel: 'Return to Overview',
    title: `${COPIER_TITLE} unavailable`
  },
  updater: {
    dataPath: updaterDataPath,
    returnLabel: 'Return to updater runs',
    title: 'Updater report unavailable'
  }
} satisfies Record<string, ReportErrorConfig>

async function loadCopier({ request }: LoaderFunctionArgs): Promise<DashboardSnapshot> {
  const snapshot = await fetchJson(`./${COPIER_DATA_PATH}`, request.signal)
  if (snapshot == null) throw new Error('No Copier report data was found.')
  return parseDashboardSnapshot(snapshot)
}

async function loadUpdater({ params, request }: LoaderFunctionArgs): Promise<UpdaterReportSnapshot> {
  const feedId = params['feedId']
  if (feedId == null) throw new Error('No updater feed was selected.')
  const report = await fetchJson(`./${updaterDataPath(feedId)}`, request.signal)
  if (report == null) throw new Error('No updater report data was found.')
  return parseUpdaterReport(report)
}

function keepReportData({ currentUrl, defaultShouldRevalidate, nextUrl }: ShouldRevalidateFunctionArgs) {
  return currentUrl.pathname === nextUrl.pathname && currentUrl.search !== nextUrl.search
    ? false
    : defaultShouldRevalidate
}

function routeErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  if (isRouteErrorResponse(error)) return typeof error.data === 'string' ? error.data : error.statusText
  return String(error)
}

// Keep dashboard-specific dependencies out of the initial bundle. Static
// loaders let data fetching run in parallel with loading each route chunk.
async function lazyCopierRoute() {
  const { default: CopierDashboard } = await import('../copier/CopierDashboard')
  return {
    Component: () => <CopierDashboard snapshot={useLoaderData<typeof loadCopier>()} />
  }
}

async function lazyUpdaterRoute() {
  const { default: UpdaterDashboard } = await import('../updaters/UpdaterDashboard')
  return {
    Component: () => <UpdaterDashboard report={useLoaderData<typeof loadUpdater>()} />
  }
}

function ReportError({ config }: { config: ReportErrorConfig }) {
  const error = useRouteError()
  const { feedId = '' } = useParams()
  return (
    <main className="max-w-3xl">
      <h1>{config.title}</h1>
      <p>{routeErrorMessage(error)}</p>
      <div className="mt-4 grid gap-2 rounded-lg border border-border bg-muted p-4">
        <p className="mt-0 mb-2 text-muted-foreground">
          Expected a generated report at <code>{config.dataPath(feedId)}</code>.
        </p>
        <Link to="/">{config.returnLabel}</Link>
      </div>
    </main>
  )
}

function NotFound() {
  return (
    <main>
      <h1>Page not found</h1>
      <p>
        Return to <Link to="/">Overview</Link>.
      </p>
    </main>
  )
}

// Hash routing avoids server-side rewrite requirements on static hosts such as GitHub Pages.
export const router = createHashRouter([
  {
    Component: AppLayout,
    children: [
      {
        Component: Overview,
        HydrateFallback: LoadingPage,
        index: true,
        loader: loadOverview
      },
      {
        errorElement: <ReportError config={REPORT_ERRORS.copier} />,
        handle: (() => COPIER_TITLE) satisfies RouteTitleResolver,
        HydrateFallback: LoadingPage,
        lazy: lazyCopierRoute,
        loader: loadCopier,
        path: 'copier',
        shouldRevalidate: keepReportData
      },
      {
        errorElement: <ReportError config={REPORT_ERRORS.updater} />,
        handle: updaterTitle satisfies RouteTitleResolver<UpdaterReportSnapshot>,
        HydrateFallback: LoadingPage,
        lazy: lazyUpdaterRoute,
        loader: loadUpdater,
        path: 'updaters/:feedId',
        shouldRevalidate: keepReportData
      },
      {
        Component: NotFound,
        handle: (() => 'Page not found') satisfies RouteTitleResolver,
        path: '*'
      }
    ],
    path: '/'
  }
])
