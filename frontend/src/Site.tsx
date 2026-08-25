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

import type { DashboardSnapshot } from './copier/dashboard'
import { fetchJson } from './lib/fetch-json'
import Overview from './Overview'

const SITE_TITLE = 'Quant Ranger Dashboard'
const COPIER_TITLE = 'Copier Dashboard'
const COPIER_DATA_PATH = 'data/copier/latest.json'
const DATA_MESSAGE_CLASS =
  'mt-4 grid gap-2 rounded-medium border border-border bg-muted p-4 [&>:first-child]:mt-0 [&>:last-child]:mb-0 [&>p]:text-muted-foreground'
const SITE_TITLE_CLASS = 'inline-flex items-center gap-2 font-bold text-foreground no-underline'

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

const ROUTE_HANDLES = {
  overview: {
    breadcrumbs: () => [],
    home: true,
    title: () => ''
  },
  copier: {
    breadcrumbs: () => [{ label: COPIER_TITLE }],
    title: () => COPIER_TITLE
  },
  notFound: {
    breadcrumbs: () => [],
    title: () => 'Page not found'
  }
} satisfies Record<string, SiteRouteHandle>

async function loadCopier({ request }: LoaderFunctionArgs): Promise<DashboardSnapshot> {
  const snapshot = await fetchJson<DashboardSnapshot>(`./${COPIER_DATA_PATH}`, { signal: request.signal })
  if (snapshot == null) throw new Error('No Copier report data was found.')
  return snapshot
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
    <main className="ml-[max(1rem,calc((100%_-_1360px)/2))] max-w-[44rem]">
      <h1>{COPIER_TITLE} unavailable</h1>
      <p>{routeErrorMessage(error)}</p>
      <div className={DATA_MESSAGE_CLASS}>
        <p>
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
      <nav
        aria-label="Breadcrumb"
        className="flex flex-wrap items-center gap-4 border-b border-border bg-primary-subtle px-[max(1rem,calc((100%_-_1360px)/2))] py-3"
      >
        {handle?.home ? (
          <span aria-current="page" className={SITE_TITLE_CLASS}>
            <img alt="" aria-hidden="true" className="size-6 flex-none" src="./favicon.png" />
            {SITE_TITLE}
          </span>
        ) : (
          <Link className={SITE_TITLE_CLASS} to="/">
            <img alt="" aria-hidden="true" className="size-6 flex-none" src="./favicon.png" />
            {SITE_TITLE}
          </Link>
        )}
        {breadcrumbs.map(({ label, to }) => (
          <Fragment key={`${to ?? 'current'}:${label}`}>
            <span aria-hidden="true" className="text-muted-foreground">
              /
            </span>
            {to ? (
              <Link to={to}>{label}</Link>
            ) : (
              <span aria-current="page" className="text-muted-foreground [overflow-wrap:anywhere]">
                {label}
              </span>
            )}
          </Fragment>
        ))}
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
      { Component: Overview, handle: ROUTE_HANDLES.overview, index: true },
      {
        errorElement: <CopierError />,
        handle: ROUTE_HANDLES.copier,
        HydrateFallback: LoadingPage,
        lazy: lazyCopierRoute,
        loader: loadCopier,
        path: 'copier',
        shouldRevalidate: keepReportData
      },
      { Component: NotFound, handle: ROUTE_HANDLES.notFound, path: '*' }
    ],
    path: '/'
  }
])
