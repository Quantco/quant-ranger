import { Fragment } from 'react'
import {
  Link,
  Outlet,
  ScrollRestoration,
  createHashRouter,
  isRouteErrorResponse,
  useLoaderData,
  useLocation,
  useMatches,
  useNavigation,
  useRouteError,
  type LoaderFunctionArgs,
  type ShouldRevalidateFunctionArgs
} from 'react-router'

import { parseDashboardSnapshot, type DashboardSnapshot } from './copier/dashboard'
import { fetchJson } from './lib/fetch-json'
import Overview from './Overview'

const SITE_TITLE = 'Quant Ranger Dashboard'
const COPIER_TITLE = 'Copier Dashboard'
const COPIER_DATA_PATH = 'data/copier/latest.json'

type Breadcrumb = {
  label: string
  to?: string
}

type SiteMatch = ReturnType<typeof useMatches>[number]

type SiteRouteHandle = {
  breadcrumbs: (match: SiteMatch) => Breadcrumb[]
  home?: boolean
  title: (match: SiteMatch) => string
}

async function loadCopier({ request }: LoaderFunctionArgs): Promise<DashboardSnapshot> {
  const snapshot = await fetchJson(`./${COPIER_DATA_PATH}`, { signal: request.signal })
  if (snapshot == null) throw new Error('No Copier report data was found.')
  return parseDashboardSnapshot(snapshot)
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

function LoadingPage() {
  return (
    <main>
      <p>Loading…</p>
    </main>
  )
}

function SiteTitle({ current }: { current: boolean }) {
  const title = (
    <span
      aria-current={current ? 'page' : undefined}
      className="inline-flex items-center gap-2 font-bold text-foreground"
    >
      <img alt="" aria-hidden="true" className="size-6 flex-none" src="./favicon.png" />
      {SITE_TITLE}
    </span>
  )

  return current ? (
    title
  ) : (
    <Link className="no-underline" to="/">
      {title}
    </Link>
  )
}

// Keep Copier/Recharts out of the initial bundle. The static loader lets data
// fetching run in parallel with loading this route chunk.
async function lazyCopierRoute() {
  const { default: CopierDashboard } = await import('./copier/CopierDashboard')
  return {
    Component: () => <CopierDashboard snapshot={useLoaderData<typeof loadCopier>()} />
  }
}

function CopierError() {
  const error = useRouteError()
  return (
    <main className="max-w-3xl">
      <h1>{COPIER_TITLE} unavailable</h1>
      <p>{routeErrorMessage(error)}</p>
      <div className="mt-4 grid gap-2 rounded-lg border border-border bg-muted p-4">
        <p className="mt-0 mb-2 text-muted-foreground">
          Expected a generated report at <code>{COPIER_DATA_PATH}</code>.
        </p>
        <Link to="/">Return to Overview</Link>
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

function Site() {
  const location = useLocation()
  const matches = useMatches()
  const navigation = useNavigation()
  const currentMatch = matches.at(-1)
  const handle = currentMatch?.handle as SiteRouteHandle | undefined
  const pageTitle = currentMatch && handle ? handle.title(currentMatch) : ''
  const breadcrumbs = currentMatch && handle ? handle.breadcrumbs(currentMatch) : []
  const loadingPage = navigation.state === 'loading' && navigation.location?.pathname !== location.pathname

  return (
    <>
      <title>{pageTitle ? `${pageTitle} · ${SITE_TITLE}` : SITE_TITLE}</title>
      <nav aria-label="Breadcrumb" className="border-b border-border bg-primary-subtle">
        <div className="mx-auto flex w-full max-w-7xl flex-wrap items-center gap-4 px-4 py-3">
          <SiteTitle current={handle?.home === true} />
          {breadcrumbs.map(({ label, to }) => (
            <Fragment key={`${to ?? 'current'}:${label}`}>
              <span aria-hidden="true" className="text-muted-foreground">
                /
              </span>
              {to ? (
                <Link to={to}>{label}</Link>
              ) : (
                <span aria-current="page" className="wrap-anywhere text-muted-foreground">
                  {label}
                </span>
              )}
            </Fragment>
          ))}
        </div>
      </nav>
      {loadingPage ? <LoadingPage /> : <Outlet />}
      <ScrollRestoration />
    </>
  )
}

// Hash routing avoids server-side rewrite requirements on static hosts such as GitHub Pages.
export const router = createHashRouter([
  {
    Component: Site,
    children: [
      {
        Component: Overview,
        handle: {
          breadcrumbs: () => [],
          home: true,
          title: () => ''
        } satisfies SiteRouteHandle,
        index: true
      },
      {
        errorElement: <CopierError />,
        handle: {
          breadcrumbs: () => [{ label: COPIER_TITLE }],
          title: () => COPIER_TITLE
        } satisfies SiteRouteHandle,
        HydrateFallback: LoadingPage,
        lazy: lazyCopierRoute,
        loader: loadCopier,
        path: 'copier',
        shouldRevalidate: keepReportData
      },
      {
        Component: NotFound,
        handle: {
          breadcrumbs: () => [],
          title: () => 'Page not found'
        } satisfies SiteRouteHandle,
        path: '*'
      }
    ],
    path: '/'
  }
])
