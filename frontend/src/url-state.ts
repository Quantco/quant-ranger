export function queryParameters(hash: string): URLSearchParams {
  const queryStart = hash.indexOf("?");
  return new URLSearchParams(queryStart === -1 ? "" : hash.slice(queryStart + 1));
}

export function setsEqual(left: Set<string>, right: Set<string>): boolean {
  return left.size === right.size && [...left].every((value) => right.has(value));
}

export function replaceHash(hash: string): void {
  if (window.location.hash !== hash) window.history.replaceState(window.history.state, "", hash);
}
