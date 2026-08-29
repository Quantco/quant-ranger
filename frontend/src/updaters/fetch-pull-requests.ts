import type { Octokit } from '@octokit/rest'
import pLimit from 'p-limit'

import {
  hasPullRequest,
  parseGitHubRepository,
  pullRequestKey,
  type CiStatus,
  type LivePullRequest,
  type PullRequestLookup,
  type PullRequests,
  type ReviewStatus,
  type UpdaterResultWithPullRequest
} from './pull-request'
import type { UpdaterReportResult } from './updater-report'

const MAX_CONCURRENT_PULL_REQUEST_LOADS = 6
const NON_FAILURE_CHECK_CONCLUSIONS = new Set(['neutral', 'skipped', 'success'])
const QUANT_RANGER_COMMIT_TRAILER_PREFIX = 'X-Quant-Ranger:'

export interface PullRequestProgress {
  completed: number
  failures: number
  total: number
}

export async function fetchPullRequests(
  results: UpdaterReportResult[],
  githubApiUrl: string,
  token: string,
  { onProgress, signal }: { onProgress?: (progress: PullRequestProgress) => void; signal?: AbortSignal } = {}
): Promise<PullRequests> {
  // Octokit is only needed when the user explicitly loads live GitHub data.
  const { Octokit } = await import('@octokit/rest')
  const octokit = new Octokit({ auth: token === '' ? undefined : token, baseUrl: githubApiUrl })
  const uniqueResults = new Map(results.filter(hasPullRequest).map((result) => [pullRequestKey(result), result]))
  const progress: PullRequestProgress = { completed: 0, failures: 0, total: uniqueResults.size }
  onProgress?.({ ...progress })

  const complete = (failed: boolean) => {
    if (signal?.aborted === true) return
    progress.completed++
    if (failed) progress.failures++
    onProgress?.({ ...progress })
  }
  const limit = pLimit({ concurrency: MAX_CONCURRENT_PULL_REQUEST_LOADS, rejectOnClear: true })
  const requests = [...uniqueResults].map(([key, result]) =>
    limit(async () => {
      const lookup = await fetchPullRequestLookup(result, octokit, signal)
      complete(lookup.status === 'failed')
      return [key, lookup] as const
    })
  )
  if (signal?.aborted === true) limit.clearQueue()
  else signal?.addEventListener('abort', () => limit.clearQueue(), { once: true })
  return Object.fromEntries(await Promise.all(requests))
}

async function fetchPullRequestLookup(
  result: UpdaterResultWithPullRequest,
  octokit: Octokit,
  signal?: AbortSignal
): Promise<PullRequestLookup> {
  try {
    return { pullRequest: await fetchLivePullRequest(result, octokit, signal), status: 'loaded' }
  } catch (error) {
    if (signal?.aborted === true)
      throw signal.reason instanceof Error ? signal.reason : new DOMException('Request aborted', 'AbortError')
    return { message: error instanceof Error ? error.message : String(error), status: 'failed' }
  }
}

async function fetchLivePullRequest(
  result: UpdaterResultWithPullRequest,
  octokit: Octokit,
  signal?: AbortSignal
): Promise<LivePullRequest> {
  const repository = parseGitHubRepository(result.repository)
  if (!repository) throw new Error(`Invalid GitHub repository name: ${result.repository}`)
  const { owner, repo } = repository
  const pull_number = result.pull_request
  const request = signal ? { request: { signal } } : {}
  const { data: pull } = await octokit.rest.pulls.get({ owner, pull_number, repo, ...request })
  const open = pull.state === 'open'
  const [commits, runs, reviews] = await Promise.all([
    octokit.paginate(octokit.rest.pulls.listCommits, { owner, per_page: 100, pull_number, repo, ...request }),
    open
      ? octokit.rest.actions.listWorkflowRunsForRepo({
          head_sha: pull.head.sha,
          owner,
          per_page: 100,
          repo,
          ...request
        })
      : null,
    open
      ? octokit.paginate(octokit.rest.pulls.listReviews, { owner, per_page: 100, pull_number, repo, ...request })
      : []
  ])
  return {
    ciStatus: runs == null ? null : deriveCiStatus(runs.data.workflow_runs),
    comments: pull.comments + pull.review_comments,
    createdAt: pull.created_at,
    hasMergeConflicts: open && pull.mergeable != null ? !pull.mergeable : null,
    hasNonQuantRangerCommits: commits.some(({ commit }) => !hasQuantRangerCommitTrailer(commit.message)),
    reviewStatus: open
      ? deriveReviewStatus(
          reviews,
          (pull.requested_reviewers?.length ?? 0) > 0 || (pull.requested_teams?.length ?? 0) > 0
        )
      : null,
    reviewers: [
      ...(pull.requested_reviewers ?? []).map(({ html_url, login }) => ({ label: `@${login}`, url: html_url })),
      ...(pull.requested_teams ?? []).map(({ html_url, slug }) => ({ label: `@${owner}/${slug}`, url: html_url }))
    ],
    state: pull.merged_at == null ? pull.state : 'merged',
    title: pull.title,
    updatedAt: pull.updated_at
  }
}

function deriveCiStatus(checks: { conclusion: string | null; status: string | null }[]): CiStatus {
  if (checks.length === 0) return 'none'
  // A completed failure takes precedence even while other checks are pending.
  if (checks.some(({ conclusion }) => conclusion != null && !NON_FAILURE_CHECK_CONCLUSIONS.has(conclusion)))
    return 'failure'
  if (checks.some(({ conclusion, status }) => status !== 'completed' || conclusion == null)) return 'pending'
  return 'success'
}

function deriveReviewStatus(
  reviews: { state: string; user?: { login: string } | null }[],
  requested: boolean
): ReviewStatus {
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

function hasQuantRangerCommitTrailer(message: string): boolean {
  return message.split('\n').some((line) => line.startsWith(QUANT_RANGER_COMMIT_TRAILER_PREFIX))
}
