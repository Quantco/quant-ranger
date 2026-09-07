interface LabelledOption {
  label: string
}

/** Filters options by label and orders equally ranked matches by their original position. */
export function filterOptions<Option extends LabelledOption>(options: Option[], query: string, limit?: number) {
  const matches: { index: number; option: Option; rank: number }[] = []
  for (const [index, option] of options.entries()) {
    const rank = optionMatchRank(option.label, query)
    if (rank != null) matches.push({ index, option, rank })
  }

  matches.sort((left, right) => left.rank - right.rank || left.index - right.index)
  const limitedMatches = limit == null ? matches : matches.slice(0, limit)
  return limitedMatches.map(({ option }) => option)
}

/**
 * Scores an option label for autocomplete matching. Lower ranks are better:
 * exact match, label prefix, word prefix, then substring. An empty query gives
 * every option the same rank so that the original option order is preserved.
 */
function optionMatchRank(label: string, query: string): number | null {
  const candidate = label.toLocaleLowerCase()
  const search = query.trim().toLocaleLowerCase()
  if (search === '' || candidate === search) return 0
  if (candidate.startsWith(search)) return 1
  if (candidate.split(/[^a-zA-Z0-9]+/).some((word) => word.startsWith(search))) return 2
  if (candidate.includes(search)) return 3
  return null
}
