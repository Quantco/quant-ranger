import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'
import { formatDateTime, formatRelativeTime } from '../lib/date'
import type { LivePullRequestModel } from './useLivePullRequests'

type PullRequestDataControlsModel = Pick<
  LivePullRequestModel,
  | 'cachedAt'
  | 'clearToken'
  | 'createTokenUrl'
  | 'load'
  | 'loadError'
  | 'loadedCount'
  | 'loading'
  | 'setTokenInput'
  | 'tokenInput'
>

function PullRequestCacheSummary({ cachedAt, loadedCount }: { cachedAt: string | null; loadedCount: number }) {
  if (cachedAt == null) return null

  return (
    <span className="grid min-w-28 gap-0.5 text-sm/tight text-muted-foreground">
      <small className="font-semibold text-foreground">{loadedCount} pull requests</small>
      <small title={formatDateTime(cachedAt) ?? cachedAt}>
        Cached {formatRelativeTime(cachedAt) ?? 'at an unknown time'}
      </small>
    </span>
  )
}

export function PullRequestDataControls({
  githubApiUrl,
  model
}: {
  githubApiUrl: string
  model: PullRequestDataControlsModel
}) {
  const { cachedAt, clearToken, createTokenUrl, load, loadError, loadedCount, loading, setTokenInput, tokenInput } =
    model

  return (
    <>
      <form
        className="grid w-full max-w-full grid-cols-1 items-center gap-3 lg:flex lg:w-fit lg:flex-wrap"
        onSubmit={(event) => {
          event.preventDefault()
          load()
        }}
      >
        <Input
          aria-describedby="github-token-help"
          aria-label="GitHub token"
          autoComplete="off"
          className="lg:w-96"
          id="github-token"
          onChange={(event) => setTokenInput(event.target.value)}
          placeholder="GitHub token (optional)"
          type="password"
          value={tokenInput}
        />
        <div className="flex items-center gap-2 whitespace-nowrap">
          <Button className="min-h-10" disabled={loading} type="submit">
            {loading ? 'Loading…' : cachedAt != null ? 'Refresh PR data' : 'Load PR data'}
          </Button>
          <PullRequestCacheSummary cachedAt={cachedAt} loadedCount={loadedCount} />
        </div>
        {tokenInput !== '' && (
          <Button className="min-h-10" onClick={clearToken} type="button" variant="secondary">
            Clear token
          </Button>
        )}
      </form>
      {loadError !== '' && <p role="alert">Could not load pull request data: {loadError}</p>}
      <div className="mt-3 grid max-w-4xl gap-1 text-sm wrap-anywhere text-muted-foreground" id="github-token-help">
        <p className="m-0">
          The token is only needed for non-public repositories. If you don&apos;t have a token with the appropriate
          permissions, you can create one below:
        </p>
        {createTokenUrl != null && (
          <a className="w-fit" href={createTokenUrl} rel="noreferrer" target="_blank">
            Create a read-only token with the required permissions.
          </a>
        )}
        <p className="m-0">
          The token is kept only in memory until this page is reloaded and sent only to {githubApiUrl}.
        </p>
      </div>
    </>
  )
}
