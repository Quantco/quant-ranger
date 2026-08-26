export async function fetchJson(url: string, init?: RequestInit): Promise<unknown> {
  const headers = new Headers(init?.headers)
  // Prevent Vite's SPA fallback from serving index.html for missing development data.
  headers.set('Accept', 'application/json')

  let response: Response
  try {
    response = await fetch(url, { ...init, cache: 'no-cache', headers })
  } catch (error) {
    if (init?.signal?.aborted) throw error
    throw new Error(`Could not request ${url}. Check your connection and reload the page.`, {
      cause: error
    })
  }

  if (response.status === 404) return null
  if (!response.ok) throw new Error(`Could not load ${url} (HTTP ${response.status}).`)

  try {
    return await response.json()
  } catch (error) {
    if (!(error instanceof SyntaxError)) throw error
    throw new Error(`${url} does not contain valid JSON.`, { cause: error })
  }
}
