import { DashboardSection } from '../components/dashboard/DashboardSection'
import { PullRequestDataControls } from './PullRequestDataControls'
import { PullRequestDataStatus } from './PullRequestDataStatus'
import type { LivePullRequestModel } from './useLivePullRequests'

export function PullRequestDataPanel({ githubApiUrl, model }: { githubApiUrl: string; model: LivePullRequestModel }) {
  return (
    <DashboardSection heading="Live pull request data">
      <PullRequestDataControls githubApiUrl={githubApiUrl} model={model} />
      <PullRequestDataStatus model={model} />
    </DashboardSection>
  )
}
