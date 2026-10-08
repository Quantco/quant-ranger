import type { UpdaterReportResult } from '../updater-report'

export type PullRequestState = 'closed' | 'merged' | 'open'
export type CiStatus = 'failure' | 'none' | 'pending' | 'success'
export type ReviewStatus = 'approved' | 'changes-requested' | 'none' | 'pending'

export type PullRequestReviewer = {
  label: string
  url: string
}

export type PullRequest = {
  title: string
  createdAt: string
  updatedAt: string
  state: PullRequestState
  comments: number
  hasNonQuantRangerCommits: boolean
  reviewers: PullRequestReviewer[]
  hasMergeConflicts: boolean | null
  reviewStatus: ReviewStatus | null
  ciStatus: CiStatus | null
}

export type UpdaterResultWithPullRequest = UpdaterReportResult & { pull_request: number }

export const hasPullRequest = (result: UpdaterReportResult): result is UpdaterResultWithPullRequest =>
  result.pull_request != null

export const parseGitHubRepository = (repository: string): { owner: string; repo: string } | null => {
  const [owner, repo, ...remainder] = repository.split('/')
  return owner != null && owner !== '' && repo != null && repo !== '' && remainder.length === 0 ? { owner, repo } : null
}

export const pullRequestKey = (result: Pick<UpdaterResultWithPullRequest, 'pull_request' | 'repository'>) =>
  `${result.repository}#${result.pull_request}`
