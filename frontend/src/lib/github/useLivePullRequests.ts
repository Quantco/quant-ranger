import { queryOptions, useQueries, useQueryClient, type UseQueryResult } from '@tanstack/react-query'
import { useCallback, useMemo, useState } from 'react'

import { fetchPullRequest } from './fetch-pull-requests'
import { useOctokit } from './github-client'
import { hasPullRequest, pullRequestKey, type PullRequest } from './pull-request'
import { pullRequestQueryKey, feedQueryKey } from '@/lib/query-client'
import type { UpdaterReportSnapshot } from '../updater-report'

export type PullRequestFailure = {
  key: string
  message: string
}

type PullRequestFeedState = {
  cachedAt: string | null
  errors: PullRequestFailure[]
  progress: {
    loading: number
    completed: number
    failed: number
    total: number
  }
  openCount: number
  pullRequests: Record<string, PullRequest>
}

export type PullRequestModel = PullRequestFeedState & { load: () => void }

export const usePullRequests = ({
  feed_id: feedId,
  github_api_url: githubApiUrl,
  results
}: UpdaterReportSnapshot): PullRequestModel => {
  const { commitToken, octokit } = useOctokit()
  const queryClient = useQueryClient()
  const [enabled, setEnabled] = useState(false)

  // a report may mention the same pull request in several results -> deduplicate
  const unique = useMemo(
    () => [...new Map(results.filter(hasPullRequest).map((result) => [pullRequestKey(result), result]))],
    [results]
  )
  const queries = useMemo(
    () =>
      unique.map(([key, result]) =>
        queryOptions({
          enabled,
          queryFn: ({ signal }: { signal: AbortSignal }) => fetchPullRequest(result, octokit, signal),
          queryKey: pullRequestQueryKey(githubApiUrl, feedId, key),
          retry: false,
          staleTime: Infinity
        })
      ),
    [unique, enabled, githubApiUrl, feedId, octokit]
  )

  // add key to each query result, then call `combinePullRequests`
  const combine = useCallback(
    (queries: UseQueryResult<PullRequest>[]) => {
      const keys = unique.map(([key]) => key)
      const keyedQueries = queries.map((query, index) => ({ key: keys[index]!, ...query }))
      return combinePullRequests(keyedQueries)
    },
    [unique]
  )

  const live = useQueries({ combine, queries })

  const load = () => {
    setEnabled(true)
    commitToken()
    void queryClient.invalidateQueries({ queryKey: feedQueryKey(githubApiUrl, feedId) })
  }

  return { ...live, load }
}

/** Folds the per-pull-request queries into the one shape the dashboard renders. */
const combinePullRequests = (queries: (UseQueryResult<PullRequest> & { key: string })[]): PullRequestFeedState => {
  const {
    loading = [],
    failure = [],
    success = []
  } = Object.groupBy(queries, (query) => {
    if (query.isFetching) return 'loading'
    if (query.error !== null) return 'failure'
    return 'success'
  })

  const lastUpdatedAt = Math.max(0, ...queries.map((query) => query.dataUpdatedAt))
  const cachedAt = lastUpdatedAt === 0 ? null : new Date(lastUpdatedAt).toISOString()
  const errors = failure.map((query) => ({ key: query.key, message: query.error!.message }))
  const openCount = success.filter((query) => query.data!.state === 'open').length

  const pullRequests: Record<string, PullRequest> = Object.fromEntries(success.map((query) => [query.key, query.data!]))

  const progress = {
    loading: loading.length,
    completed: failure.length + success.length,
    failed: failure.length,
    total: queries.length
  }

  return {
    cachedAt,
    errors,
    openCount,
    progress,
    pullRequests
  }
}
