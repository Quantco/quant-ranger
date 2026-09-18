import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { formatDateTime, formatRelativeTime } from '@/lib/format'
import { useGitHubToken } from '@/lib/github/github-client'
import { createGitHubTokenUrl } from '@/lib/github/github-token-url'
import type { UpdaterReportSnapshot } from '@/lib/updater-report'
import type { PullRequestModel, PullRequestFailure } from '@/lib/github/useLivePullRequests'

const CacheSummary = ({ cachedAt, loadedCount }: { cachedAt: string | null; loadedCount: number }) => {
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

const Progress = ({ progress }: { progress: PullRequestModel['progress'] }) => (
  <div className="flex items-center gap-3">
    <progress
      aria-label="Pull request loading progress"
      className="w-full max-w-md"
      max={progress.total || 1}
      value={progress.completed}
    />
    <span>
      {progress.completed} of {progress.total} pull requests checked
      {progress.failed > 0 && ` · ${progress.failed} failed`}
    </span>
  </div>
)

const Failures = ({ failures }: { failures: PullRequestFailure[] }) => {
  if (failures.length === 0) return null
  // One bad token or a dead network fails every lookup identically, so each
  // message is listed once with the pull requests it affected.
  const grouped = Object.entries(Object.groupBy(failures, ({ message }) => message))

  return (
    <details className="border-l-4 border-error bg-error-subtle px-3 py-2">
      <summary className="focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
        {failures.length} GitHub API lookups failed
      </summary>
      <ul className="list-disc pl-5">
        {grouped.map(([message, affected = []]) => (
          <li key={message}>
            {message}
            <div className="text-muted-foreground">
              {affected.slice(0, 10).map(({ key }) => (
                <code className="mr-2 inline-block" key={key}>
                  {key}
                </code>
              ))}
              {affected.length > 10 && `and ${affected.length - 10} more`}
            </div>
          </li>
        ))}
      </ul>
    </details>
  )
}

type TokenInputProps = {
  onSubmit: () => void
  progress: PullRequestModel['progress']
  cachedAt: string | null
}

const TokenInput = ({ onSubmit, progress, cachedAt }: TokenInputProps) => {
  const { clearToken, setTokenInput, tokenInput } = useGitHubToken()

  return (
    <form
      className="grid w-full max-w-full grid-cols-1 items-center gap-3 lg:flex lg:w-fit lg:flex-wrap"
      onSubmit={(event) => {
        event.preventDefault()
        onSubmit()
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
        <Button className="min-h-10" disabled={progress.loading > 0} type="submit">
          {progress.loading > 0 ? 'Loading…' : cachedAt != null ? 'Refresh PR data' : 'Load PR data'}
        </Button>
        <CacheSummary cachedAt={cachedAt} loadedCount={progress.completed} />
      </div>
      {tokenInput !== '' && (
        <Button className="min-h-10" onClick={clearToken} type="button" variant="secondary">
          Clear token
        </Button>
      )}
    </form>
  )
}

export const PullRequestData = ({
  model,
  report
}: {
  model: Pick<PullRequestModel, 'cachedAt' | 'load' | 'errors' | 'progress'>
  report: UpdaterReportSnapshot
}) => {
  const createTokenUrl = createGitHubTokenUrl(report)

  return (
    <>
      <TokenInput onSubmit={() => model.load()} progress={model.progress} cachedAt={model.cachedAt} />
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
          The token is kept only in memory until this page is reloaded and sent only to {report.github_api_url}.
        </p>
      </div>
      {model.progress.loading > 0 && <Progress progress={model.progress} />}
      {model.progress.failed > 0 && <Failures failures={model.errors} />}
    </>
  )
}
