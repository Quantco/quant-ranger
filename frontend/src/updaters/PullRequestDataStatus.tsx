import type { LivePullRequestModel, PullRequestFailure, PullRequestProgress } from './useLivePullRequests'

type PullRequestDataStatusModel = Pick<LivePullRequestModel, 'failures' | 'loading' | 'progress'>

const PullRequestLoadingProgress = ({ progress }: { progress: PullRequestProgress }) => (
  <div className="flex items-center gap-3">
    <progress
      aria-label="Pull request loading progress"
      className="w-full max-w-md"
      max={progress.total || 1}
      value={progress.completed}
    />
    <span>
      {progress.completed} of {progress.total} pull requests checked
      {progress.failures > 0 && ` · ${progress.failures} failed`}
    </span>
  </div>
)

const PullRequestFailures = ({ failures }: { failures: PullRequestFailure[] }) => {
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

export const PullRequestDataStatus = ({ model }: { model: PullRequestDataStatusModel }) => (
  <>
    {model.loading && <PullRequestLoadingProgress progress={model.progress} />}
    <PullRequestFailures failures={model.failures} />
  </>
)
