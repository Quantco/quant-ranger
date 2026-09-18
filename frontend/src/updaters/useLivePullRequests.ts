import { useQueries, useQueryClient, type UseQueryResult } from '@tanstack/react-query'
import { useCallback, useMemo } from 'react'

import { fetchLivePullRequest } from './fetch-pull-requests'
import { useOctokit } from './github-client'
import { createGitHubTokenUrl } from './github-token-url'
import {
  hasPullRequest,
  pullRequestKey,
  type LivePullRequest,
  type PullRequests,
  type UpdaterResultWithPullRequest
} from './pull-request'
import { livePullRequestQueryKey, pullRequestQueryKey } from './pull-request-query'
import type { UpdaterReportSnapshot } from './updater-report'

export type PullRequestFailure = {
  key: string
  message: string
}

export type PullRequestProgress = {
  completed: number
  failures: number
  total: number
}

/** Everything the dashboard reads from the queries, as opposed to from the report. */
export type PullRequestFeedState = {
  cachedAt: string | null
  failures: PullRequestFailure[]
  loadedCount: number
  loading: boolean
  openCount: number
  progress: PullRequestProgress
  pullRequests: PullRequests
}

export type LivePullRequestFeed = {
  createTokenUrl: string | null
  /** Reloads every pull request using the token currently in the field. */
  refetch: () => void
} & PullRequestFeedState

/** What the panel renders: the feed, with enabling folded into a single action. */
export type LivePullRequestModel = {
  load: () => void
} & Omit<LivePullRequestFeed, 'refetch'>

/** One distinct pull request the report mentions, paired with its cache key. */
type ReportedPullRequest = {
  key: string
  result: UpdaterResultWithPullRequest
}

export const useLivePullRequests = (report: UpdaterReportSnapshot, enabled: boolean): LivePullRequestFeed => {
  const { commitToken, octokit } = useOctokit()
  const queryClient = useQueryClient()
  const { feed_id: feedId, github_api_url: githubApiUrl, results } = report

  // One query per pull request, deduplicated: a report may mention the same
  // pull request in several results.
  const reported = useMemo(
    () =>
      [...new Map(results.filter(hasPullRequest).map((result) => [pullRequestKey(result), result]))].map(
        ([key, result]): ReportedPullRequest => ({ key, result })
      ),
    [results]
  )
  const combine = useCallback(
    (queries: UseQueryResult<LivePullRequest>[]) => combinePullRequests(reported, queries),
    [reported]
  )

  const live = useQueries({
    combine,
    queries: reported.map(({ key, result }) => ({
      enabled,
      queryFn: ({ signal }: { signal: AbortSignal }) => fetchLivePullRequest(result, octokit, signal),
      queryKey: livePullRequestQueryKey(githubApiUrl, feedId, key),
      retry: false,
      staleTime: Infinity
    }))
  })

  const refetch = () => {
    // Adopt whatever is typed now; requests already queued keep the old token.
    commitToken()
    // Invalidation rather than the queries' own `refetch`: it overrides
    // `staleTime`, and it also marks queries that are still disabled, so a
    // caller may flip `enabled` in the same event without ordering the two.
    void queryClient.invalidateQueries({ queryKey: pullRequestQueryKey(githubApiUrl, feedId) })
  }

  return { ...live, createTokenUrl: createGitHubTokenUrl(report), refetch }
}

/** Folds the per-pull-request queries into the one shape the dashboard renders. */
const combinePullRequests = (
  reported: readonly ReportedPullRequest[],
  queries: readonly UseQueryResult<LivePullRequest>[]
): PullRequestFeedState => {
  const pullRequests: PullRequests = {}
  const failures: PullRequestFailure[] = []
  let completed = 0
  let loadedCount = 0
  let loading = false
  let openCount = 0
  let lastUpdatedAt = 0

  queries.forEach((query, index) => {
    const key = reported[index]?.key
    if (key == null) return

    if (query.isFetching) {
      loading = true
    } else if (query.error != null) {
      completed += 1
      failures.push({ key, message: query.error.message })
    } else if (query.data != null) {
      completed += 1
    }

    // Data from an earlier load stays visible while a refetch is in flight, so
    // this is deliberately not tied to the settled branches above.
    if (query.data != null) {
      pullRequests[key] = query.data
      loadedCount += 1
      if (query.data.state === 'open') openCount += 1
      lastUpdatedAt = Math.max(lastUpdatedAt, query.dataUpdatedAt)
    }
  })

  return {
    cachedAt: lastUpdatedAt === 0 ? null : new Date(lastUpdatedAt).toISOString(),
    failures,
    loadedCount,
    loading,
    openCount,
    progress: { completed, failures: failures.length, total: queries.length },
    pullRequests
  }
}
