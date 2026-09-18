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
  const loading = queries.filter((query) => query.isFetching)
  // A refetch that fails keeps the data it had, so these overlap by design and
  // are counted over the queries rather than summed from the lists above.
  const completed = queries.filter((query) => query.data != null || query.error != null)

  // Selected on what a query holds rather than on what it is doing. A query that
  // has never run reports `isFetching: false` with no data and no error, so any
  // grouping keyed on activity files it alongside the ones that succeeded.
  const success = queries.flatMap((query) => (query.data == null ? [] : [{ data: query.data, key: query.key }]))
  const failures = queries.flatMap((query) =>
    query.error == null ? [] : [{ key: query.key, message: query.error.message }]
  )
  const lastUpdatedAt = Math.max(0, ...queries.map((query) => query.dataUpdatedAt))
  const cachedAt = lastUpdatedAt === 0 ? null : new Date(lastUpdatedAt).toISOString()
  const openCount = success.filter(({ data }) => data.state === 'open').length

  const pullRequests = Object.fromEntries(success.map(({ data, key }) => [key, data]))

  const progress = {
    loading: loading.length,
    completed: completed.length,
    failed: failures.length,
    total: queries.length
  }

  return {
    cachedAt,
    errors: failures,
    openCount,
    progress,
    pullRequests
  }
}
