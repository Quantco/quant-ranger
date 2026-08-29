import { Link, Outlet, ScrollRestoration, useLocation, useMatches, useNavigation, type UIMatch } from 'react-router'

const SITE_TITLE = 'Quant Ranger Dashboard'

export type RouteTitleResolver<Data = unknown> = (match: UIMatch<Data>) => string

function isRouteTitleResolver(value: unknown): value is RouteTitleResolver {
  return typeof value === 'function'
}

function resolveRouteTitle(match: UIMatch | undefined): string {
  return match != null && isRouteTitleResolver(match.handle) ? match.handle(match) : ''
}

function AppTitle({ current }: { current: boolean }) {
  const content = (
    <>
      <img alt="" aria-hidden="true" className="size-6 flex-none" src="./favicon.png" />
      {SITE_TITLE}
    </>
  )
  const className = 'inline-flex items-center gap-2 leading-none font-bold text-foreground'

  return current ? (
    <span aria-current="page" className={className}>
      {content}
    </span>
  ) : (
    <Link className={`${className} no-underline`} to="/">
      {content}
    </Link>
  )
}

export function LoadingPage() {
  return (
    <main>
      <p>Loading…</p>
    </main>
  )
}

export function AppLayout() {
  const location = useLocation()
  const matches = useMatches()
  const navigation = useNavigation()
  const home = location.pathname === '/'
  const title = resolveRouteTitle(matches.at(-1))
  const loadingPage = navigation.state === 'loading' && navigation.location.pathname !== location.pathname

  return (
    <>
      <title>{title ? `${title} · ${SITE_TITLE}` : SITE_TITLE}</title>
      <nav aria-label="Breadcrumb" className="border-b border-border bg-primary-subtle">
        <div className="mx-auto flex w-full max-w-7xl flex-wrap items-center gap-4 px-4 py-3">
          <AppTitle current={home} />
          {!home && title !== '' && (
            <span className="inline-flex min-w-0 items-center gap-4 leading-none">
              <span aria-hidden="true" className="text-muted-foreground">
                /
              </span>
              <span aria-current="page" className="min-w-0 wrap-anywhere text-muted-foreground">
                {title}
              </span>
            </span>
          )}
        </div>
      </nav>
      {loadingPage ? <LoadingPage /> : <Outlet />}
      <ScrollRestoration />
    </>
  )
}
