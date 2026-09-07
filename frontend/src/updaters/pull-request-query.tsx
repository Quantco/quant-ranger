import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

const PULL_REQUEST_QUERY_SCOPE = 'pull-requests'
const queryClient = new QueryClient({ defaultOptions: { queries: { gcTime: Infinity } } })

export function PullRequestQueryProvider({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
}

export function pullRequestQueryKey(githubApiUrl: string, feedId: string) {
  return [PULL_REQUEST_QUERY_SCOPE, githubApiUrl, feedId] as const
}
