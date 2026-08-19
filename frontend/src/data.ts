function displayPath(url: string) {
  return url.replace(/^\.\//, "");
}

function isHtml(response: Response, body: string) {
  return response.headers.get("content-type")?.includes("text/html") === true || /^\s*<(?:!doctype\s+html|html)[\s>]/i.test(body);
}

export async function fetchJson<T>(url: string): Promise<T | null> {
  let response: Response;
  try {
    response = await fetch(url, { cache: "no-cache" });
  } catch {
    throw new Error(`Could not request ${displayPath(url)}. Check your connection and reload the page.`);
  }

  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`Could not load ${displayPath(url)} (HTTP ${response.status}).`);

  const body = await response.text();
  if (isHtml(response, body)) return null;

  try {
    return JSON.parse(body) as T;
  } catch {
    throw new Error(`${displayPath(url)} does not contain valid JSON.`);
  }
}
