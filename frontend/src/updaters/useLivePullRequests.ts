import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import * as z from 'zod/mini'

import { fetchPullRequests, type PullRequestProgress } from './fetch-pull-requests'
import { createGitHubTokenUrl } from './github-token-url'
import { hasPullRequest, pullRequestKey, pullRequestsSchema, type PullRequests } from './pull-request'
import { pullRequestQueryKey } from './pull-request-query'
import type { UpdaterReportSnapshot } from './updater-report'

const pullRequestCacheSchema = z.object({
  cachedAt: z.nullable(z.string()),
  pullRequests: pullRequestsSchema
})

interface PullRequestCache {
  cachedAt: string | null
  pullRequests: PullRequests
}

export interface PullRequestFailure {
  key: string
  message: string
}

export interface LivePullRequestModel {
  cachedAt: string | null
  clearToken: () => void
  createTokenUrl: string | null
  failures: PullRequestFailure[]
  load: () => void
  loadError: string
  loadProgress: PullRequestProgress
  loadedCount: number
  loading: boolean
  openCount: number
  pullRequests: PullRequests
  setTokenInput: (value: string) => void
  tokenInput: string
}

const EMPTY_PULL_REQUEST_CACHE: PullRequestCache = { cachedAt: null, pullRequests: {} }

export function useLivePullRequests(report: UpdaterReportSnapshot): LivePullRequestModel {
  const [tokenInput, setTokenInput] = useState('')
  const [loadProgress, setLoadProgress] = useState<PullRequestProgress>({ completed: 0, failures: 0, total: 0 })
  const query = useQuery({
    enabled: false,
    queryFn: async ({ signal }) => {
      const pullRequests = await fetchPullRequests(report.results, report.github_api_url, tokenInput.trim(), {
        onProgress: setLoadProgress,
        signal
      })
      return { cachedAt: new Date().toISOString(), pullRequests }
    },
    queryKey: pullRequestQueryKey(report.github_api_url, report.feed_id),
    retry: false,
    select: validatedPullRequestCache,
    staleTime: Infinity
  })
  const { cachedAt, pullRequests } = query.data ?? EMPTY_PULL_REQUEST_CACHE

  const load = () => {
    setLoadProgress({ completed: 0, failures: 0, total: 0 })
    void query.refetch()
  }
  const currentKeys = new Set(report.results.filter(hasPullRequest).map(pullRequestKey))
  const failures: PullRequestFailure[] = []
  let loadedCount = 0
  let openCount = 0

  for (const [key, lookup] of Object.entries(pullRequests)) {
    if (!currentKeys.has(key)) continue
    if (lookup.status === 'failed') failures.push({ key, message: lookup.message })
    else {
      loadedCount += 1
      if (lookup.pullRequest.state === 'open') openCount += 1
    }
  }

  return {
    cachedAt,
    clearToken: () => setTokenInput(''),
    createTokenUrl: createGitHubTokenUrl(report),
    failures,
    load,
    loadError: query.error?.message ?? '',
    loadProgress,
    loadedCount,
    loading: query.isFetching,
    openCount,
    pullRequests,
    setTokenInput,
    tokenInput
  }
}

function validatedPullRequestCache(value: unknown): PullRequestCache {
  const result = z.safeParse(pullRequestCacheSchema, value)
  return result.success ? result.data : EMPTY_PULL_REQUEST_CACHE
}
