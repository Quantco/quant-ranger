import { Octokit } from '@octokit/rest'
import pLimit from 'p-limit'
import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react'

const MAX_CONCURRENT_REQUESTS = 6

type OctokitContextValue = {
  /** Adopts the typed token as the credentials for every later request. */
  commitToken: () => void
  octokit: Octokit
}

type GitHubTokenContextValue = {
  clearToken: () => void
  setTokenInput: (value: string) => void
  tokenInput: string
}

// Two contexts rather than one: the token field changes on every keystroke,
// and the data layer only needs the client, which never changes at all.
const OctokitContext = createContext<OctokitContextValue | null>(null)
const GitHubTokenContext = createContext<GitHubTokenContextValue | null>(null)

export const OctokitProvider = ({ children, githubApiUrl }: { children: ReactNode; githubApiUrl: string }) => {
  const [tokenInput, setTokenInput] = useState('')
  // Both tokens are refs so that typing rebuilds neither the client nor the
  // Octokit context: `typedToken` mirrors the field, `committedToken` holds the
  // credentials requests actually use, and only `commitToken` moves one to the
  // other. Without that step a half-typed token would be sent by every request
  // still queued behind the limiter, since each one authenticates at the moment
  // the limiter admits it.
  const typedToken = useRef('')
  const committedToken = useRef('')

  const updateToken = useCallback((value: string) => {
    typedToken.current = value
    setTokenInput(value)
  }, [])

  const octokit = useMemo(() => createOctokitClient(githubApiUrl, () => committedToken.current), [githubApiUrl])
  const client = useMemo(
    () => ({
      commitToken: () => {
        committedToken.current = typedToken.current.trim()
      },
      octokit
    }),
    [octokit]
  )
  const token = useMemo(
    () => ({ clearToken: () => updateToken(''), setTokenInput: updateToken, tokenInput }),
    [tokenInput, updateToken]
  )

  return (
    <OctokitContext value={client}>
      <GitHubTokenContext value={token}>{children}</GitHubTokenContext>
    </OctokitContext>
  )
}

export const useOctokit = (): OctokitContextValue => {
  const value = useContext(OctokitContext)
  if (value == null) throw new Error('useOctokit must be used inside OctokitProvider.')
  return value
}

export const useGitHubToken = (): GitHubTokenContextValue => {
  const value = useContext(GitHubTokenContext)
  if (value == null) throw new Error('useGitHubToken must be used inside OctokitProvider.')
  return value
}

/** Create an octokit client, that rate limits concurrent requests to a maximum of `MAX_CONCURRENT_REQUESTS` */
const createOctokitClient = (githubApiUrl: string, committedToken: () => string) => {
  const limit = pLimit({ concurrency: MAX_CONCURRENT_REQUESTS })
  const octokit = new Octokit({ baseUrl: githubApiUrl })

  // Authenticating per request rather than at construction is what lets one
  // instance outlive any number of token changes. Registration order matters:
  // the last hook registered is the outermost, so the limiter wraps the `before`
  // hook and a queued request reads the committed token when it is admitted
  // rather than when it was enqueued.
  octokit.hook.before('request', (options) => {
    const token = committedToken()
    if (token !== '') options.headers.authorization = `token ${token}`
  })
  octokit.hook.wrap('request', (request, options) => limit(() => request(options)))

  return octokit
}
