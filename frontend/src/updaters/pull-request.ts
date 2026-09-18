import type { UpdaterReportResult } from './updater-report'

export type PullRequestState = 'closed' | 'merged' | 'open'
export type CiStatus = 'failure' | 'none' | 'pending' | 'success'
export type ReviewStatus = 'approved' | 'changes-requested' | 'none' | 'pending'

export type PullRequestReviewer = {
  label: string
  url: string
}

export type LivePullRequest = {
  ciStatus: CiStatus | null
  comments: number
  createdAt: string
  hasMergeConflicts: boolean | null
  hasNonQuantRangerCommits: boolean
  reviewStatus: ReviewStatus | null
  reviewers: PullRequestReviewer[]
  state: PullRequestState
  title: string
  updatedAt: string
}

/** Successfully loaded pull requests by `pullRequestKey`. Lookups that failed
 * are reported separately, so a missing entry simply means "not loaded". */
export type PullRequests = Record<string, LivePullRequest>

export type UpdaterResultWithPullRequest = UpdaterReportResult & { pull_request: number }

export const hasPullRequest = (result: UpdaterReportResult): result is UpdaterResultWithPullRequest =>
  result.pull_request != null

export const parseGitHubRepository = (repository: string): { owner: string; repo: string } | null => {
  const [owner, repo, ...remainder] = repository.split('/')
  return owner != null && owner !== '' && repo != null && repo !== '' && remainder.length === 0 ? { owner, repo } : null
}

export const pullRequestKey = (result: Pick<UpdaterResultWithPullRequest, 'pull_request' | 'repository'>): string =>
  `${result.repository}#${result.pull_request}`
