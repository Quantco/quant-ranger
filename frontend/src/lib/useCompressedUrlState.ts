import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router'

import { createCompressedJsonCodec } from './compressed-json-codec'

const STATE_PARAMETER = 'state'
const stateCodec = createCompressedJsonCodec({
  maxCompressedLength: 10_000,
  maxDecompressedLength: 100_000
})

export function useCompressedUrlReducer<State, Action>({
  defaultState,
  parse,
  reducer
}: {
  defaultState: State
  parse: (value: unknown) => State | null
  reducer: (state: State, action: Action) => State
}) {
  const [searchParameters, setSearchParameters] = useSearchParams()
  const read = useCallback(
    (parameters: URLSearchParams) => {
      const encoded = parameters.get(STATE_PARAMETER)
      return encoded == null ? defaultState : (parse(stateCodec.decode(encoded)) ?? defaultState)
    },
    [defaultState, parse]
  )
  const state = useMemo(() => read(searchParameters), [read, searchParameters])
  const dispatch = useCallback(
    (action: Action) => {
      setSearchParameters(
        (parameters) => new URLSearchParams([[STATE_PARAMETER, stateCodec.encode(reducer(read(parameters), action))]]),
        { preventScrollReset: true, replace: true }
      )
    },
    [read, reducer, setSearchParameters]
  )
  const resetState = useCallback(
    () => setSearchParameters({}, { preventScrollReset: true, replace: true }),
    [setSearchParameters]
  )
  return { dispatch, resetState, state }
}
