import { hasPullRequest, parseGitHubRepository } from './pull-request'
import type { UpdaterReportSnapshot } from './updater-report'

export function createGitHubTokenUrl(report: UpdaterReportSnapshot): string | null {
  const candidates = report.results.filter(hasPullRequest)
  const repositories = candidates.map(({ repository }) => parseGitHubRepository(repository))
  const firstRepository = repositories[0]
  if (
    !firstRepository ||
    repositories.some(
      (repository) => repository?.owner.toLocaleLowerCase() !== firstRepository.owner.toLocaleLowerCase()
    )
  )
    return null

  if (!URL.canParse(report.github_api_url)) return null
  const apiHost = new URL(report.github_api_url).hostname
  if (apiHost !== 'api.github.com' && !(apiHost.startsWith('api.') && apiHost.endsWith('.ghe.com'))) return null
  const firstResultUrl = candidates[0]?.url
  if (
    firstResultUrl == null ||
    firstResultUrl === '' ||
    !URL.canParse('/settings/personal-access-tokens/new', firstResultUrl)
  )
    return null
  const url = new URL('/settings/personal-access-tokens/new', firstResultUrl)
  url.search = new URLSearchParams({
    actions: 'read',
    description: 'Read-only pull request data for the Quant Ranger dashboard',
    expires_in: '30',
    name: 'Quant Ranger dashboard',
    pull_requests: 'read',
    target_name: firstRepository.owner
  }).toString()
  return url.href
}
