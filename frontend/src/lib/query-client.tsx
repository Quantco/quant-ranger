import { QueryClient } from '@tanstack/react-query'

export const queryClient = new QueryClient({ defaultOptions: { queries: { gcTime: Infinity } } })

const PULL_REQUEST_QUERY_SCOPE = 'pull-requests'

export const feedQueryKey = (githubApiUrl: string, feedId: string) =>
  [PULL_REQUEST_QUERY_SCOPE, githubApiUrl, feedId] as const

export const pullRequestQueryKey = (githubApiUrl: string, feedId: string, pullRequest: string) =>
  [...feedQueryKey(githubApiUrl, feedId), pullRequest] as const
