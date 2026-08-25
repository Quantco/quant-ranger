import LZString from 'lz-string'

import type { DashboardSnapshot } from './dashboard'
import {
  COPIER_DASHBOARD_STATE_VERSION,
  parseStoredDashboardState,
  restoreDashboardState,
  storeDashboardState,
  type CopierDashboardUrlState
} from './dashboard-url-state'

export type { CopierDashboardUrlState, StoredDashboardState } from './dashboard-url-state'

const STATE_PARAMETER = 'state'
const STATE_PREFIX = `v${COPIER_DASHBOARD_STATE_VERSION}.`
const MAX_COMPRESSED_STATE_LENGTH = 10_000
const MAX_DECOMPRESSED_STATE_LENGTH = 100_000
const { compressToEncodedURIComponent, decompressFromEncodedURIComponent } = LZString

export function readCopierDashboardUrlState(
  snapshot: DashboardSnapshot,
  parameters: URLSearchParams
): CopierDashboardUrlState {
  const encodedState = parameters.get(STATE_PARAMETER)
  const storedState = encodedState == null ? null : decodeDashboardState(encodedState)
  return restoreDashboardState(snapshot, storedState ?? { version: COPIER_DASHBOARD_STATE_VERSION })
}

export function copierDashboardSearchParameters(state: CopierDashboardUrlState): URLSearchParams {
  const stored = storeDashboardState(state)
  if (Object.keys(stored).length === 1) return new URLSearchParams()

  const encoded = compressToEncodedURIComponent(JSON.stringify(stored))
  return new URLSearchParams([[STATE_PARAMETER, `${STATE_PREFIX}${encoded}`]])
}

function decodeDashboardState(encoded: string) {
  if (!encoded.startsWith(STATE_PREFIX) || encoded.length > MAX_COMPRESSED_STATE_LENGTH) return null

  try {
    const json = decompressFromEncodedURIComponent(encoded.slice(STATE_PREFIX.length))
    if (json == null || json.length > MAX_DECOMPRESSED_STATE_LENGTH) return null
    return parseStoredDashboardState(JSON.parse(json))
  } catch {
    return null
  }
}
