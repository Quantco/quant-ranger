export async function fetchJson(url: string, signal: AbortSignal): Promise<unknown> {
  let response: Response
  try {
    response = await fetch(url, {
      cache: 'no-cache',
      // Prevent Vite's SPA fallback from serving index.html for missing development data.
      headers: { Accept: 'application/json' },
      signal
    })
  } catch (error) {
    signal.throwIfAborted()
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
