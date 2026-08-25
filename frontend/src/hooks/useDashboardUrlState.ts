import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router'

type DashboardUrlStateOptions<Context, State extends object> = {
  context: Context
  read: (context: Context, parameters: URLSearchParams) => State
  write: (state: State, context: Context) => URLSearchParams
}

export function useDashboardUrlState<Context, State extends object>({
  context,
  read,
  write
}: DashboardUrlStateOptions<Context, State>) {
  const [searchParameters, setSearchParameters] = useSearchParams()
  const state = useMemo(() => read(context, searchParameters), [context, read, searchParameters])
  const updateState = useCallback(
    (changes: Partial<State>) => {
      setSearchParameters(write({ ...state, ...changes }, context), {
        preventScrollReset: true,
        replace: true
      })
    },
    [context, setSearchParameters, state, write]
  )

  return [state, updateState] as const
}
