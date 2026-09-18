import LZString from 'lz-string'
import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router'

const STATE_PARAMETER = 'state'
const MAX_COMPRESSED_LENGTH = 10_000
const MAX_DECOMPRESSED_LENGTH = 100_000

// lz-string's declarations omit the null returned for invalid compressed input.
const decompress: (encoded: string) => string | null = LZString.decompressFromEncodedURIComponent

export type UrlState<State> = {
  /** Drops the parameter entirely rather than encoding the defaults. */
  resetState: () => void
  setState: (update: (previous: State) => State) => void
  state: State
}

/**
 * Stores one dashboard state object in the `state` search parameter, compressed
 * so that long filter selections still fit in a shareable URL.
 *
 * `parse` guards everything coming from the URL and returns null for anything it
 * does not recognise; unusable values fall back to `defaultState`. Decoding is
 * keyed on the raw parameter alone, so an unmemoized `parse` costs a validation
 * pass per render but never a decompression.
 */
export const useUrlState = <State>({
  defaultState,
  parse
}: {
  defaultState: State
  parse: (value: unknown) => State | null
}): UrlState<State> => {
  const [searchParameters, setSearchParameters] = useSearchParams()

  const read = useCallback(
    (parameters: URLSearchParams): State => parse(decodeStateParameter(parameters)) ?? defaultState,
    [defaultState, parse]
  )

  const write = useCallback(
    (encode: (parameters: URLSearchParams) => string | null) =>
      setSearchParameters(
        (parameters) => {
          // Rewrite only our own parameter so that unrelated ones survive.
          const updated = new URLSearchParams(parameters)
          const encoded = encode(parameters)
          if (encoded == null) updated.delete(STATE_PARAMETER)
          else updated.set(STATE_PARAMETER, encoded)
          return updated
        },
        { preventScrollReset: true, replace: true }
      ),
    [setSearchParameters]
  )

  const reset = useCallback(() => {
    write(() => null)
  }, [write])

  const set = useCallback(
    (update: (previous: State) => State) => {
      write((parameters) => LZString.compressToEncodedURIComponent(JSON.stringify(update(read(parameters)))))
    },
    [read, write]
  )

  return {
    resetState: reset,
    setState: set,
    state: useMemo(() => read(searchParameters), [read, searchParameters])
  }
}

// Decompressing is the expensive half of a read, so it is cached on the exact
// parameter value and shared by every caller regardless of hook instance.
const decoded = new Map<string, unknown>()

const decodeStateParameter = (parameters: URLSearchParams): unknown => {
  const encoded = parameters.get(STATE_PARAMETER)
  if (encoded == null || encoded.length > MAX_COMPRESSED_LENGTH) return null
  if (decoded.has(encoded)) return decoded.get(encoded)

  const json = decompress(encoded)
  const value = json == null || json.length > MAX_DECOMPRESSED_LENGTH ? null : parseJson(json)
  // Only the current URL is read repeatedly; anything older is dead weight.
  decoded.clear()
  decoded.set(encoded, value)
  return value
}

const parseJson = (value: string): unknown => {
  try {
    return JSON.parse(value)
  } catch (error) {
    if (error instanceof SyntaxError) return null
    throw error
  }
}
