import type { Octokit, RestEndpointMethodTypes } from '@octokit/rest'

import {
  parseGitHubRepository,
  type CiStatus,
  type LivePullRequest,
  type PullRequestReviewer,
  type ReviewStatus,
  type UpdaterResultWithPullRequest
} from './pull-request'

const PAGE_SIZE = 100
const NON_FAILURE_CHECK_CONCLUSIONS = new Set(['neutral', 'skipped', 'success'])
const QUANT_RANGER_COMMIT_TRAILER_PREFIX = 'X-Quant-Ranger:'

type PullRequestDetails = RestEndpointMethodTypes['pulls']['get']['response']['data']

/** Repository and cancellation parameters every call in one load shares. */
type ListScope = {
  owner: string
  per_page: number
  repo: string
  request: { signal: AbortSignal }
}

/** The fields that only mean anything while a pull request is still open. */
type OpenPullRequestStatus = Pick<LivePullRequest, 'ciStatus' | 'hasMergeConflicts' | 'reviewStatus'>

const CLOSED_PULL_REQUEST_STATUS: OpenPullRequestStatus = {
  ciStatus: null,
  hasMergeConflicts: null,
  reviewStatus: null
}

export const fetchLivePullRequest = async (
  result: UpdaterResultWithPullRequest,
  octokit: Octokit,
  signal: AbortSignal
): Promise<LivePullRequest> => {
  const repository = parseGitHubRepository(result.repository)
  if (!repository) throw new Error(`Invalid GitHub repository name: ${result.repository}`)

  const scope = { ...repository, request: { signal } }
  const listScope: ListScope = { ...scope, per_page: PAGE_SIZE }

  const { data: pull } = await octokit.rest.pulls.get({ ...scope, pull_number: result.pull_request })

  const [commits, status] = await Promise.all([
    octokit.paginate(octokit.rest.pulls.listCommits, { ...listScope, pull_number: pull.number }),
    pull.state === 'open' ? fetchOpenPullRequestStatus(octokit, pull, listScope) : CLOSED_PULL_REQUEST_STATUS
  ])

  return {
    ...status,
    comments: pull.comments + pull.review_comments,
    createdAt: pull.created_at,
    hasNonQuantRangerCommits: commits.some(({ commit }) => !hasQuantRangerCommitTrailer(commit.message)),
    reviewers: requestedReviewers(pull, repository.owner),
    state: pull.merged_at == null ? pull.state : 'merged',
    title: pull.title,
    updatedAt: pull.updated_at
  }
}

/** Checks, reviews and mergeability are only reported for open pull requests. */
const fetchOpenPullRequestStatus = async (
  octokit: Octokit,
  pull: PullRequestDetails,
  listScope: ListScope
): Promise<OpenPullRequestStatus> => {
  const [runs, reviews] = await Promise.all([
    octokit.paginate(octokit.rest.actions.listWorkflowRunsForRepo, { ...listScope, head_sha: pull.head.sha }),
    octokit.paginate(octokit.rest.pulls.listReviews, { ...listScope, pull_number: pull.number })
  ])

  return {
    ciStatus: deriveCiStatus(runs),
    hasMergeConflicts: pull.mergeable == null ? null : !pull.mergeable,
    reviewStatus: deriveReviewStatus(reviews, hasRequestedReviewer(pull))
  }
}

const hasRequestedReviewer = (pull: PullRequestDetails): boolean =>
  (pull.requested_reviewers?.length ?? 0) > 0 || (pull.requested_teams?.length ?? 0) > 0

const requestedReviewers = (pull: PullRequestDetails, owner: string): PullRequestReviewer[] => [
  ...(pull.requested_reviewers ?? []).map(({ html_url, login }) => ({ label: `@${login}`, url: html_url })),
  ...(pull.requested_teams ?? []).map(({ html_url, slug }) => ({ label: `@${owner}/${slug}`, url: html_url }))
]

const deriveCiStatus = (checks: { conclusion: string | null; status: string | null }[]): CiStatus => {
  if (checks.length === 0) return 'none'
  // A completed failure takes precedence even while other checks are pending.
  if (checks.some(({ conclusion }) => conclusion != null && !NON_FAILURE_CHECK_CONCLUSIONS.has(conclusion)))
    return 'failure'
  if (checks.some(({ conclusion, status }) => status !== 'completed' || conclusion == null)) return 'pending'
  return 'success'
}

const deriveReviewStatus = (
  reviews: { state: string; user?: { login: string } | null }[],
  requested: boolean
): ReviewStatus => {
  // Later reviews replace each reviewer's previous decision; dismissals clear it.
  const decisions = new Map<string, 'approved' | 'changes_requested'>()
  for (const { state, user } of reviews) {
    if (!user) continue
    const decision = state.toLowerCase()
    if (decision === 'dismissed') decisions.delete(user.login)
    else if (decision === 'approved' || decision === 'changes_requested') decisions.set(user.login, decision)
  }
  const latestDecisions = new Set(decisions.values())
  // Any outstanding change request takes precedence over approvals.
  if (latestDecisions.has('changes_requested')) return 'changes-requested'
  if (latestDecisions.has('approved')) return 'approved'
  return requested ? 'pending' : 'none'
}

const hasQuantRangerCommitTrailer = (message: string): boolean =>
  message.split('\n').some((line) => line.startsWith(QUANT_RANGER_COMMIT_TRAILER_PREFIX))
