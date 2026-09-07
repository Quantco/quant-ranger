import * as z from 'zod/mini'

import type { UpdaterReportResult } from './updater-report'

const pullRequestStateSchema = z.enum(['closed', 'merged', 'open'])
const ciStatusSchema = z.enum(['failure', 'none', 'pending', 'success'])
const reviewStatusSchema = z.enum(['approved', 'changes-requested', 'none', 'pending'])
const livePullRequestSchema = z.object({
  ciStatus: z.nullable(ciStatusSchema),
  comments: z.number(),
  createdAt: z.string(),
  hasMergeConflicts: z.nullable(z.boolean()),
  hasNonQuantRangerCommits: z.boolean(),
  reviewStatus: z.nullable(reviewStatusSchema),
  reviewers: z.array(z.object({ label: z.string(), url: z.string() })),
  state: pullRequestStateSchema,
  title: z.string(),
  updatedAt: z.string()
})
const pullRequestLookupSchema = z.union([
  z.object({ message: z.string(), status: z.literal('failed') }),
  z.object({ pullRequest: livePullRequestSchema, status: z.literal('loaded') })
])
export const pullRequestsSchema = z.record(z.string(), pullRequestLookupSchema)

export type PullRequestState = z.infer<typeof pullRequestStateSchema>
export type CiStatus = z.infer<typeof ciStatusSchema>
export type ReviewStatus = z.infer<typeof reviewStatusSchema>
export type LivePullRequest = z.infer<typeof livePullRequestSchema>
export type PullRequestLookup = z.infer<typeof pullRequestLookupSchema>
export type PullRequests = z.infer<typeof pullRequestsSchema>

export type UpdaterResultWithPullRequest = UpdaterReportResult & { pull_request: number }

export function hasPullRequest(result: UpdaterReportResult): result is UpdaterResultWithPullRequest {
  return result.pull_request != null
}

export function parseGitHubRepository(repository: string): { owner: string; repo: string } | null {
  const [owner, repo, ...remainder] = repository.split('/')
  return owner != null && owner !== '' && repo != null && repo !== '' && remainder.length === 0 ? { owner, repo } : null
}

export function getLoadedPullRequest(lookup: PullRequestLookup | undefined): LivePullRequest | undefined {
  return lookup?.status === 'loaded' ? lookup.pullRequest : undefined
}

export function pullRequestKey(result: Pick<UpdaterResultWithPullRequest, 'pull_request' | 'repository'>): string {
  return `${result.repository}#${result.pull_request}`
}
