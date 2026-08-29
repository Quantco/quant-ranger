import type { PullRequestProgress } from './fetch-pull-requests'
import type { LivePullRequestModel, PullRequestFailure } from './useLivePullRequests'

type PullRequestDataStatusModel = Pick<LivePullRequestModel, 'failures' | 'loading' | 'loadProgress'>

function PullRequestLoadingProgress({ progress }: { progress: PullRequestProgress }) {
  return (
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
}

function PullRequestFailures({ failures }: { failures: PullRequestFailure[] }) {
  if (failures.length === 0) return null

  return (
    <details className="border-l-4 border-error bg-error-subtle px-3 py-2">
      <summary className="focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
        {failures.length} GitHub API lookups failed
      </summary>
      <ul className="list-disc pl-5">
        {failures.map(({ key, message }) => (
          <li key={key}>
            <code>{key}</code>: {message}
          </li>
        ))}
      </ul>
    </details>
  )
}

export function PullRequestDataStatus({ model }: { model: PullRequestDataStatusModel }) {
  return (
    <>
      {model.loading && <PullRequestLoadingProgress progress={model.loadProgress} />}
      <PullRequestFailures failures={model.failures} />
    </>
  )
}
