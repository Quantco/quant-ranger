import { QueryClient } from '@tanstack/react-query'

export const queryClient = new QueryClient({ defaultOptions: { queries: { gcTime: Infinity } } })

const PULL_REQUEST_QUERY_SCOPE = 'pull-requests'

/** Prefix shared by every pull request in one feed, so the whole feed can be refetched at once. */
export const pullRequestQueryKey = (githubApiUrl: string, feedId: string) =>
  [PULL_REQUEST_QUERY_SCOPE, githubApiUrl, feedId] as const

export const livePullRequestQueryKey = (githubApiUrl: string, feedId: string, pullRequest: string) =>
  [...pullRequestQueryKey(githubApiUrl, feedId), pullRequest] as const
